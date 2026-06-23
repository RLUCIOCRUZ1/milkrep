from urllib.parse import urlparse

from supabase import create_client, Client
from dotenv import load_dotenv
import os

# 🔐 carregar variáveis
load_dotenv()


def _normalizar_supabase_url(raw: str) -> str:
    u = str(raw).strip().strip('"').strip("'").rstrip("/")
    if not u:
        return u
    if not u.startswith(("http://", "https://")):
        u = f"https://{u}"
    return u


def _validar_supabase_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host.endswith(".supabase.co"):
        raise Exception(
            "SUPABASE_URL inválida. Use o formato "
            "https://SEU_PROJETO.supabase.co (copie em Supabase → Settings → API)."
        )


# 🔗 pegar do .env
url = _normalizar_supabase_url(os.getenv("SUPABASE_URL", ""))
key = (os.getenv("SUPABASE_KEY") or "").strip()

# 🧪 validação (evita erro silencioso)
if not url or not key:
    raise Exception("❌ SUPABASE_URL ou SUPABASE_KEY não encontrados")

_validar_supabase_url(url)

# 🔗 conexão
supabase: Client = create_client(url, key)