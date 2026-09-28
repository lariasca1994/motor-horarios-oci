#!/usr/bin/env bash
# Red dentro de PRPagos-vnc (la cuenta Free Tier solo admite 2 VCN):
#   subred pública 10.0.20.0/24 -> VM (HTTP/HTTPS abiertos, SSH solo desde MI_IP)
#   subred privada 10.0.21.0/24 -> MySQL (solo accesible desde la subred pública)
# No modifica la subred ni las reglas existentes de PRPagos; reutiliza su internet gateway.
# Uso: MI_IP=1.2.3.4 bash deploy/01_red.sh
set -euo pipefail
cd "$(dirname "$0")"
source <(tr -d '\r' < estado.env)
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
guardar() { grep -q "^$1=" estado.env && sed -i "s#^$1=.*#$1=$2#" estado.env || echo "$1=$2" >> estado.env; }
id_de() { tr -d '\r'; }
: "${MI_IP:?Define MI_IP con tu IP pública para permitir SSH}"

VCN=$(oci network vcn list -c "$TENANCY" --display-name PRPagos-vnc --query 'data[0].id' --raw-output | id_de)
IGW=$(oci network internet-gateway list -c "$TENANCY" --vcn-id "$VCN" --query 'data[0].id' --raw-output | id_de)
guardar VCN "$VCN"

RT_PUB=$(oci network route-table create -c "$COMPARTMENT" --vcn-id "$VCN" --display-name motor-rt-publica \
      --route-rules "[{\"destination\": \"0.0.0.0/0\", \"destinationType\": \"CIDR_BLOCK\", \"networkEntityId\": \"$IGW\"}]" \
      --wait-for-state AVAILABLE --query data.id --raw-output | id_de)
RT_PRIV=$(oci network route-table create -c "$COMPARTMENT" --vcn-id "$VCN" --display-name motor-rt-privada \
      --route-rules '[]' --wait-for-state AVAILABLE --query data.id --raw-output | id_de)

SL_PUB=$(oci network security-list create -c "$COMPARTMENT" --vcn-id "$VCN" --display-name motor-sl-publica \
      --ingress-security-rules "[
        {\"source\": \"0.0.0.0/0\", \"protocol\": \"6\", \"tcpOptions\": {\"destinationPortRange\": {\"min\": 80, \"max\": 80}}},
        {\"source\": \"0.0.0.0/0\", \"protocol\": \"6\", \"tcpOptions\": {\"destinationPortRange\": {\"min\": 443, \"max\": 443}}},
        {\"source\": \"$MI_IP/32\", \"protocol\": \"6\", \"tcpOptions\": {\"destinationPortRange\": {\"min\": 22, \"max\": 22}}},
        {\"source\": \"0.0.0.0/0\", \"protocol\": \"1\", \"icmpOptions\": {\"type\": 3, \"code\": 4}}]" \
      --egress-security-rules '[{"destination": "0.0.0.0/0", "protocol": "all"}]' \
      --wait-for-state AVAILABLE --query data.id --raw-output | id_de)
SL_PRIV=$(oci network security-list create -c "$COMPARTMENT" --vcn-id "$VCN" --display-name motor-sl-privada \
      --ingress-security-rules '[
        {"source": "10.0.20.0/24", "protocol": "6", "tcpOptions": {"destinationPortRange": {"min": 3306, "max": 3306}}},
        {"source": "10.0.20.0/24", "protocol": "6", "tcpOptions": {"destinationPortRange": {"min": 33060, "max": 33060}}}]' \
      --egress-security-rules '[{"destination": "10.0.20.0/24", "protocol": "all"}]' \
      --wait-for-state AVAILABLE --query data.id --raw-output | id_de)
guardar SL_PUBLICA "$SL_PUB"

SUBNET_PUB=$(oci network subnet create -c "$COMPARTMENT" --vcn-id "$VCN" --display-name motor-subred-publica \
      --cidr-block 10.0.20.0/24 --dns-label motorpub --route-table-id "$RT_PUB" \
      --security-list-ids "[\"$SL_PUB\"]" --wait-for-state AVAILABLE --query data.id --raw-output | id_de)
SUBNET_PRIV=$(oci network subnet create -c "$COMPARTMENT" --vcn-id "$VCN" --display-name motor-subred-privada \
      --cidr-block 10.0.21.0/24 --dns-label motorpriv --route-table-id "$RT_PRIV" --prohibit-public-ip-on-vnic true \
      --security-list-ids "[\"$SL_PRIV\"]" --wait-for-state AVAILABLE --query data.id --raw-output | id_de)
guardar SUBNET_PUBLICA "$SUBNET_PUB"
guardar SUBNET_PRIVADA "$SUBNET_PRIV"
echo "Red creada"
