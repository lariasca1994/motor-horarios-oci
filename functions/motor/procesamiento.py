"""
Lógica del motor: calcula los huecos de una reunión, los guarda en `sugerencias`
y envía un correo a cada persona de la reunión.

La usan func.py (OCI Functions), local_server.py (servicio HTTP) y la API
directamente cuando MOTOR_MODE=inproceso (p. ej. en Render).
"""
import logging

from db import conexion
from motor import calcular_huecos
from notificaciones import enviar_correos

logger = logging.getLogger(__name__)


def procesar_reunion(reunion_id: int) -> dict:
    with conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, titulo, duracion_min, ventana_inicio, ventana_fin, estado "
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

    enviados = 0
    try:
        enviados = enviar_correos(
            personas,
            asunto=f"Sugerencias para: {reunion['titulo']}",
            cuerpo=_formatear_sugerencias(reunion["titulo"], [n for n, _ in personas], huecos),
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


def _formatear_sugerencias(titulo: str, participantes: list, huecos: list) -> str:
    lineas = [f"Reunión: {titulo}", f"Participantes: {', '.join(participantes)}", ""]
    if not huecos:
        lineas.append("No se encontraron huecos libres para todos en la ventana indicada.")
    for i, h in enumerate(huecos, 1):
        lineas.append(f"Opción {i}: {h['inicio']:%a %d/%m/%Y %H:%M} – {h['fin']:%H:%M} "
                      f"(score {h['score']})")
    return "\n".join(lineas)
