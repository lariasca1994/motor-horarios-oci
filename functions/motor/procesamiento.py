"""
Lógica del motor: calcula los huecos de una reunión, los guarda en `sugerencias`
y envía un correo a cada persona de la reunión.

La usan func.py (OCI Functions), local_server.py (servicio HTTP) y la API
directamente cuando MOTOR_MODE=inproceso (p. ej. en Render).
"""
import logging
import os

from db import conexion
from motor import calcular_huecos
from notificaciones import enviar_correos
from plantilla_correo import html_sugerencias, texto_sugerencias

logger = logging.getLogger(__name__)


def procesar_reunion(reunion_id: int) -> dict:
    with conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, titulo, duracion_min, ventana_inicio, ventana_fin, estado, organizador_id "
            "FROM reuniones WHERE id = %s FOR UPDATE",
            (reunion_id,),
        )
        reunion = cur.fetchone()
        if not reunion:
            return {"status": "error", "mensaje": "reunión no encontrada"}
        if reunion["estado"] in ("confirmada", "cancelada"):
            return {"status": "omitida", "mensaje": f"reunión {reunion['estado']}"}

        cur.execute("SELECT usuario_id FROM reunion_participantes WHERE reunion_id = %s",
                    (reunion_id,))
        usuarios = [r["usuario_id"] for r in cur.fetchall()]
        if not usuarios:
            return {"status": "error", "mensaje": "la reunión no tiene participantes"}

        reglas = _cargar_reglas(cur, usuarios)
        eventos = _cargar_eventos(cur, usuarios, reunion["ventana_inicio"], reunion["ventana_fin"])

        huecos = calcular_huecos(
            usuarios=usuarios,
            duracion_min=reunion["duracion_min"],
            ventana_inicio=reunion["ventana_inicio"],
            ventana_fin=reunion["ventana_fin"],
            reglas=reglas,
            eventos=eventos,
        )

        cur.execute("DELETE FROM sugerencias WHERE reunion_id = %s", (reunion_id,))
        if huecos:
            cur.executemany(
                "INSERT INTO sugerencias (reunion_id, inicio, fin, score) VALUES (%s, %s, %s, %s)",
                [(reunion_id, h["inicio"], h["fin"], h["score"]) for h in huecos],
            )
        estado = "con_sugerencias" if huecos else "sin_huecos"
        cur.execute("UPDATE reuniones SET estado = %s WHERE id = %s", (estado, reunion_id))
        conn.commit()

        cur.execute("SELECT nombre, email FROM usuarios WHERE id IN %s ORDER BY nombre", (usuarios,))
        personas = [(r["nombre"], r["email"]) for r in cur.fetchall()]

        cur.execute("SELECT nombre, email FROM usuarios WHERE id = %s", (reunion["organizador_id"],))
        fila = cur.fetchone()
        organizador = (fila["nombre"], fila["email"]) if fila else None

    enviados = 0
    try:
        nombres = [n for n, _ in personas]
        enlace = _enlace_reuniones()
        enviados = enviar_correos(
            personas,
            asunto=f"Horarios sugeridos · {reunion['titulo']}",
            cuerpo=lambda nombre: (
                texto_sugerencias(nombre, reunion, nombres, huecos, enlace),
                html_sugerencias(nombre, reunion, nombres, huecos, enlace),
            ),
            organizador=organizador,
        )
    except Exception:
        logger.exception("Falló el envío de correos de la reunión %s", reunion_id)

    return {"status": estado, "huecos": len(huecos), "correos": enviados}


def _cargar_reglas(cur, usuarios) -> dict:
    cur.execute("SELECT usuario_id, no_antes_de, no_despues_de, dias_laborables "
                "FROM reglas_usuario WHERE usuario_id IN %s", (usuarios,))
    return {
        r["usuario_id"]: {
            "no_antes_de": r["no_antes_de"],
            "no_despues_de": r["no_despues_de"],
            "dias_laborables": [int(d) for d in r["dias_laborables"].split(",") if d],
        }
        for r in cur.fetchall()
    }


def _cargar_eventos(cur, usuarios, v_ini, v_fin) -> dict:
    # Eventos puntuales que se solapan con la ventana + todos los recurrentes
    # que empezaron antes de que termine la ventana.
    cur.execute(
        "SELECT id, usuario_id, inicio, fin, tipo, rrule FROM disponibilidad "
        "WHERE usuario_id IN %s AND inicio < %s AND (rrule IS NOT NULL OR fin > %s)",
        (usuarios, v_fin, v_ini),
    )
    eventos: dict = {}
    for r in cur.fetchall():
        eventos.setdefault(r["usuario_id"], []).append(r)
    return eventos


def _enlace_reuniones():
    """Página de reuniones del frontend: FRONTEND_URL o, si no, el primer origen de CORS_ORIGINS."""
    base = os.environ.get("FRONTEND_URL", "").strip()
    if not base:
        origenes = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
        base = next((o for o in origenes if o.startswith("http")), "")
    return f"{base.rstrip('/')}/reuniones.html" if base else None
