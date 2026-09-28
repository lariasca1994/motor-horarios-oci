"""
Conexión a MySQL.

DB_MODE=env   (desarrollo local) -> DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME,
                                    opcional DB_SSL_CA (ruta), DB_SSL_CA_PEM (contenido del
                                    certificado) o DB_SSL=true (cifrado sin verificar).
DB_MODE=vault (OCI, por defecto) -> secreto JSON en OCI Vault (DB_SECRET_OCID).
                                    Siempre usa TLS; con "ssl_ca" además verifica el servidor.
"""
import os
import ssl as ssl_lib
import tempfile
from contextlib import contextmanager

import pymysql
import pymysql.cursors

_ca_path = None


def _config() -> dict:
    if os.environ.get("DB_MODE", "vault") == "env":
        return {
            "host": os.environ["DB_HOST"],
            "port": int(os.environ.get("DB_PORT", "3306")),
            "user": os.environ["DB_USER"],
            "password": os.environ["DB_PASSWORD"],
            "database": os.environ["DB_NAME"],
            "ssl_ca_path": os.environ.get("DB_SSL_CA") or _escribir_ca(os.environ.get("DB_SSL_CA_PEM")),
            "ssl": os.environ.get("DB_SSL", "false").lower() == "true",
        }

    from vault import credenciales_bd
    creds = credenciales_bd()
    return {
        "host": creds["host"],
        "port": int(creds.get("port", 3306)),
        "user": creds["user"],
        "password": creds["password"],
        "database": creds["database"],
        "ssl_ca_path": _escribir_ca(creds.get("ssl_ca")),
        "ssl": True,
    }


def _escribir_ca(pem: str | None) -> str | None:
    """PyMySQL necesita el certificado CA como archivo; en OCI solo /tmp es escribible."""
    global _ca_path
    if not pem:
        return None
    if _ca_path is None:
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
            f.write(pem)
            _ca_path = f.name
    return _ca_path


def get_connection() -> pymysql.connections.Connection:
    cfg = _config()
    if cfg["ssl_ca_path"]:
        # El archivo puede ser la CA o el propio certificado del servidor (pinning):
        # VERIFY_X509_PARTIAL_CHAIN permite confiar directamente en este último.
        ssl = ssl_lib.create_default_context(cafile=cfg["ssl_ca_path"])
        ssl.verify_flags |= ssl_lib.VERIFY_X509_PARTIAL_CHAIN
        ssl.verify_flags &= ~getattr(ssl_lib, "VERIFY_X509_STRICT", 0)  # el cert de HeatWave no trae extensiones
        ssl.check_hostname = os.environ.get("DB_SSL_CHECK_HOSTNAME", "true").lower() == "true"
    elif cfg["ssl"]:
        ssl = {"check_hostname": False}  # cifrado dentro de la VCN, sin verificar certificado
    else:
        ssl = None
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        ssl=ssl,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        autocommit=False,
    )


@contextmanager
def conexion():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
