"""Pruebas sin base de datos: la conexión a MySQL se reemplaza por una falsa en memoria."""
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "functions" / "api"), str(RAIZ / "functions" / "motor")]
os.environ.setdefault("AUTH_SECRET", "secreto-solo-para-pruebas")
os.environ["EMAIL_MODE"] = "log"


class _CursorFalso:
    def __init__(self, filas):
        self._filas = filas

    def execute(self, *_args, **_kwargs):
        pass

    def fetchone(self):
        return self._filas.pop(0) if self._filas else None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _ConexionFalsa:
    def __init__(self, filas):
        self._filas = filas

    def cursor(self):
        return _CursorFalso(self._filas)

    def commit(self):
        pass


@pytest.fixture
def bd(monkeypatch):
    """Lista de filas que devolverán los SELECT; los UPDATE no hacen nada."""
    import auditoria
    import auth
    import mfa

    filas = []

    @contextmanager
    def conexion():
        yield _ConexionFalsa(filas)

    for modulo in (mfa, auditoria, auth):
        monkeypatch.setattr(modulo, "conexion", conexion)
    return filas


@pytest.fixture
def correos(monkeypatch):
    """Captura los correos en vez de enviarlos: lista de (destinatarios, asunto, texto, html)."""
    import notificaciones

    enviados = []

    def enviar(destinatarios, asunto, cuerpo, organizador=None):
        destinatarios = list(destinatarios)
        texto, html = cuerpo(destinatarios[0][0])
        enviados.append((destinatarios, asunto, texto, html))
        return len(destinatarios)

    monkeypatch.setattr(notificaciones, "enviar_correos", enviar)
    return enviados


@pytest.fixture
def usuario(bd):
    """Cuenta con solo la app autenticadora activa (sin el método correo)."""
    import mfa

    u = {"id": 7, "nombre": "Ana Pérez", "email": "usuario@ejemplo.com", "rol": "usuario",
         "activo": True, "mfa": {}}
    secreto = mfa.iniciar_totp(u)["secreto"]
    u["mfa"].update({"totp": u["mfa"]["totp_pendiente"], "totp_pendiente": None, "preferido": "totp"})
    u["_secreto"] = secreto
    return u
