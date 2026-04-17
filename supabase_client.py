from supabase import create_client, Client
from dotenv import load_dotenv
import os

# 🔐 carregar variáveis
load_dotenv()

# 🔗 pegar do .env
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

# 🧪 validação (evita erro silencioso)
if not url or not key:
    raise Exception("❌ SUPABASE_URL ou SUPABASE_KEY não encontrados")

# 🔗 conexão
supabase: Client = create_client(url.strip(), key.strip())

print("Tentando conectar...")

try:
    res = supabase.table("pedidos").select("*").limit(1).execute()
    print("✅ Conectado com sucesso!")
    print(res)
except Exception as e:
    print("❌ Erro na conexão:")
    print(e)