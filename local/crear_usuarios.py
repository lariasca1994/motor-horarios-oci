"""
Crea (o actualiza) las cuentas iniciales. Lee líneas "email|contraseña|rol|nombre"
desde un archivo o desde stdin; ignora líneas vacías y comentarios (#).

    python local/crear_usuarios.py deploy/.usuarios_iniciales
    ... | python local/crear_usuarios.py -

Usa la misma conexión que la API (variables DB_MODE, DB_HOST, ... o Vault).
Si la cuenta ya existe actualiza nombre y rol, pero NO cambia su contraseña
(salvo con --forzar-clave), para no pisar contraseñas ya cambiadas por la persona.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "functions" / "api"))

from auth import hash_clave  # noqa: E402
from db import conexion  # noqa: E402


def leer_cuentas(origen: str):
    texto = sys.stdin.read() if origen == "-" else Path(origen).read_text(encoding="utf-8")
    for n, linea in enumerate(texto.splitlines(), 1):
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        partes = linea.split("|")
        if len(partes) != 4 or partes[2] not in ("admin", "usuario") or len(partes[1]) < 10:
            raise SystemExit(f"Línea {n} inválida (formato email|clave(>=10)|admin/usuario|nombre)")
        email, clave, rol, nombre = (p.strip() for p in partes)
        yield email.lower(), clave, rol, nombre


def main():
    p = argparse.ArgumentParser()
    p.add_argument("origen", help="archivo o '-' para stdin")
    p.add_argument("--forzar-clave", action="store_true", help="reescribe la contraseña aunque ya exista")
    a = p.parse_args()

    with conexion() as conn, conn.cursor() as cur:
        for email, clave, rol, nombre in leer_cuentas(a.origen):
            cur.execute("SELECT id, password_hash FROM usuarios WHERE email = %s", (email,))
            fila = cur.fetchone()
            if fila is None:
                cur.execute("INSERT INTO usuarios (nombre, email, rol, password_hash) VALUES (%s, %s, %s, %s)",
                            (nombre, email, rol, hash_clave(clave)))
                cur.execute("INSERT INTO reglas_usuario (usuario_id, no_antes_de, no_despues_de) "
                            "VALUES (%s, 8, 18)", (cur.lastrowid,))
                print(f"creada      {email} ({rol})")
            else:
                cur.execute("UPDATE usuarios SET nombre = %s, rol = %s, activo = TRUE WHERE id = %s",
                            (nombre, rol, fila["id"]))
                if a.forzar_clave or not fila["password_hash"]:
                    cur.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s",
                                (hash_clave(clave), fila["id"]))
                    print(f"actualizada {email} ({rol}, contraseña reescrita)")
                else:
                    print(f"actualizada {email} ({rol}, contraseña sin cambios)")
        conn.commit()


if __name__ == "__main__":
    main()
