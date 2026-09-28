#!/usr/bin/env bash
# Se ejecuta EN la VM (como root) después de subir /tmp/motor-horarios.tar.gz
set -euo pipefail
APP=/opt/motor-horarios
cloud-init status --wait >/dev/null || true

tar -xzf /tmp/motor-horarios.tar.gz -C "$APP"
cat > "$APP/frontend/js/config.js" <<'JS'
window.APP_CONFIG = { API_URL: "/api" };
JS
if [ ! -x "$APP/.venv/bin/python" ]; then python3 -m venv "$APP/.venv"; fi
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/functions/api/requirements.txt" -r "$APP/functions/motor/requirements.txt"
chown -R motor:motor "$APP"

install -m 644 "$APP/deploy/vm/motor-api.service" /etc/systemd/system/
install -m 644 "$APP/deploy/vm/motor-motor.service" /etc/systemd/system/
install -m 644 "$APP/deploy/vm/nginx.conf" /etc/nginx/sites-available/motor-horarios
ln -sf /etc/nginx/sites-available/motor-horarios /etc/nginx/sites-enabled/motor-horarios
rm -f /etc/nginx/sites-enabled/default
chmod 755 /opt /opt/motor-horarios

nginx -t
systemctl daemon-reload
systemctl reload nginx
if [ -f /etc/motor-horarios.env ]; then
    systemctl enable motor-motor.service motor-api.service
    systemctl restart motor-motor.service motor-api.service
    echo "Instalación completa, servicios reiniciados"
else
    echo "Código instalado; falta /etc/motor-horarios.env para arrancar los servicios"
fi
