"""Recuperación de acceso: "Olvidé mi contraseña", "Perdí mi autenticador" y nombre visible."""
import time
from datetime import datetime

import pytest

import auth
import mfa

NOMBRE = "Coordinador de reuniones"


def _codigo_app(secreto: str, desfase: int = 0) -> str:
    return mfa._totp(secreto, int(time.time()) // 30 + desfase)


def _codigo_del_correo(texto: str) -> str:
    return next(p for p in texto.replace(".", " ").split() if p.isdigit() and len(p) == 6)


# ─────────────────────────── perdí mi autenticador ───────────────────────────


def test_codigo_al_correo_aunque_el_metodo_correo_no_este_activo(usuario, correos):
    assert "correo" not in mfa.metodos_activos(usuario)
    assert mfa.enviar_codigo(usuario, recuperacion=True)
    (destinatarios, asunto, texto, html), = correos
    assert destinatarios == [("Ana Pérez", "usuario@ejemplo.com")]
    assert NOMBRE in asunto and texto.startswith(NOMBRE) and texto.rstrip().endswith(NOMBRE)
    assert NOMBRE in html
    guardado = usuario["mfa"]["codigo_recuperar"]
    assert 14 * 60 < guardado["expira"] - time.time() <= 15 * 60
    assert "codigo" not in usuario["mfa"]  # no toca el código del método correo


def test_limite_de_envios(usuario, correos):
    assert all(mfa.enviar_codigo(usuario, recuperacion=True) for _ in range(3))
    assert not mfa.enviar_codigo(usuario, recuperacion=True)
    assert len(correos) == 3


def test_codigo_correcto_no_abre_sesion_y_obliga_a_configurar_app_nueva(usuario, correos):
    secreto_viejo = usuario["_secreto"]
    totp_viejo = usuario["mfa"]["totp"]
    mfa.enviar_codigo(usuario, recuperacion=True)
    codigo = _codigo_del_correo(correos[-1][2])

    assert not mfa.puede_reponer(usuario)
    assert not mfa.activar_reposicion(usuario, "123456")  # sin el código del correo no se puede
    assert mfa.verificar_recuperacion(usuario, codigo)
    assert mfa.puede_reponer(usuario)
    assert not mfa.verificar_recuperacion(usuario, codigo)  # un solo uso

    secreto_nuevo = mfa.iniciar_totp(usuario)["secreto"]
    assert usuario["mfa"]["totp"] == totp_viejo  # la app vieja sigue hasta activar la nueva
    assert mfa.activar_reposicion(usuario, _codigo_app(secreto_nuevo))
    assert usuario["mfa"]["totp"] != totp_viejo
    assert not mfa.puede_reponer(usuario)
    assert mfa.metodos_activos(usuario) == ["totp"]
    # La app perdida deja de servir; la nueva sí.
    assert not mfa.verificar(usuario, "totp", _codigo_app(secreto_viejo, 1))
    assert mfa.verificar(usuario, "totp", _codigo_app(secreto_nuevo, 1))


def test_codigo_vencido(usuario, correos, monkeypatch):
    mfa.enviar_codigo(usuario, recuperacion=True)
    codigo = _codigo_del_correo(correos[-1][2])
    ahora = time.time()
    monkeypatch.setattr(mfa.time, "time", lambda: ahora + 15 * 60 + 1)
    assert not mfa.verificar_recuperacion(usuario, codigo)


def test_cinco_errados_bloquean_quince_minutos(usuario, correos, monkeypatch):
    mfa.enviar_codigo(usuario, recuperacion=True)
    codigo = _codigo_del_correo(correos[-1][2])
    errado = f"{(int(codigo) + 1) % 1_000_000:06d}"
    for _ in range(5):
        assert not mfa.verificar_recuperacion(usuario, errado)
    assert mfa.bloqueado(usuario)
    # Bloqueo compartido con la app: ni el código correcto ni la app sirven mientras dura.
    mfa.enviar_codigo(usuario, recuperacion=True)
    assert not mfa.verificar_recuperacion(usuario, _codigo_del_correo(correos[-1][2]))
    assert not mfa.verificar(usuario, "totp", _codigo_app(usuario["_secreto"]))
    ahora = time.time()
    monkeypatch.setattr(mfa.time, "time", lambda: ahora + 15 * 60 + 1)
    assert not mfa.bloqueado(usuario)


# ─────────────────────────── olvidé mi contraseña ───────────────────────────


def test_restablecer_cierra_sesiones_y_mantiene_dos_pasos(usuario):
    vieja = auth.leer_sesion(auth.crear_token(usuario["id"]))
    activos = mfa.metodos_activos(usuario)
    time.sleep(0.01)
    mfa.clave_restablecida(usuario, cerrar_sesiones=True)
    assert not auth.sesion_vigente(vieja[1], usuario["mfa"])
    time.sleep(0.01)
    nueva = auth.leer_sesion(auth.crear_token(usuario["id"]))
    assert auth.sesion_vigente(nueva[1], usuario["mfa"])
    assert mfa.metodos_activos(usuario) == activos == ["totp"]


def test_cambio_de_clave_desde_el_perfil_no_cierra_la_sesion(usuario):
    actual = auth.leer_sesion(auth.crear_token(usuario["id"]))
    mfa.clave_restablecida(usuario)
    assert auth.sesion_vigente(actual[1], usuario["mfa"])


def test_enlace_de_recuperacion_es_de_un_solo_uso():
    token = auth.crear_token_recuperacion(3, "hash-viejo")
    usuario_id, huella = auth.leer_token_recuperacion(token)
    assert usuario_id == 3 and auth.huella_coincide("hash-viejo", huella)
    assert not auth.huella_coincide("hash-nuevo", huella)  # tras cambiarla ya no sirve
    assert auth.leer_token(token) is None  # no sirve como sesión


# ─────────────────────────── API ───────────────────────────


@pytest.fixture
def cliente(usuario, monkeypatch):
    from fastapi.testclient import TestClient

    import main

    monkeypatch.setattr(mfa, "cargar", lambda _id: usuario)
    return TestClient(main.app)


def test_api_perdi_mi_autenticador(cliente, usuario, correos):
    pase = auth.crear_pase_mfa(usuario["id"])
    r = cliente.post("/auth/mfa/recuperar/activar", json={"pase": pase, "codigo": "123456"})
    assert r.status_code == 403
    r = cliente.post("/auth/mfa/recuperar", json={"pase": pase})
    assert r.status_code == 202 and auth.leer_pase_mfa(r.json()["pase"]) == usuario["id"]
    r = cliente.post("/auth/mfa/recuperar/verificar",
                     json={"pase": pase, "codigo": _codigo_del_correo(correos[-1][2])})
    assert r.status_code == 200
    datos = r.json()
    assert "token" not in datos and datos["qr"].startswith("<svg")
    r = cliente.post("/auth/mfa/recuperar/activar",
                     json={"pase": datos["pase"], "codigo": _codigo_app(datos["secreto"])})
    assert r.status_code == 200 and auth.leer_token(r.json()["token"]) == usuario["id"]


def test_api_sesion_cerrada_tras_restablecer(cliente, usuario, bd):
    token = auth.crear_token(usuario["id"])
    fila = {k: usuario[k] for k in ("id", "nombre", "email", "rol", "activo")}
    bd.append({**fila, "mfa": {}})
    assert cliente.get("/auth/yo", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    bd.append({**fila, "mfa": {"sesiones_desde": time.time() + 1}})
    assert cliente.get("/auth/yo", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ─────────────────────────── nombre visible ───────────────────────────


def test_emisor_del_qr(usuario, monkeypatch):
    uris = []
    real = mfa.segno.make
    monkeypatch.setattr(mfa.segno, "make", lambda uri, **kw: uris.append(uri) or real(uri, **kw))
    mfa.iniciar_totp(usuario)
    assert "issuer=Coordinador%20de%20reuniones" in uris[0]
    assert uris[0].startswith("otpauth://totp/Coordinador%20de%20reuniones:")
    assert mfa._ETIQUETA_CLAVE == b"MotorHorarios.MFA.v1"  # la clave interna no cambia


def test_correos_con_el_nombre_visible(usuario, correos):
    import main
    from plantilla_correo import html_sugerencias, telegram_sugerencias

    mfa.enviar_codigo(usuario)
    asunto, texto, html = correos[-1][1:]
    assert NOMBRE in asunto and texto.startswith(NOMBRE) and texto.rstrip().endswith(NOMBRE)
    assert html.startswith(f'<p style="font-weight:700;color:#00758F">{NOMBRE}')

    texto, html = main._correo_recuperacion("Ana <b>", "https://ejemplo.com/restablecer#x")
    assert texto.startswith(NOMBRE) and texto.rstrip().endswith(NOMBRE)
    assert NOMBRE in html and "Ana &lt;b&gt;" in html and "Motor de Horarios" not in texto + html

    reunion = {"titulo": "Revisión", "duracion_min": 30, "ventana_inicio": datetime(2026, 11, 9, 8),
               "ventana_fin": datetime(2026, 11, 10, 18)}
    hueco = [{"inicio": datetime(2026, 11, 9, 9), "fin": datetime(2026, 11, 9, 9, 30), "score": 100}]
    html = html_sugerencias("Ana", reunion, ["Ana"], hueco, None)
    assert html.count(NOMBRE) == 2 and "Motor de Horarios" not in html
    assert NOMBRE in telegram_sugerencias(reunion, ("Ana", "a@ejemplo.com"), ["Ana"], hueco)


def test_asunto_del_correo_de_sugerencias():
    from pathlib import Path

    fuente = Path(__file__).resolve().parents[1] / "functions" / "motor" / "procesamiento.py"
    assert 'asunto=f"Horarios sugeridos · {reunion[\'titulo\']} · {NOMBRE}"' in fuente.read_text(encoding="utf-8")
