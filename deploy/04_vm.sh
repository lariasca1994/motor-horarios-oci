#!/usr/bin/env bash
# VM Always Free (Ampere A1, Ubuntu 24.04) en la subred pública.
# Reintenta mientras OCI responda "Out of host capacity" o 429 (INTENTOS x ESPERA segundos).
set -euo pipefail
cd "$(dirname "$0")"
source <(tr -d '\r' < estado.env)
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
guardar() { grep -q "^$1=" estado.env && sed -i "s#^$1=.*#$1=$2#" estado.env || echo "$1=$2" >> estado.env; }
LLAVE="$HOME/.ssh/motor_horarios_oci"
OCPUS="${OCPUS:-1}"; MEMORIA="${MEMORIA:-6}"
INTENTOS="${INTENTOS:-120}"; ESPERA="${ESPERA:-180}"

[ -f "$LLAVE" ] || ssh-keygen -t ed25519 -N "" -C motor-horarios-oci -f "$LLAVE" >/dev/null
IMAGEN=$(oci compute image list -c "$COMPARTMENT" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
          --shape VM.Standard.A1.Flex --sort-by TIMECREATED --limit 1 --query 'data[0].id' --raw-output 2>/dev/null | tr -d '\r')

for i in $(seq 1 "$INTENTOS"); do
  SALIDA=$(oci compute instance launch -c "$COMPARTMENT" --availability-domain "$AD" --display-name motor-vm \
      --shape VM.Standard.A1.Flex --shape-config "{\"ocpus\": $OCPUS, \"memoryInGBs\": $MEMORIA}" \
      --image-id "$IMAGEN" --subnet-id "$SUBNET_PUBLICA" --assign-public-ip true \
      --ssh-authorized-keys-file "$LLAVE.pub" --user-data-file vm/cloud-init.yaml \
      --wait-for-state RUNNING --max-wait-seconds 900 --query 'data.id' --raw-output 2>&1) && break
  if echo "$SALIDA" | grep -qiE "capacity|TooManyRequests|\"status\": 429"; then
    echo "Intento $i ($(date +%H:%M)): sin capacidad o límite de peticiones, reintento en $ESPERA s"; sleep "$ESPERA"
  else
    echo "$SALIDA" >&2; exit 1
  fi
done
VM=$(echo "$SALIDA" | grep -o 'ocid1.instance[^" ]*' | tail -1 | tr -d '\r')
[ -n "$VM" ] || { echo "No se pudo crear la VM tras $INTENTOS intentos"; exit 1; }
guardar VM_ID "$VM"
IP=$(oci compute instance list-vnics --instance-id "$VM" --query 'data[0]."public-ip"' --raw-output | tr -d '\r')
PRIV=$(oci compute instance list-vnics --instance-id "$VM" --query 'data[0]."private-ip"' --raw-output | tr -d '\r')
guardar VM_IP "$IP"
guardar VM_IP_PRIVADA "$PRIV"
echo "VM lista: $IP (privada $PRIV)"
