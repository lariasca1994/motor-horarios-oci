"""
Envío de correos individuales a cada persona de una reunión.

EMAIL_MODE=log  (por defecto, desarrollo) -> solo se escribe en el log.
EMAIL_MODE=brevo_api -> API HTTP de Brevo (BREVO_API_KEY, EMAIL_FROM, EMAIL_FROM_NAME).
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
from typing import Iterable, Tuple

logger = logging.getLogger(__name__)

Destinatario = Tuple[str, str]  # (nombre, email)


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


def enviar_correos(destinatarios: Iterable[Destinatario], asunto: str, cuerpo: str) -> int:
    """
    Envía un correo independiente a cada destinatario (nadie ve el email de los demás).
    Devuelve cuántos se enviaron; un fallo con una persona no impide enviar al resto.
    """
    destinatarios = list(destinatarios)
    modo = os.environ.get("EMAIL_MODE", "log")
    if modo == "brevo_api":
        return _enviar_brevo_api(destinatarios, asunto, cuerpo)
    if modo != "smtp":
        for nombre, email in destinatarios:
            logger.info("[correo local] Para: %s <%s> | %s\n%s", nombre, email, asunto, cuerpo)
        return 0

    cfg = _config_smtp()
    enviados = 0
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as smtp:
        smtp.starttls()
        smtp.login(cfg["user"], cfg["password"])
        for nombre, email in destinatarios:
            msg = EmailMessage()
            msg["From"] = formataddr((cfg["from_name"], cfg["from"]))
            msg["To"] = formataddr((nombre, email))
            msg["Subject"] = asunto
            msg.set_content(f"Hola {nombre},\n\n{cuerpo}\n")
            try:
                smtp.send_message(msg)
                enviados += 1
            except smtplib.SMTPException:
                logger.exception("No se pudo enviar el correo a %s", email)
    return enviados


def _enviar_brevo_api(destinatarios, asunto: str, cuerpo: str) -> int:
    import httpx

    clave = os.environ["BREVO_API_KEY"].strip().strip("\"'").strip()
    if clave.startswith("xsmtpsib-"):
        logger.error("BREVO_API_KEY es una clave SMTP (xsmtpsib-). La API de Brevo necesita una "
                     "API key (xkeysib-): Brevo > SMTP & API > pestaña 'API Keys'.")
        return 0
    remitente = {"email": os.environ["EMAIL_FROM"].strip(),
                 "name": os.environ.get("EMAIL_FROM_NAME", "Motor de Horarios")}
    enviados = 0
    with httpx.Client(base_url="https://api.brevo.com/v3", timeout=20,
                      headers={"api-key": clave, "accept": "application/json"}) as cliente:
        for nombre, email in destinatarios:
            r = cliente.post("/smtp/email", json={
                "sender": remitente,
                "to": [{"email": email, "name": nombre}],
                "subject": asunto,
                "textContent": f"Hola {nombre},\n\n{cuerpo}\n",
            })
            if r.is_success:
                enviados += 1
            else:
                logger.error("Brevo rechazó el correo a %s: %s %s", email, r.status_code, r.text[:300])
    return enviados
