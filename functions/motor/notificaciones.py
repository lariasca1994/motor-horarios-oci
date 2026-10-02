"""
Envío de correos individuales a cada persona de una reunión.

EMAIL_MODE=log  (por defecto, desarrollo) -> solo se escribe en el log.
EMAIL_MODE=brevo_api -> API HTTP de Brevo (BREVO_API_KEY, EMAIL_FROM, EMAIL_FROM_NAME).
CORREOS_COPIA (opcional, separados por coma) -> copia oculta de cada reunión.
    Útil donde los puertos SMTP están bloqueados (Render gratis).
EMAIL_MODE=smtp -> SMTP con STARTTLS (OCI Email Delivery, Gmail, etc.).
    Credenciales: SMTP_SECRET_OCID (secreto JSON en Vault con host, port, user,
    password, from, from_name) o, sin Vault, SMTP_HOST, SMTP_PORT, SMTP_USER,
    SMTP_PASSWORD, EMAIL_FROM y EMAIL_FROM_NAME.
"""
import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import Callable, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

Destinatario = Tuple[str, str]  # (nombre, email)
# Arma el correo de una persona a partir de su nombre: (texto_plano, html).
CuerpoPersonal = Callable[[str], Tuple[str, Optional[str]]]


def _config_smtp() -> dict:
    if os.environ.get("SMTP_SECRET_OCID"):
        from vault import leer_secreto
        s = leer_secreto(os.environ["SMTP_SECRET_OCID"])
        return {"host": s["host"], "port": int(s.get("port", 587)), "user": s["user"],
                "password": s["password"], "from": s["from"],
                "from_name": s.get("from_name", "Motor de Horarios")}
    return {
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ["SMTP_USER"],
        "password": os.environ["SMTP_PASSWORD"],
        "from": os.environ["EMAIL_FROM"],
        "from_name": os.environ.get("EMAIL_FROM_NAME", "Motor de Horarios"),
    }


def _copia_oculta(destinatarios) -> list:
    """
    Cuentas de CORREOS_COPIA (separadas por coma) que reciben copia oculta de
    cada envío, sin repetir a quien ya es destinatario. Va solo en el correo
    del primer participante: una copia por reunión, no una por persona.
    """
    ya = {email.strip().lower() for _, email in destinatarios}
    copia = []
    for email in os.environ.get("CORREOS_COPIA", "").split(","):
        email = email.strip()
        if email and email.lower() not in ya and email.lower() not in {c.lower() for c in copia}:
            copia.append(email)
    return copia


def _nombre_remitente(organizador: Optional[Destinatario], cuenta: str, por_defecto: str) -> str:
    """
    El correo sale siempre de la cuenta verificada (cuenta), pero se presenta con el
    nombre de quien organizó la reunión: "Ana Pérez vía Motor de Horarios". Si el
    organizador es la propia cuenta remitente (las pruebas de QA), queda el nombre normal.
    """
    if not organizador or organizador[1].strip().lower() == cuenta.strip().lower():
        return por_defecto
    return f"{organizador[0]} vía Motor de Horarios"


def enviar_correos(destinatarios: Iterable[Destinatario], asunto: str, cuerpo: CuerpoPersonal,
                   organizador: Optional[Destinatario] = None) -> int:
    """
    Envía un correo independiente a cada destinatario (nadie ve el email de los demás),
    en HTML y texto plano, armado con su nombre por `cuerpo(nombre)`. Las respuestas
    van al organizador (Reply-To).
    Devuelve cuántos se enviaron; un fallo con una persona no impide enviar al resto.
    """
    destinatarios = list(destinatarios)
    modo = os.environ.get("EMAIL_MODE", "log")
    if modo == "brevo_api":
        return _enviar_brevo_api(destinatarios, asunto, cuerpo, organizador)
    if modo != "smtp":
        for nombre, email in destinatarios:
            logger.info("[correo local] Para: %s <%s> | %s\n%s", nombre, email, asunto, cuerpo(nombre)[0])
        return 0

    cfg = _config_smtp()
    copia = _copia_oculta(destinatarios)
    enviados = 0
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as smtp:
        smtp.starttls()
        smtp.login(cfg["user"], cfg["password"])
        for i, (nombre, email) in enumerate(destinatarios):
            msg = EmailMessage()
            msg["From"] = formataddr((_nombre_remitente(organizador, cfg["from"], cfg["from_name"]), cfg["from"]))
            if organizador:
                msg["Reply-To"] = formataddr(organizador)
            msg["To"] = formataddr((nombre, email))
            msg["Subject"] = asunto
            if i == 0 and copia:
                msg["Bcc"] = ", ".join(copia)  # send_message la usa y no la deja en el correo
            texto, html = cuerpo(nombre)
            msg.set_content(texto)
            if html:
                msg.add_alternative(html, subtype="html")
            try:
                smtp.send_message(msg)
                enviados += 1
            except smtplib.SMTPException:
                logger.exception("No se pudo enviar el correo a %s", email)
    return enviados


def _enviar_brevo_api(destinatarios, asunto: str, cuerpo: CuerpoPersonal,
                      organizador: Optional[Destinatario] = None) -> int:
    import httpx

    clave = os.environ["BREVO_API_KEY"].strip().strip("\"'").strip()
    if clave.startswith("xsmtpsib-"):
        logger.error("BREVO_API_KEY es una clave SMTP (xsmtpsib-). La API de Brevo necesita una "
                     "API key (xkeysib-): Brevo > SMTP & API > pestaña 'API Keys'.")
        return 0
    cuenta = os.environ["EMAIL_FROM"].strip()
    remitente = {"email": cuenta,
                 "name": _nombre_remitente(organizador, cuenta,
                                           os.environ.get("EMAIL_FROM_NAME", "Motor de Horarios"))}
    copia = _copia_oculta(destinatarios)
    enviados = 0
    with httpx.Client(base_url="https://api.brevo.com/v3", timeout=20,
                      headers={"api-key": clave, "accept": "application/json"}) as cliente:
        for i, (nombre, email) in enumerate(destinatarios):
            texto, html = cuerpo(nombre)
            mensaje = {
                "sender": remitente,
                "to": [{"email": email, "name": nombre}],
                "subject": asunto,
                "textContent": texto,
            }
            if html:
                mensaje["htmlContent"] = html
            if organizador:
                mensaje["replyTo"] = {"email": organizador[1], "name": organizador[0]}
            if i == 0 and copia:
                mensaje["bcc"] = [{"email": c} for c in copia]
            r = cliente.post("/smtp/email", json=mensaje)
            if r.is_success:
                enviados += 1
            else:
                logger.error("Brevo rechazó el correo a %s: %s %s", email, r.status_code, r.text[:300])
    return enviados
