"""
Autenticación: contraseñas con scrypt y tokens firmados con HMAC-SHA256.

AUTH_SECRET       clave para firmar tokens (obligatoria en producción; debe ser la
                  misma en todos los workers).
AUTH_TTL_HORAS    duración de la sesión (12 h por defecto).
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import conexion

logger = logging.getLogger(__name__)

_N, _R, _P = 2 ** 14, 8, 1
_SECRETO = os.environ.get("AUTH_SECRET") or ""
if not _SECRETO:
    logger.warning("AUTH_SECRET no definido: se usa uno aleatorio (las sesiones no sobreviven reinicios)")
    _SECRETO = secrets.token_urlsafe(32)
_TTL = int(os.environ.get("AUTH_TTL_HORAS", "12")) * 3600


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---------------------------------------------------------------- contraseñas

def hash_clave(clave: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.scrypt(clave.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64e(sal)}${_b64e(dk)}"


def verificar_clave(clave: str, guardado: str | None) -> bool:
    if not guardado:
        return False
    try:
        alg, n, r, p, sal, dk = guardado.split("$")
        if alg != "scrypt":
            return False
        calc = hashlib.scrypt(clave.encode(), salt=_b64d(sal), n=int(n), r=int(r), p=int(p),
                              dklen=len(_b64d(dk)))
        return hmac.compare_digest(calc, _b64d(dk))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- tokens

def crear_token(usuario_id: int) -> str:
    cuerpo = _b64e(json.dumps({"sub": usuario_id, "exp": int(time.time()) + _TTL}).encode())
    firma = _b64e(hmac.new(_SECRETO.encode(), cuerpo.encode(), hashlib.sha256).digest())
    return f"{cuerpo}.{firma}"


def leer_token(token: str) -> int | None:
    try:
        cuerpo, firma = token.split(".")
        esperada = _b64e(hmac.new(_SECRETO.encode(), cuerpo.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(firma, esperada):
            return None
        datos = json.loads(_b64d(cuerpo))
        return int(datos["sub"]) if datos["exp"] > time.time() else None
    except (ValueError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------- freno a fuerza bruta

_INTENTOS: dict[str, list[float]] = {}
_LOCK = threading.Lock()
_MAX_FALLOS, _VENTANA = 5, 15 * 60


def bloqueado(email: str) -> bool:
    ahora = time.time()
    with _LOCK:
        fallos = [t for t in _INTENTOS.get(email, []) if ahora - t < _VENTANA]
        _INTENTOS[email] = fallos
        return len(fallos) >= _MAX_FALLOS


def registrar_fallo(email: str):
    with _LOCK:
        _INTENTOS.setdefault(email, []).append(time.time())


def limpiar_fallos(email: str):
    with _LOCK:
        _INTENTOS.pop(email, None)


# ---------------------------------------------------------------- dependencias FastAPI

_bearer = HTTPBearer(auto_error=False)


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    usuario_id = leer_token(cred.credentials) if cred else None
    if usuario_id is None:
        raise HTTPException(status_code=401, detail="sesión inválida o vencida",
                            headers={"WWW-Authenticate": "Bearer"})
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, nombre, email, rol, activo FROM usuarios WHERE id = %s", (usuario_id,))
        u = cur.fetchone()
    if not u or not u["activo"]:
        raise HTTPException(status_code=401, detail="cuenta inexistente o desactivada")
    return u


def solo_admin(u: dict = Depends(usuario_actual)) -> dict:
    if u["rol"] != "admin":
        raise HTTPException(status_code=403, detail="solo administradores")
    return u
