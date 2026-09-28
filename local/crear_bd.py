"""
Crea la base de datos y el usuario de desarrollo en un MySQL local (sin Docker)
y carga el esquema + datos demo. Pide la contraseña del administrador por consola.

    .venv\\Scripts\\python local\\crear_bd.py [--host 127.0.0.1] [--port 3306] [--admin root] [--reset]

Al terminar escribe local/.env con las credenciales del usuario de la app.
"""
import argparse
import os
import getpass
import secrets
from pathlib import Path

import pymysql
from pymysql.constants import CLIENT

RAIZ = Path(__file__).resolve().parent.parent
ENV = Path(__file__).resolve().parent / ".env"


def _clave_segura(largo: int = 24) -> str:
    """Cumple la política de MySQL HeatWave: mayúsculas, minúsculas, dígitos y símbolos."""
    import string
    simbolos = "#%+-.:=@^_~"
    alfabeto = string.ascii_letters + string.digits + simbolos
    while True:
        c = "".join(secrets.choice(alfabeto) for _ in range(largo))
        if (any(x.islower() for x in c) and any(x.isupper() for x in c)
                and any(x.isdigit() for x in c) and any(x in simbolos for x in c)):
            return c


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--admin", default="root")
    p.add_argument("--db", default="motor_horarios")
    p.add_argument("--usuario", default="motor")
    p.add_argument("--desde", default="localhost", help="host desde el que se conecta la app (p. ej. 10.0.20.%%)")
    p.add_argument("--env", default=str(ENV), help="dónde escribir el .env resultante")
    p.add_argument("--sin-demo", action="store_true", help="no cargar 002_datos_demo.sql")
    p.add_argument("--ssl", action="store_true", help="conectar con TLS (MySQL HeatWave)")
    p.add_argument("--reset", action="store_true", help="borra la base si ya existe")
    a = p.parse_args()

    clave_admin = os.environ.get("MYSQL_ADMIN_PASSWORD") or getpass.getpass(f"Contraseña de {a.admin}@{a.host}:{a.port}: ")
    clave_app = _clave_segura()

    conn = pymysql.connect(host=a.host, port=a.port, user=a.admin, password=clave_admin,
                           client_flag=CLIENT.MULTI_STATEMENTS, autocommit=True,
                           ssl={"check_hostname": False} if a.ssl else None)
    with conn.cursor() as cur:
        cur.execute("SELECT VERSION()")
        print("Conectado a MySQL", cur.fetchone()[0])
        if a.reset:
            cur.execute(f"DROP DATABASE IF EXISTS `{a.db}`")
        cur.execute(f"SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (a.db,))
        if cur.fetchone():
            raise SystemExit(f"La base `{a.db}` ya existe. Usa --reset para recrearla.")
        cur.execute(f"CREATE DATABASE `{a.db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        cur.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (a.usuario, a.desde, clave_app))
        cur.execute("ALTER USER %s@%s IDENTIFIED BY %s", (a.usuario, a.desde, clave_app))
        cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{a.db}`.* TO %s@%s", (a.usuario, a.desde))

        cur.execute(f"USE `{a.db}`")
        scripts = ["001_esquema.sql"] + ([] if a.sin_demo else ["002_datos_demo.sql"])
        for nombre in scripts:
            cur.execute((RAIZ / "db" / nombre).read_text(encoding="utf-8"))
            while cur.nextset():
                pass
            print("Ejecutado", nombre)
    conn.close()

    destino = Path(a.env)
    destino.write_text(
        "# Generado por local/crear_bd.py — no subir a git\n"
        f"DB_MODE=env\nDB_HOST={a.host}\nDB_PORT={a.port}\n"
        f"DB_USER={a.usuario}\nDB_PASSWORD={clave_app}\nDB_NAME={a.db}\n",
        encoding="utf-8",
    )
    print(f"Listo. Credenciales de la app guardadas en {destino}")


if __name__ == "__main__":
    main()
