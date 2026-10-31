"""Registro de eventos de seguridad de las cuentas.

Guarda qué pasó y cuándo; nunca contraseñas, códigos ni datos del equipo. Los eventos
viven en la propia cuenta (columna mfa), porque el usuario de la app no puede crear
tablas, a propósito. Se conservan 15 días y como máximo los últimos 50.
Si la base no responde, el evento se pierde pero el ingreso sigue: la auditoría
nunca bloquea al usuario.
"""

import json
import logging
import time

from db import conexion

INGRESO = "ingreso"
CLAVE_ERRADA = "clave_errada"
CODIGO_ERRADO = "codigo_errado"
CUENTA_BLOQUEADA = "cuenta_bloqueada"
CLAVE_CAMBIADA = "clave_cambiada"
RECUPERACION = "recuperacion_solicitada"
METODO_ACTIVADO = "metodo_activado"

RETENCION_DIAS = 15
_MAX_EVENTOS = 50


def registrar(tipo: str, usuario: dict) -> None:
    ahora = int(time.time())
    estado = dict(usuario.get("mfa") or {})
    vigentes = [e for e in estado.get("eventos", []) if ahora - e.get("fecha", 0) < RETENCION_DIAS * 86400]
    estado["eventos"] = (vigentes + [{"tipo": tipo, "fecha": ahora}])[-_MAX_EVENTOS:]
    usuario["mfa"] = estado
    try:
        with conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET mfa = %s WHERE id = %s", (json.dumps(estado), usuario["id"]))
            conn.commit()
    except Exception:  # noqa: BLE001 - la auditoría no debe tumbar el ingreso
        logging.warning("No se pudo registrar el evento de seguridad %s", tipo)
