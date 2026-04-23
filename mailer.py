import base64
import logging
import os
import smtplib
from email.message import EmailMessage

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("milkyrep.mailer")


def _to_bool(v: str | None, default: bool = True) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def validar_config_smtp() -> tuple[bool, str]:
    obrigatorias = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")
    faltando = [k for k in obrigatorias if not os.getenv(k)]
    if faltando:
        return (
            False,
            "Config SMTP incompleta. Defina no .env: " + ", ".join(faltando),
        )
    return True, ""


def _deve_usar_sendgrid_api(
    smtp_host: str, smtp_user: str, smtp_password: str
) -> bool:
    return (
        "sendgrid.net" in smtp_host.lower()
        and smtp_user.strip().lower() == "apikey"
        and smtp_password.strip().startswith("SG.")
    )


def _enviar_via_sendgrid_api(
    destinatarios: list[str],
    assunto: str,
    corpo_texto: str,
    anexo_bytes: bytes,
    anexo_nome: str,
    smtp_from: str,
    smtp_reply_to: str,
    api_key: str,
) -> None:
    anexo_b64 = base64.b64encode(anexo_bytes).decode("ascii")
    payload = {
        "personalizations": [{"to": [{"email": d} for d in destinatarios]}],
        "from": {"email": smtp_from},
        "reply_to": {"email": smtp_reply_to},
        "subject": assunto,
        "content": [{"type": "text/plain", "value": corpo_texto}],
        "attachments": [
            {
                "content": anexo_b64,
                "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "filename": anexo_nome,
                "disposition": "attachment",
            }
        ],
    }

    logger.info("Enviando via SendGrid API HTTPS para %s destinatário(s).", len(destinatarios))
    with httpx.Client(timeout=40.0) as client:
        r = client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if r.status_code not in (200, 202):
        raise Exception(f"SendGrid API retornou {r.status_code}: {r.text[:500]}")


def enviar_email_com_anexo(
    destinatarios: list[str],
    assunto: str,
    corpo_texto: str,
    anexo_bytes: bytes,
    anexo_nome: str,
) -> None:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587").strip())
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", "").strip() or smtp_user
    smtp_reply_to = os.getenv("SMTP_REPLY_TO", "").strip() or smtp_from
    smtp_use_tls = _to_bool(os.getenv("SMTP_USE_TLS", "true"), default=True)

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg["Reply-To"] = smtp_reply_to
    msg.set_content(corpo_texto)
    msg.add_attachment(
        anexo_bytes,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=anexo_nome,
    )

    if _deve_usar_sendgrid_api(smtp_host, smtp_user, smtp_password):
        _enviar_via_sendgrid_api(
            destinatarios=destinatarios,
            assunto=assunto,
            corpo_texto=corpo_texto,
            anexo_bytes=anexo_bytes,
            anexo_nome=anexo_nome,
            smtp_from=smtp_from,
            smtp_reply_to=smtp_reply_to,
            api_key=smtp_password,
        )
        return

    logger.info("Enviando via SMTP (%s:%s).", smtp_host, smtp_port)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=40) as server:
        if smtp_use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
