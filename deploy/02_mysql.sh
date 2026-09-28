#!/usr/bin/env bash
# MySQL HeatWave Always Free (shape MySQL.Free) en la subred privada.
set -euo pipefail
cd "$(dirname "$0")"
source <(tr -d '\r' < estado.env); source <(tr -d '\r' < .secretos)
export OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True
guardar() { grep -q "^$1=" estado.env && sed -i "s#^$1=.*#$1=$2#" estado.env || echo "$1=$2" >> estado.env; }

DB=$(oci mysql db-system create -c "$COMPARTMENT" --display-name motor-mysql \
      --shape-name MySQL.Free --subnet-id "$SUBNET_PRIVADA" --availability-domain "$AD" \
      --admin-username "$MYSQL_ADMIN_USER" --admin-password "$MYSQL_ADMIN_PASSWORD" \
      --data-storage-size-in-gbs 50 --hostname-label motormysql \
      --wait-for-state ACTIVE --max-wait-seconds 3600 \
      --query 'data.id' --raw-output | tr -d '\r')
guardar MYSQL_ID "$DB"
IP=$(oci mysql db-system get --db-system-id "$DB" --query 'data."ip-address"' --raw-output | tr -d '\r')
guardar MYSQL_IP "$IP"
echo "MySQL listo en $IP"
