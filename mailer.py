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


def _resolver_brevo_api_key() -> str:
    return (
        os.getenv("BREVO_API_KEY", "").strip()
        or os.getenv("BREVO_APIKEY", "").strip()
    )


def _host_brevo(smtp_host: str) -> bool:
    return "brevo.com" in smtp_host.lower()


def _deve_usar_brevo_api(smtp_host: str) -> bool:
    """
    Hugging Face e outros hosts em nuvem costumam bloquear SMTP (porta 587).
    Com Brevo, usamos a API HTTPS (porta 443).
    """
    if not _host_brevo(smtp_host):
        return False
    if _to_bool(os.getenv("BREVO_USE_SMTP"), default=False):
        return False
    return bool(_resolver_brevo_api_key())


def validar_config_smtp() -> tuple[bool, str]:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_from = os.getenv("SMTP_FROM", "").strip()

    if _deve_usar_brevo_api(smtp_host):
        if not _resolver_brevo_api_key():
            return (
                False,
                "Para Brevo na nuvem, defina BREVO_API_KEY (Brevo → SMTP & API → API keys).",
            )
        if not smtp_from:
            return False, "Defina SMTP_FROM com o remetente validado no Brevo."
        return True, ""

    obrigatorias = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")
    faltando = [k for k in obrigatorias if not os.getenv(k)]
    if faltando:
        return (
            False,
            "Config SMTP incompleta. Defina no .env: " + ", ".join(faltando),
        )
    return True, ""


def _parse_remetente(smtp_from: str) -> tuple[str, str]:
    bruto = str(smtp_from).strip()
    if "<" in bruto and ">" in bruto:
        nome = bruto.split("<", 1)[0].strip().strip('"')
        email = bruto.split("<", 1)[1].split(">", 1)[0].strip()
        return (nome or "Milkyrep"), email
    return "Milkyrep", bruto


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
    with httpx.Client(timeout=120.0) as client:
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


def _enviar_via_brevo_api(
    destinatarios: list[str],
    assunto: str,
    corpo_texto: str,
    anexo_bytes: bytes,
    anexo_nome: str,
    smtp_from: str,
    smtp_reply_to: str,
    api_key: str,
) -> None:
    nome_remetente, email_remetente = _parse_remetente(smtp_from)
    _, email_reply = _parse_remetente(smtp_reply_to)
    anexo_b64 = base64.b64encode(anexo_bytes).decode("ascii")
    payload = {
        "sender": {"name": nome_remetente, "email": email_remetente},
        "to": [{"email": d} for d in destinatarios],
        "replyTo": {"email": email_reply},
        "subject": assunto,
        "textContent": corpo_texto,
        "attachment": [{"content": anexo_b64, "name": anexo_nome}],
    }

    logger.info(
        "Enviando via Brevo API HTTPS para %s destinatário(s).", len(destinatarios)
    )
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "accept": "application/json",
            },
            json=payload,
        )
    if r.status_code not in (200, 201):
        raise Exception(f"Brevo API retornou {r.status_code}: {r.text[:500]}")


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

    if _deve_usar_brevo_api(smtp_host):
        _enviar_via_brevo_api(
            destinatarios=destinatarios,
            assunto=assunto,
            corpo_texto=corpo_texto,
            anexo_bytes=anexo_bytes,
            anexo_nome=anexo_nome,
            smtp_from=smtp_from,
            smtp_reply_to=smtp_reply_to,
            api_key=_resolver_brevo_api_key(),
        )
        return

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

    logger.info("Enviando via SMTP (%s:%s).", smtp_host, smtp_port)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=120) as server:
        if smtp_use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
