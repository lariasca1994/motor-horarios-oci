#!/usr/bin/env bash
# Expone MySQL HeatWave (subred privada) con un Network Load Balancer Always Free en
# la subred pública, para que Render pueda conectarse. El puerto 3306 solo se abre a
# las IPs de PERMITIR_IPS (tu IP + IPs de salida de Render), nunca a 0.0.0.0/0.
# Uso: PERMITIR_IPS="1.2.3.4 5.6.7.8" bash deploy/06_nlb_mysql.sh
#      (reejecutarlo solo actualiza la lista de IPs permitidas)
set -euo pipefail
cd "$(dirname "$0")"
source <(tr -d '\r' < estado.env)
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
guardar() { grep -q "^$1=" estado.env && sed -i "s#^$1=.*#$1=$2#" estado.env || echo "$1=$2" >> estado.env; }
: "${PERMITIR_IPS:?Define PERMITIR_IPS con las IPs que pueden llegar a MySQL}"

if [ -z "${NLB_ID:-}" ]; then
  NLB_ID=$(oci nlb network-load-balancer create -c "$COMPARTMENT" --display-name motor-mysql-nlb \
      --subnet-id "$SUBNET_PUBLICA" --is-private false --is-preserve-source-destination false \
      --backend-sets "{\"mysql\": {\"policy\": \"FIVE_TUPLE\", \"isPreserveSource\": false,
                        \"healthChecker\": {\"protocol\": \"TCP\", \"port\": 3306},
                        \"backends\": [{\"ipAddress\": \"$MYSQL_IP\", \"port\": 3306}]}}" \
      --listeners '{"mysql": {"name": "mysql", "defaultBackendSetName": "mysql", "port": 3306, "protocol": "TCP"}}' \
      --wait-for-state SUCCEEDED --max-wait-seconds 1800 --query 'data.resources[0].identifier' --raw-output | tr -d '\r')
  guardar NLB_ID "$NLB_ID"
fi
NLB_IP=$(oci nlb network-load-balancer get --network-load-balancer-id "$NLB_ID" \
    --query 'data."ip-addresses"[?"is-public"] | [0]."ip-address"' --raw-output | tr -d '\r')
guardar NLB_IP "$NLB_IP"

# Reglas de la subred pública: HTTP/HTTPS, SSH desde MI_IP (si existe) y MySQL solo desde PERMITIR_IPS
REGLAS=$(PERMITIR_IPS="$PERMITIR_IPS" python - <<'PY'
import json, os
ips = os.environ["PERMITIR_IPS"].split()
reglas = [{"source": "0.0.0.0/0", "protocol": "6", "tcpOptions": {"destinationPortRange": {"min": p, "max": p}}}
          for p in (80, 443)]
reglas.append({"source": "0.0.0.0/0", "protocol": "1", "icmpOptions": {"type": 3, "code": 4}})
for ip in ips:
    cidr = ip if "/" in ip else ip + "/32"
    reglas.append({"source": cidr, "protocol": "6", "description": "MySQL via NLB",
                   "tcpOptions": {"destinationPortRange": {"min": 3306, "max": 3306}}})
print(json.dumps(reglas))
PY
)
oci network security-list update --security-list-id "$SL_PUBLICA" --ingress-security-rules "$REGLAS" --force >/dev/null
echo "MySQL publicado en $NLB_IP:3306 solo para: $PERMITIR_IPS"
