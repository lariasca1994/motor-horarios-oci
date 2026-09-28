#!/usr/bin/env bash
# Identidad de la VM (dynamic group + política) y Vault con llave de software.
# Los correos se envían por SMTP (Brevo); ver deploy/.smtp.example.
set -euo pipefail
cd "$(dirname "$0")"
source <(tr -d '\r' < estado.env)
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
guardar() { grep -q "^$1=" estado.env && sed -i "s#^$1=.*#$1=$2#" estado.env || echo "$1=$2" >> estado.env; }
id_de() { tr -d '\r'; }

# --- IAM: la VM se autentica como instance principal y solo puede leer secretos
oci iam dynamic-group create --name motor-horarios-vm \
    --description "VMs del compartimento motor-horarios" \
    --matching-rule "ALL {instance.compartment.id = '$COMPARTMENT'}" --wait-for-state ACTIVE >/dev/null
oci iam policy create -c "$COMPARTMENT" --name motor-horarios-vm \
    --description "Permisos de la VM del Motor de Horarios" \
    --statements '["Allow dynamic-group motor-horarios-vm to read secret-bundles in compartment motor-horarios"]' \
    --wait-for-state ACTIVE >/dev/null
echo "IAM listo"

# --- Vault (virtual, gratuito) + llave AES de software (gratuita)
VAULT=$(oci kms management vault create -c "$COMPARTMENT" --display-name motor-vault --vault-type DEFAULT \
        --wait-for-state ACTIVE --max-wait-seconds 1800 --query data.id --raw-output | id_de)
MGMT=$(oci kms management vault get --vault-id "$VAULT" --query 'data."management-endpoint"' --raw-output | id_de)
KEY=$(oci kms management key create -c "$COMPARTMENT" --display-name motor-llave --endpoint "$MGMT" \
        --key-shape '{"algorithm": "AES", "length": 32}' --protection-mode SOFTWARE \
        --wait-for-state ENABLED --max-wait-seconds 1800 --query data.id --raw-output | id_de)
guardar VAULT_ID "$VAULT"
guardar VAULT_KEY_ID "$KEY"
echo "Vault listo"
