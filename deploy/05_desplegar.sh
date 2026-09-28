#!/usr/bin/env bash
# Sube el código a la VM, la primera vez crea la base en MySQL y el secreto en Vault,
# y (re)inicia los servicios. Se puede volver a ejecutar para desplegar cambios.
set -euo pipefail
cd "$(dirname "$0")"
source <(tr -d '\r' < estado.env)
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
guardar() { grep -q "^$1=" estado.env && sed -i "s#^$1=.*#$1=$2#" estado.env || echo "$1=$2" >> estado.env; }
RAIZ=$(cd .. && pwd)
LLAVE="$HOME/.ssh/motor_horarios_oci"
SSH="ssh -i $LLAVE -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 ubuntu@$VM_IP"

echo "== Empaquetando código"
PAQUETE=$(mktemp -d)/motor-horarios.tar.gz
tar -czf "$PAQUETE" -C "$RAIZ" --exclude='__pycache__' --exclude='*.pyc' \
    functions/api functions/motor frontend db local/crear_bd.py local/crear_usuarios.py deploy/vm
scp -q -i "$LLAVE" -o StrictHostKeyChecking=accept-new "$PAQUETE" "ubuntu@$VM_IP:/tmp/motor-horarios.tar.gz"
$SSH "sudo bash -s" < <(tr -d '\r' < vm/instalar.sh)

if [ -z "${DB_SECRET_ID:-}" ]; then
  echo "== Primera vez: creando base de datos y usuario de la app en MySQL ($MYSQL_IP)"
  source <(tr -d '\r' < .secretos)
  # La clave de admin viaja por stdin (no queda en la línea de comandos de la VM)
  printf '%s\n' "$MYSQL_ADMIN_PASSWORD" | $SSH "read -r P; sudo -u motor env MYSQL_ADMIN_PASSWORD=\"\$P\" \
      /opt/motor-horarios/.venv/bin/python /opt/motor-horarios/local/crear_bd.py \
      --host $MYSQL_IP --admin $MYSQL_ADMIN_USER --desde '10.0.20.%' --ssl --sin-demo \
      --env /opt/motor-horarios/db.env"
  CREDS=$($SSH "sudo cat /opt/motor-horarios/db.env && sudo rm -f /opt/motor-horarios/db.env" | tr -d '\r')
  JSON=$(echo "$CREDS" | python -c "
import json, sys
kv = dict(l.split('=', 1) for l in sys.stdin.read().splitlines() if '=' in l and not l.startswith('#'))
print(json.dumps({'host': kv['DB_HOST'], 'port': int(kv['DB_PORT']), 'user': kv['DB_USER'],
                  'password': kv['DB_PASSWORD'], 'database': kv['DB_NAME']}))")
  SECRETO=$(oci vault secret create-base64 -c "$COMPARTMENT" --vault-id "$VAULT_ID" --key-id "$VAULT_KEY_ID" \
      --secret-name motor-horarios-bd --description "Credenciales MySQL de la app" \
      --secret-content-content "$(printf '%s' "$JSON" | base64 -w0)" \
      --wait-for-state ACTIVE --query data.id --raw-output | tr -d '\r')
  guardar DB_SECRET_ID "$SECRETO"
  DB_SECRET_ID=$SECRETO
  echo "Secreto guardado en Vault"
fi

if [ -z "${SMTP_SECRET_ID:-}" ] && [ -f .smtp ] && ! grep -qE '^SMTP_PASSWORD=\s*$' .smtp; then
  echo "== Guardando credenciales SMTP en Vault"
  JSON=$(tr -d '\r' < .smtp | python -c "
import json, sys
kv = dict(l.split('=', 1) for l in sys.stdin.read().splitlines() if '=' in l and not l.startswith('#'))
print(json.dumps({'host': kv['SMTP_HOST'], 'port': int(kv.get('SMTP_PORT', 587)), 'user': kv['SMTP_USER'],
                  'password': kv['SMTP_PASSWORD'], 'from': kv['EMAIL_FROM'],
                  'from_name': kv.get('EMAIL_FROM_NAME', 'Motor de Horarios')}))")
  SMTP_SECRET_ID=$(oci vault secret create-base64 -c "$COMPARTMENT" --vault-id "$VAULT_ID" --key-id "$VAULT_KEY_ID" \
      --secret-name motor-horarios-smtp --description "Credenciales SMTP (Brevo)" \
      --secret-content-content "$(printf '%s' "$JSON" | base64 -w0)" \
      --wait-for-state ACTIVE --query data.id --raw-output | tr -d '\r')
  guardar SMTP_SECRET_ID "$SMTP_SECRET_ID"
fi
if [ -n "${SMTP_SECRET_ID:-}" ]; then EMAIL_CONF="EMAIL_MODE=smtp
SMTP_SECRET_OCID=$SMTP_SECRET_ID"; else EMAIL_CONF="EMAIL_MODE=log"; echo "AVISO: sin deploy/.smtp los correos solo van al log"; fi

# Clave para firmar sesiones: se genera una vez y se conserva entre despliegues
if ! grep -q '^AUTH_SECRET=' .secretos; then
  echo "AUTH_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" >> .secretos
fi
source <(tr -d '\r' < .secretos)

echo "== Configuración de servicios"
$SSH "sudo tee /etc/motor-horarios.env >/dev/null && sudo chmod 640 /etc/motor-horarios.env && sudo chown root:motor /etc/motor-horarios.env" <<CONF
DB_MODE=vault
DB_SECRET_OCID=$DB_SECRET_ID
OCI_AUTH=instance_principal
MOTOR_MODE=http
MOTOR_URL=http://127.0.0.1:8001/
$EMAIL_CONF
CORS_ORIGINS=http://$VM_IP
AUTH_SECRET=$AUTH_SECRET
TZ=America/Bogota
PYTHONUNBUFFERED=1
CONF
$SSH "sudo systemctl daemon-reload && sudo systemctl enable motor-motor motor-api >/dev/null 2>&1; sudo systemctl restart motor-motor motor-api"

if [ -f .usuarios_iniciales ]; then
  echo "== Cuentas iniciales (no cambia contraseñas ya existentes)"
  tr -d '\r' < .usuarios_iniciales | $SSH "sudo -u motor bash -c 'set -a; . /etc/motor-horarios.env; set +a;       /opt/motor-horarios/.venv/bin/python /opt/motor-horarios/local/crear_usuarios.py -'"
fi

echo "== Verificando"
for i in $(seq 1 20); do
  if curl -sf "http://$VM_IP/api/health/db" >/dev/null; then echo "OK: http://$VM_IP"; exit 0; fi
  sleep 3
done
echo "La API no respondió; logs:"; $SSH "sudo journalctl -u motor-api -u motor-motor -n 40 --no-pager"; exit 1
