import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


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

    with smtplib.SMTP(smtp_host, smtp_port, timeout=60) as server:
        if smtp_use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
