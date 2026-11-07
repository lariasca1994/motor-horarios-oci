"""Verificacion en dos pasos (obligatoria).

Cada cuenta usa al menos uno de dos metodos y puede tener ambos:

  - App autenticadora (TOTP, RFC 6238): codigo de 6 digitos que cambia cada
    30 s. El secreto se guarda cifrado con AES-GCM; la clave se deriva del
    AUTH_SECRET con HKDF, asi que un volcado de la base no basta para
    generar codigos. Un mismo codigo no se acepta dos veces.
  - Codigo por correo: 6 digitos de un solo uso que vencen en 10 minutos.
    Solo se guarda su huella (HMAC) y admite 5 intentos; se pueden pedir
    hasta 3 envios cada 10 minutos. Tras 5 codigos de la app errados, la app
    queda bloqueada 15 minutos.
  - "Perdí mi autenticador": codigo de 6 digitos al correo de la cuenta aunque el
    metodo correo no este activo. Vence en 15 minutos, tiene su propio limite de
    envios y comparte el bloqueo de la app (5 errados -> 15 minutos). Acertarlo no
    abre sesion: solo permite configurar una app autenticadora nueva (QR), y la
    sesion llega al activarla.

Todo vive en la columna JSON "mfa" de la tabla usuarios (MySQL); el usuario se
maneja como diccionario con id, email y mfa.
"""

import base64
import hashlib
import hmac
import html
import json
import logging
import secrets
import struct
import time
from urllib.parse import quote

import segno
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from auth import secreto_mfa
import auditoria
from db import conexion

# Nombre visible (correos y emisor del QR). Cambiarlo no invalida las apps ya configuradas:
# los codigos dependen solo del secreto. La etiqueta interna de la clave (HKDF) NO cambia.
EMISOR = "Coordinador de reuniones"
_ETIQUETA_CLAVE = b"MotorHorarios.MFA.v1"
METODOS = {"totp": "App autenticadora", "correo": "Código por correo"}
_PASO = 30
_CODIGO_MINUTOS = 10
_MAX_INTENTOS = 5
_MAX_ENVIOS = 3
_BLOQUEO_SEG = 15 * 60  # tras 5 códigos de la app errados
_RECUPERAR_MINUTOS = 15  # código de "Perdí mi autenticador"

_clave = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_ETIQUETA_CLAVE).derive(
    secreto_mfa()
)


# ─────────────────────────────── utilidades ───────────────────────────────


def _cifrar(texto: str) -> str:
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + AESGCM(_clave).encrypt(nonce, texto.encode(), None)).decode()


def _descifrar(valor: str) -> str:
    datos = base64.b64decode(valor)
    return AESGCM(_clave).decrypt(datos[:12], datos[12:], None).decode()


def _huella(codigo: str) -> str:
    return hmac.new(_clave, codigo.encode(), hashlib.sha256).hexdigest()


def _totp(secreto: str, paso: int) -> str:
    clave = base64.b32decode(secreto + "=" * (-len(secreto) % 8))
    resumen = hmac.new(clave, struct.pack(">Q", paso), hashlib.sha1).digest()
    desfase = resumen[-1] & 0x0F
    numero = struct.unpack(">I", resumen[desfase:desfase + 4])[0] & 0x7FFFFFFF
    return f"{numero % 1_000_000:06d}"


def _limpiar(codigo: str) -> str:
    return "".join(c for c in (codigo or "") if c.isdigit())


def estado(usuario) -> dict:
    return dict(usuario.get("mfa") or {})


def metodos_activos(usuario) -> list[str]:
    m = estado(usuario)
    return [x for x in ("totp", "correo") if (x == "totp" and m.get("totp")) or (x == "correo" and m.get("correo"))]


def configurado(usuario) -> bool:
    return bool(metodos_activos(usuario))


def preferido(usuario) -> str | None:
    activos = metodos_activos(usuario)
    elegido = estado(usuario).get("preferido")
    return elegido if elegido in activos else (activos[0] if activos else None)


def _guardar(usuario, cambios: dict) -> None:
    usuario["mfa"] = {**estado(usuario), **cambios}
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE usuarios SET mfa = %s WHERE id = %s", (json.dumps(usuario["mfa"]), usuario["id"]))
        conn.commit()


def cargar(usuario_id: int) -> dict | None:
    """Usuario como diccionario (id, nombre, email, rol, activo, password_hash, mfa).
    La columna mfa la crea la migración db/004_verificacion_dos_pasos.sql (el usuario de la
    app no tiene permiso para alterar tablas, a propósito)."""
    with conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, nombre, email, rol, activo, password_hash, mfa FROM usuarios WHERE id = %s",
                    (usuario_id,))
        u = cur.fetchone()
    if not u:
        return None
    mfa = u.get("mfa")
    u["mfa"] = json.loads(mfa) if isinstance(mfa, (str, bytes)) else (mfa or {})
    return u

# ──────────────────────────── app autenticadora ───────────────────────────


def iniciar_totp(usuario) -> dict:
    """Genera un secreto pendiente y devuelve lo necesario para escanearlo."""
    secreto = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    _guardar(usuario, {"totp_pendiente": _cifrar(secreto)})
    uri = (
        f"otpauth://totp/{quote(EMISOR)}:{quote(usuario["email"])}"
        f"?secret={secreto}&issuer={quote(EMISOR)}&digits=6&period={_PASO}"
    )
    return {"qr": segno.make(uri, error="m").svg_inline(scale=5, dark="#0f172a", light="#ffffff"), "secreto": secreto}


def _verificar_totp(usuario, secreto_cifrado: str | None, codigo: str) -> bool:
    if not secreto_cifrado or len(codigo) != 6:
        return False
    secreto = _descifrar(secreto_cifrado)
    actual = int(time.time()) // _PASO
    ultimo = estado(usuario).get("ultimo_paso", 0)
    for paso in (actual - 1, actual, actual + 1):
        if paso > ultimo and hmac.compare_digest(_totp(secreto, paso), codigo):
            _guardar(usuario, {"ultimo_paso": paso})
            return True
    return False


def _activar_totp(usuario, codigo: str) -> bool:
    pendiente = estado(usuario).get("totp_pendiente")
    if not _verificar_totp(usuario, pendiente, _limpiar(codigo)):
        return False
    cambios = {"totp": pendiente, "totp_pendiente": None}
    if not configurado(usuario):
        cambios["preferido"] = "totp"
    _guardar(usuario, cambios)
    return True


# ──────────────────────────── codigo por correo ───────────────────────────


def _correo_codigo(codigo: str, minutos: int, recuperacion: bool):
    if recuperacion:
        motivo = "Pediste recuperar el acceso porque perdiste tu app autenticadora. Tu código es:"
        cierre = ("Al usarlo tendrás que configurar una app autenticadora nueva. Si no fuiste tú, "
                  "cambia tu contraseña.")
    else:
        motivo = f"Tu código de verificación de {EMISOR} es:"
        cierre = "Si no intentaste ingresar, cambia tu contraseña."
    vence = f"Vence en {minutos} minutos y sirve una sola vez."

    def contenido(nombre: str):
        texto = (f"{EMISOR}\n\nHola {nombre},\n\n{motivo} {codigo}\n\n{vence} {cierre}\n\n"
                 f"— {EMISOR}")
        cuerpo = (f'<p style="font-weight:700;color:#00758F">{EMISOR}</p>'
                  f"<p>Hola {html.escape(nombre)},</p><p>{motivo}</p>"
                  f'<p style="font-size:28px;font-weight:700;letter-spacing:6px">{codigo}</p>'
                  f"<p>{vence} {cierre}</p>"
                  f'<p style="font-size:12px;color:#5a6072">— {EMISOR}</p>')
        return texto, cuerpo
    return contenido


def enviar_codigo(usuario, recuperacion: bool = False) -> bool:
    """Envia un codigo nuevo. False si ya se pidieron demasiados.
    recuperacion=True: codigo de "Perdí mi autenticador" (no exige el metodo correo)."""
    ahora = time.time()
    minutos = _RECUPERAR_MINUTOS if recuperacion else _CODIGO_MINUTOS
    campo, campo_envios = ("codigo_recuperar", "envios_recuperar") if recuperacion else ("codigo", "envios")
    envios = [t for t in estado(usuario).get(campo_envios, []) if ahora - t < minutos * 60]
    if len(envios) >= _MAX_ENVIOS:
        return False
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    _guardar(usuario, {
        campo: {
            "huella": _huella(codigo),
            "expira": ahora + minutos * 60,
            "intentos": 0,
        },
        campo_envios: envios + [ahora],
    })
    asunto = f"Recupera tu acceso · {EMISOR}" if recuperacion else f"Tu código de acceso · {EMISOR}"
    try:
        from notificaciones import enviar_correos
        enviar_correos([(usuario.get("nombre") or "", usuario["email"])], asunto,
                       _correo_codigo(codigo, minutos, recuperacion))
    except Exception:  # el cliente recibe la misma respuesta; el error queda en el log
        logging.exception("No se pudo enviar el código de verificación")
    return True


def _verificar_correo(usuario, codigo: str, campo: str = "codigo") -> bool:
    guardado = estado(usuario).get(campo)
    if not guardado or guardado.get("intentos", 0) >= _MAX_INTENTOS:
        return False
    if guardado["expira"] < time.time():
        return False
    if not hmac.compare_digest(guardado["huella"], _huella(codigo)):
        _guardar(usuario, {campo: {**guardado, "intentos": guardado.get("intentos", 0) + 1}})
        return False
    _guardar(usuario, {campo: None})
    return True


def _activar_correo(usuario, codigo: str) -> bool:
    if not _verificar_correo(usuario, _limpiar(codigo)):
        return False
    cambios = {"correo": True}
    if not configurado(usuario):
        cambios["preferido"] = "correo"
    _guardar(usuario, cambios)
    return True


# ─────────────────────────────── verificacion ──────────────────────────────


def _verificar_metodo(usuario, metodo: str, codigo: str) -> bool:
    """Comprueba el codigo de un metodo ya activo."""
    codigo = _limpiar(codigo)
    if metodo not in metodos_activos(usuario):
        return False
    if metodo == "totp":
        # Sin este freno, con la contraseña bastaría probar códigos hasta acertar.
        if bloqueado(usuario):
            return False
        if _verificar_totp(usuario, estado(usuario).get("totp"), codigo):
            if estado(usuario).get("fallos"):
                _guardar(usuario, {"fallos": 0})
            return True
        _sumar_fallo(usuario)
        return False
    return _verificar_correo(usuario, codigo)


def bloqueado(usuario) -> bool:
    """True mientras dura el bloqueo por 5 códigos errados (app o recuperación)."""
    return estado(usuario).get("bloqueo_hasta", 0) > time.time()


def _sumar_fallo(usuario) -> None:
    fallos = estado(usuario).get("fallos", 0) + 1
    _guardar(usuario, {"fallos": 0, "bloqueo_hasta": time.time() + _BLOQUEO_SEG}
             if fallos >= _MAX_INTENTOS else {"fallos": fallos})


# ─────────────────────────── perdí mi autenticador ───────────────────────────


def _verificar_recuperacion(usuario, codigo: str) -> bool:
    """Código de "Perdí mi autenticador". Si acierta, deja un permiso temporal para
    configurar una app nueva; no abre sesión."""
    if bloqueado(usuario):
        return False
    if _verificar_correo(usuario, _limpiar(codigo), "codigo_recuperar"):
        _guardar(usuario, {"fallos": 0, "reponer_hasta": time.time() + _RECUPERAR_MINUTOS * 60})
        return True
    _sumar_fallo(usuario)
    return False


def puede_reponer(usuario) -> bool:
    return estado(usuario).get("reponer_hasta", 0) > time.time()


def _activar_reposicion(usuario, codigo: str) -> bool:
    """Reemplaza la app autenticadora por la nueva (la del QR recién escaneado)."""
    if not puede_reponer(usuario):
        return False
    pendiente = estado(usuario).get("totp_pendiente")
    if not _verificar_totp(usuario, pendiente, _limpiar(codigo)):
        return False
    cambios = {"totp": pendiente, "totp_pendiente": None, "reponer_hasta": 0}
    if not configurado(usuario):
        cambios["preferido"] = "totp"
    _guardar(usuario, cambios)
    return True


def elegir_preferido(usuario, metodo: str) -> bool:
    if metodo not in metodos_activos(usuario):
        return False
    _guardar(usuario, {"preferido": metodo})
    return True


# ───────────────────── auditoría y bloqueo por contraseña ─────────────────────

_MAX_FALLOS_CLAVE = 5
_BLOQUEO_CLAVE_SEG = 15 * 60
MENSAJE_BLOQUEO = "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo."


def verificar(usuario, metodo: str, codigo: str) -> bool:
    """Comprueba el código de un método ya activo y deja el intento en la auditoría."""
    if _verificar_metodo(usuario, metodo, codigo):
        auditoria.registrar(auditoria.INGRESO, usuario)
        return True
    auditoria.registrar(auditoria.CODIGO_ERRADO, usuario)
    return False


def activar_totp(usuario, codigo: str) -> bool:
    if not _activar_totp(usuario, codigo):
        return False
    auditoria.registrar(auditoria.METODO_ACTIVADO, usuario)
    return True


def verificar_recuperacion(usuario, codigo: str) -> bool:
    if _verificar_recuperacion(usuario, codigo):
        auditoria.registrar(auditoria.AUTENTICADOR_PERDIDO, usuario)
        return True
    auditoria.registrar(auditoria.CODIGO_ERRADO, usuario)
    return False


def activar_reposicion(usuario, codigo: str) -> bool:
    if not _activar_reposicion(usuario, codigo):
        return False
    auditoria.registrar(auditoria.METODO_ACTIVADO, usuario)
    auditoria.registrar(auditoria.INGRESO, usuario)
    return True


def activar_correo(usuario, codigo: str) -> bool:
    if not _activar_correo(usuario, codigo):
        return False
    auditoria.registrar(auditoria.METODO_ACTIVADO, usuario)
    return True


def clave_bloqueada(usuario) -> bool:
    """True si la cuenta está bloqueada por contraseñas erradas seguidas."""
    return estado(usuario).get("bloqueo_clave_hasta", 0) > time.time()


def fallo_de_clave(usuario) -> None:
    """Suma una contraseña errada; la quinta seguida bloquea la cuenta un tiempo."""
    auditoria.registrar(auditoria.CLAVE_ERRADA, usuario)
    fallos = estado(usuario).get("fallos_clave", 0) + 1
    if fallos >= _MAX_FALLOS_CLAVE:
        _guardar(usuario, {"fallos_clave": 0, "bloqueo_clave_hasta": time.time() + _BLOQUEO_CLAVE_SEG})
        auditoria.registrar(auditoria.CUENTA_BLOQUEADA, usuario)
    else:
        _guardar(usuario, {"fallos_clave": fallos})


def clave_correcta(usuario) -> None:
    """La contraseña fue correcta: el contador vuelve a cero."""
    if estado(usuario).get("fallos_clave"):
        _guardar(usuario, {"fallos_clave": 0})


def clave_restablecida(usuario, cerrar_sesiones: bool = False) -> None:
    """Contraseña nueva (recuperación o cambio): se levanta el bloqueo y queda en la auditoría.
    cerrar_sesiones=True (recuperación): toda sesión abierta antes de este momento deja de
    servir. La verificación en dos pasos no se toca: sigue activa con los mismos métodos."""
    cambios = {"fallos_clave": 0, "bloqueo_clave_hasta": 0}
    if cerrar_sesiones:
        cambios["sesiones_desde"] = time.time()
    _guardar(usuario, cambios)
    auditoria.registrar(auditoria.CLAVE_CAMBIADA, usuario)
