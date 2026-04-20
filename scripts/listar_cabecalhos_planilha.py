"""
Lista os cabeçalhos da aba dados_clientes (como o gspread devolve)
e o slug sugerido para colunas no PostgreSQL (mesma regra de colunas.normalizar_header).

Uso (na raiz do projeto, com .venv ativo e credenciais.json):
  python scripts/listar_cabecalhos_planilha.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from colunas import normalizar_header  # noqa: E402
from sheets import ler_dados  # noqa: E402


def main() -> None:
    df_clientes, *_ = ler_dados()
    if df_clientes.empty:
        print("Planilha vazia ou sem linhas de cabeçalho/dados.")
        return
    print("raw (célula cabeçalho)\t->\tslug_postgres")
    print("-" * 72)
    for c in df_clientes.columns:
        slug = normalizar_header(c)
        print(f"{c!r}\t->\t{slug!r}")


if __name__ == "__main__":
    main()
