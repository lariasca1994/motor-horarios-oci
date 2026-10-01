"""
Correo de sugerencias de horario: HTML con la paleta del frontend
(frontend/css/estilos.css, tema claro) y versión en texto plano.

Estilos en línea y maquetación con tablas: es lo único que respetan todos los
clientes de correo. Todo texto que viene de la base se escapa.
"""
from datetime import datetime
from html import escape
from typing import List, Optional

ACENTO = "#00758f"
ACENTO_SUAVE = "#dff0f4"
FONDO = "#f5f6fa"
SUPERFICIE = "#ffffff"
TEXTO = "#1f2430"
TEXTO_SUAVE = "#5a6072"
BORDE = "#dde1ea"
FUENTE = "system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif"

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga(dt: datetime) -> str:
    """'jueves 1 de octubre de 2026' (sin depender del locale del servidor)."""
    return f"{_DIAS[dt.weekday()]} {dt.day} de {_MESES[dt.month - 1]} de {dt.year}"


def _calificacion(score: int):
    """Texto y colores del chip de puntaje (mayor = mejor; parte de 100)."""
    if score >= 100:
        return "Excelente", "#1e7a3a", "#dff5e3"
    if score >= 90:
        return "Muy buena", ACENTO, ACENTO_SUAVE
    return "Buena", "#8a5a00", "#fdf1d6"


def _chip(texto: str, color: str, fondo: str) -> str:
    return (f'<span style="display:inline-block;margin:0 6px 6px 0;padding:3px 10px;'
            f'border-radius:999px;font-size:12px;font-weight:600;color:{color};'
            f'background:{fondo};">{escape(texto)}</span>')


def html_sugerencias(nombre: str, reunion: dict, participantes: List[str], huecos: List[dict],
                     enlace: Optional[str]) -> str:
    titulo = escape(reunion["titulo"])
    duracion = reunion["duracion_min"]

    ficha = [
        ("Reunión", reunion["titulo"]),
        ("Duración", f"{duracion} minutos"),
        ("Ventana de búsqueda",
         f"{fecha_larga(reunion['ventana_inicio'])} {reunion['ventana_inicio']:%H:%M} – "
         f"{fecha_larga(reunion['ventana_fin'])} {reunion['ventana_fin']:%H:%M}"),
        ("Participantes", ", ".join(participantes)),
    ]
    filas = "".join(
        f'<tr><td style="{"" if i == 0 else f"border-top:1px solid {BORDE};"}padding:10px 14px;'
        f'width:36%;font-size:13px;color:{TEXTO_SUAVE};vertical-align:top;">{escape(campo)}</td>'
        f'<td style="{"" if i == 0 else f"border-top:1px solid {BORDE};"}padding:10px 14px;'
        f'font-size:14px;font-weight:600;color:{TEXTO};vertical-align:top;">{escape(valor)}</td></tr>'
        for i, (campo, valor) in enumerate(ficha)
    )

    if huecos:
        opciones = ""
        for i, h in enumerate(huecos, 1):
            calif, color, fondo = _calificacion(h["score"])
            recomendada = (' &nbsp;<span style="font-size:12px;font-weight:600;color:#ffffff;'
                           f'background:{ACENTO};padding:2px 8px;border-radius:999px;">Recomendada</span>'
                           if i == 1 else "")
            opciones += f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDE};border-left:4px solid {ACENTO if i == 1 else BORDE};border-radius:10px;margin-bottom:10px;">
<tr><td style="padding:12px 16px;">
  <div style="font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:{TEXTO_SUAVE};">Opción {i}{recomendada}</div>
  <div style="font-size:16px;font-weight:700;color:{TEXTO};margin-top:6px;">{escape(fecha_larga(h['inicio']).capitalize())}</div>
  <div style="font-size:15px;color:{TEXTO};margin-top:2px;">{h['inicio']:%H:%M} – {h['fin']:%H:%M} <span style="color:{TEXTO_SUAVE};font-size:13px;">(hora Bogotá)</span></div>
  <div style="margin-top:8px;">{_chip(f"{calif} · puntaje {h['score']}", color, fondo)}</div>
</td></tr></table>"""
        resumen = (f"Encontramos <strong>{len(huecos)}</strong> "
                   f"{'horario' if len(huecos) == 1 else 'horarios'} en {'el' if len(huecos) == 1 else 'los'} "
                   "que todos los participantes están libres. La primera opción es la mejor según "
                   "el día, la hora y las preferencias de cada uno.")
    else:
        opciones = (f'<div style="background:#fdf1d6;border-left:4px solid #c98a00;border-radius:8px;'
                    f'padding:14px 16px;font-size:14px;line-height:1.55;color:{TEXTO};">'
                    "No hay ningún horario en el que todos estén libres dentro de la ventana indicada. "
                    "Prueba ampliando la ventana de búsqueda o revisando la agenda de los participantes."
                    "</div>")
        resumen = "Revisamos la agenda de todos los participantes para esta reunión."

    boton = ("" if not enlace else
             f'<tr><td style="padding:8px 28px 8px;"><a href="{escape(enlace)}" '
             f'style="display:inline-block;background:{ACENTO};color:#ffffff;text-decoration:none;'
             f'font-weight:600;font-size:14px;padding:10px 22px;border-radius:8px;">'
             "Ver la reunión y confirmar</a></td></tr>")

    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{titulo}</title></head>
<body style="margin:0;padding:0;background:{FONDO};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{FONDO};padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:{SUPERFICIE};border:1px solid {BORDE};border-radius:10px;overflow:hidden;font-family:{FUENTE};color:{TEXTO};">
<tr><td style="background:{ACENTO};padding:18px 28px;">
  <div style="font-size:13px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#cdeef5;">Motor de Horarios</div>
  <div style="font-size:15px;color:#ffffff;margin-top:2px;">Sugerencias de horario para tu reunión</div>
</td></tr>
<tr><td style="padding:24px 28px 6px;">
  <p style="margin:0 0 10px;font-size:15px;">Hola {escape(nombre)},</p>
  <h1 style="margin:0 0 10px;font-size:20px;line-height:1.35;color:{TEXTO};">{titulo}</h1>
  <div>{_chip(f"{duracion} min", ACENTO, ACENTO_SUAVE)}{_chip(f"{len(participantes)} participantes", ACENTO, ACENTO_SUAVE)}{_chip(f"{len(huecos)} opciones" if len(huecos) != 1 else "1 opción", ACENTO, ACENTO_SUAVE)}</div>
  <p style="margin:8px 0 0;font-size:14px;line-height:1.55;color:{TEXTO_SUAVE};">{resumen}</p>
</td></tr>
<tr><td style="padding:16px 28px 4px;">
  <div style="font-size:13px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:{ACENTO};margin-bottom:10px;">Horarios sugeridos</div>
  {opciones}
</td></tr>
<tr><td style="padding:12px 28px 4px;">
  <div style="font-size:13px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:{ACENTO};margin-bottom:10px;">Detalle de la reunión</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDE};border-radius:10px;border-collapse:separate;">{filas}</table>
</td></tr>
{boton}
<tr><td style="padding:20px 28px 22px;border-top:1px solid {BORDE};font-size:12px;line-height:1.5;color:{TEXTO_SUAVE};">
  Aviso automático del Motor de Horarios. Cada participante recibe su propio correo; nadie ve la dirección de los demás.
</td></tr>
</table>
</td></tr></table>
</body></html>"""


def texto_sugerencias(nombre: str, reunion: dict, participantes: List[str], huecos: List[dict],
                      enlace: Optional[str]) -> str:
    lineas = [
        f"Hola {nombre},", "",
        f"Sugerencias de horario para: {reunion['titulo']}",
        f"Duración: {reunion['duracion_min']} minutos",
        f"Participantes: {', '.join(participantes)}", "",
    ]
    if not huecos:
        lineas.append("No hay ningún horario en el que todos estén libres dentro de la ventana indicada.")
    for i, h in enumerate(huecos, 1):
        calif, _, _ = _calificacion(h["score"])
        lineas.append(f"Opción {i}{' (recomendada)' if i == 1 else ''}: {fecha_larga(h['inicio'])}, "
                      f"{h['inicio']:%H:%M} – {h['fin']:%H:%M} (hora Bogotá) · {calif}, puntaje {h['score']}")
    if enlace:
        lineas += ["", f"Ver la reunión y confirmar: {enlace}"]
    return "\n".join(lineas)
