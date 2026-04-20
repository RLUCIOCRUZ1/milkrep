"""
Mapeamento por letra Excel da planilha para colunas no Supabase.
"""

from __future__ import annotations

import pandas as pd
from openpyxl.utils import get_column_letter

from colunas import normalizar_header

# Só use se o banco tiver nomes diferentes dos canônicos.
RENOME_COLUNAS_CANONICAS_SUPABASE: dict[str, str] = {}

# Mapeamento confirmado pelo usuário (planilha -> pedidos).
PEDIDOS_COLUNA_POR_LETRA: dict[str, str] = {
    "D": "store",
    "E": "customer_name",
    "O": "descricao_modelo",
    "Q": "genero",
    "V": "preco_bruto",
    "Y": "preco_liquido",
    "Z": "total",
    "AS": "pick_date",
    "AD": "data_original",
    "AF": "data_faturamento",
}

# Coluna de SKU para itens_pedido.
SKU_LETRA_ITENS = "L"

# Faixa de tamanhos/quantidades (horizontal na planilha -> vertical em itens_pedido).
ITENS_FAIXA_INICIO = "AV"
ITENS_FAIXA_FIM = "CC"


def _excel_letras_para_indice_1based(letras: str) -> int:
    s = str(letras).strip().upper()
    if not s or any(c < "A" or c > "Z" for c in s):
        raise ValueError(f"Letras de coluna Excel inválidas: {letras!r}")
    n = 0
    for c in s:
        n = n * 26 + (ord(c) - ord("A") + 1)
    return n


def indice_0based_de_excel(letras: str) -> int:
    return _excel_letras_para_indice_1based(letras) - 1


def excel_de_indice_0based(i: int) -> str:
    return get_column_letter(i + 1)


def indice_esta_em_faixa_itens(i: int) -> bool:
    a = indice_0based_de_excel(ITENS_FAIXA_INICIO)
    b = indice_0based_de_excel(ITENS_FAIXA_FIM)
    return a <= i <= b


def indices_excel_somente_pedidos() -> list[int]:
    return sorted(indice_0based_de_excel(L) for L in PEDIDOS_COLUNA_POR_LETRA)


def indices_excel_selecionados() -> list[int]:
    s: set[int] = set(indices_excel_somente_pedidos())
    s.add(indice_0based_de_excel(SKU_LETRA_ITENS))
    a = indice_0based_de_excel(ITENS_FAIXA_INICIO)
    b = indice_0based_de_excel(ITENS_FAIXA_FIM)
    for j in range(a, b + 1):
        s.add(j)
    return sorted(s)


def _coluna_df_por_letra(df: pd.DataFrame, letra: str) -> str | None:
    i = indice_0based_de_excel(letra)
    if i < 0 or i >= len(df.columns):
        return None
    return str(df.columns[i])


def garantir_coluna_sku_por_letra(df: pd.DataFrame) -> pd.DataFrame:
    col = _coluna_df_por_letra(df, SKU_LETRA_ITENS)
    if not col:
        return df
    out = df.copy()
    out["sku"] = out[col]
    return out


def enriquecer_pedidos_colunas_excel(
    df_cli: pd.DataFrame,
    df_ped: pd.DataFrame,
    headers_orig: list[str],
    indices: list[int],
) -> pd.DataFrame:
    _ = headers_orig
    _ = indices
    out = df_ped.copy()
    for letra, destino in PEDIDOS_COLUNA_POR_LETRA.items():
        col = _coluna_df_por_letra(df_cli, letra)
        if not col:
            continue
        dest = RENOME_COLUNAS_CANONICAS_SUPABASE.get(destino, destino)
        out[dest] = df_cli[col].values
    return out


def montar_de_para_planilha_supabase(
    headers_orig: list[str],
    df_cli: pd.DataFrame,
    indices: list[int],
) -> pd.DataFrame:
    linhas = []
    for i in indices:
        if i >= len(headers_orig) or i >= len(df_cli.columns):
            continue
        letra = excel_de_indice_0based(i)
        hp = headers_orig[i]
        if letra in PEDIDOS_COLUNA_POR_LETRA:
            col_db = PEDIDOS_COLUNA_POR_LETRA[letra]
            nota = f"Coluna `pedidos.{col_db}`"
        elif letra == SKU_LETRA_ITENS:
            col_db = "sku (itens_pedido)"
            nota = "Usada para preencher `itens_pedido.sku`"
        elif indice_esta_em_faixa_itens(i):
            col_db = "—"
            nota = (
                "Só `itens_pedido`: valor > 0 vira linha vertical "
                f"(tamanho=`{normalizar_header(hp)}`, quantidade)"
            )
        else:
            col_db = "—"
            nota = "Não mapeada para banco"
        linhas.append(
            {
                "excel": letra,
                "cabecalho_planilha": hp,
                "coluna_supabase_pedidos": col_db,
                "detalhe": nota,
            }
        )
    return pd.DataFrame(linhas)
