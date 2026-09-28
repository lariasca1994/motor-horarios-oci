import logging
from datetime import datetime
from typing import List, Tuple

from dateutil.rrule import rrulestr

logger = logging.getLogger(__name__)


def expandir_evento(evento: dict, desde: datetime, hasta: datetime) -> List[Tuple[datetime, datetime]]:
    """
    Devuelve las instancias (inicio, fin) del evento que se solapan con [desde, hasta].
    Si el evento tiene RRULE se expande; si no, se devuelve tal cual (o nada si
    está fuera de la ventana).
    """
    inicio, fin = evento["inicio"], evento["fin"]
    if not evento.get("rrule"):
        return [(inicio, fin)] if inicio < hasta and fin > desde else []
    return expandir_rrule(evento, desde, hasta)


def expandir_rrule(evento: dict, desde: datetime, hasta: datetime) -> List[Tuple[datetime, datetime]]:
    inicio = evento["inicio"]
    duracion = evento["fin"] - inicio
    try:
        regla = rrulestr(evento["rrule"], dtstart=inicio)
        # Se retrocede `duracion` para incluir ocurrencias que empiezan antes
        # de la ventana pero todavía la ocupan.
        ocurrencias = regla.between(desde - duracion, hasta, inc=True)
    except (ValueError, TypeError):
        logger.warning("RRULE inválida en evento %s: %r", evento.get("id"), evento["rrule"])
        return []
    return [(o, o + duracion) for o in ocurrencias if o + duracion > desde and o < hasta]
