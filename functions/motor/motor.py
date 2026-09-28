from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from recurrencia import expandir_evento

Bloque = Tuple[datetime, datetime]

# Si un usuario no tiene reglas propias se asume jornada laboral estándar.
REGLAS_POR_DEFECTO = {"no_antes_de": 8, "no_despues_de": 18, "dias_laborables": [0, 1, 2, 3, 4]}


def calcular_huecos(
    usuarios: List[int],
    duracion_min: int,
    ventana_inicio: datetime,
    ventana_fin: datetime,
    reglas: Dict[int, dict],
    eventos: Dict[int, List[dict]],
    max_sugerencias: int = 3,
    paso_min: int = 15,
) -> List[dict]:
    """
    Devuelve hasta `max_sugerencias` huecos que no se solapan entre sí, en los
    que todos los usuarios están libres y dentro de sus reglas.
    Cada hueco: {"inicio", "fin", "score"}; mayor score = mejor.

    `eventos[uid]` es una lista de dicts con inicio, fin, tipo ('ocupado' |
    'preferido') y rrule opcional.
    """
    duracion = timedelta(minutes=duracion_min)
    ocupados: Dict[int, List[Bloque]] = {}
    preferidos: Dict[int, List[Bloque]] = {}
    for uid in usuarios:
        ocupados[uid], preferidos[uid] = [], []
        for ev in eventos.get(uid, []):
            destino = preferidos[uid] if ev.get("tipo") == "preferido" else ocupados[uid]
            destino.extend(expandir_evento(ev, ventana_inicio, ventana_fin))

    candidatos = []
    cursor = _redondear_arriba(ventana_inicio, paso_min)
    while cursor + duracion <= ventana_fin:
        fin = cursor + duracion
        if all(_usuario_libre(uid, cursor, fin, ocupados, reglas) for uid in usuarios):
            score = _calcular_score(cursor, fin, usuarios, preferidos)
            candidatos.append({"inicio": cursor, "fin": fin, "score": score})
        cursor += timedelta(minutes=paso_min)

    # Mejor score primero; a igualdad, el más temprano.
    candidatos.sort(key=lambda c: (-c["score"], c["inicio"]))
    elegidos: List[dict] = []
    for c in candidatos:
        if all(c["fin"] <= e["inicio"] or c["inicio"] >= e["fin"] for e in elegidos):
            elegidos.append(c)
            if len(elegidos) == max_sugerencias:
                break
    return elegidos


def _redondear_arriba(dt: datetime, paso_min: int) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    resto = dt.minute % paso_min
    return dt + timedelta(minutes=paso_min - resto) if resto else dt


def _usuario_libre(uid, inicio: datetime, fin: datetime, ocupados, reglas) -> bool:
    for o_ini, o_fin in ocupados.get(uid, []):
        if inicio < o_fin and fin > o_ini:
            return False
    return _cumple_reglas(inicio, fin, reglas.get(uid) or REGLAS_POR_DEFECTO)


def _cumple_reglas(inicio: datetime, fin: datetime, regla: dict) -> bool:
    if inicio.weekday() not in regla.get("dias_laborables", REGLAS_POR_DEFECTO["dias_laborables"]):
        return False
    ini_min = inicio.hour * 60 + inicio.minute
    fin_min = ini_min + int((fin - inicio).total_seconds() // 60)
    if fin_min > 24 * 60:  # no se permiten reuniones que crucen la medianoche
        return False
    if regla.get("no_antes_de") is not None and ini_min < regla["no_antes_de"] * 60:
        return False
    if regla.get("no_despues_de") is not None and fin_min > regla["no_despues_de"] * 60:
        return False
    return True


def _calcular_score(inicio: datetime, fin: datetime, usuarios, preferidos) -> int:
    score = 100
    if inicio.weekday() == 4:  # viernes
        score -= 20
    if inicio.hour < 10:
        score -= 10
    if inicio.hour >= 16:
        score -= 10
    # +10 por cada participante para quien el hueco cae en un bloque preferido
    for uid in usuarios:
        if any(p_ini <= inicio and fin <= p_fin for p_ini, p_fin in preferidos.get(uid, [])):
            score += 10
    return score
