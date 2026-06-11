"""Ordem e rótulos da tabela de comissionamento (layout atual da planilha)."""

from __future__ import annotations

import pandas as pd

# (slug no banco/planilha normalizado, rótulo na tela, slugs alternativos)
_COLUNAS_LAYOUT_NOVO: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("emp", "Emp", ()),
    ("tipo", "Tipo", ()),
    ("doc", "Doc.", ()),
    ("parc", "Parc.", ()),
    ("dt_emissao", "Dt. Emissão", ()),
    ("dt_vencto", "Dt. Vencto", ()),
    ("dias_atraso", "Dias Atraso", ()),
    ("valor_titulo", "Valor Título", ()),
    ("saldo_titulo", "Saldo Título", ()),
    ("situacao", "Situação", ()),
    ("ref", "Ref.", ()),
    ("cod", "Cód.", ("codigo", "cod_cliente")),
    ("razao_social", "Razão Social", ()),
    ("cnpj", "CNPJ", ()),
    ("grupo", "Grupo", ()),
    ("grupo_de_cliente", "Grupo de Cliente", ()),
    ("rep", "Rep", ()),
    ("nro_pedido", "Nro. Pedido", ("numero_pedido", "n_pedido")),
    ("p_o", "P.O", ("po",)),
    ("nro_ped_integracao_i", "Nro. Ped. Integração I", ()),
    ("invoice", "Invoice", ()),
    ("emp_nf", "Emp+NF", ()),
    ("rep_hydee", "Rep. Hydee", ()),
    ("invoice_2", "Invoice", ()),
    ("p_o_2", "P.O", ("po_2",)),
    ("percentual", "%", ("coluna", "percent", "perc")),
    ("previsao", "provisao contabil", ("provisao_contabil", "provisao")),
    ("tipo_cliente", "Tipo Cliente", ("tipo_de_cliente",)),
    ("preposto", "Preposto", ()),
)

# Layout anterior — exibidos ao final se ainda existirem no banco.
_COLUNAS_LAYOUT_ANTIGO: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("liquidacao", "Liquidação", ()),
    ("valor_pago", "Valor pago", ()),
    ("juros", "Juros", ()),
    ("desconto", "Desconto", ()),
    ("baixa_descccc", "Baixa Desc/CCC", ("baixa_desc_ccc",)),
    ("outros", "Outros", ()),
    ("port", "port", ()),
)

_COLUNAS_OCULTAS = frozenset({"id", "created_at", "updated_at"})

_SLUG_PARA_LABEL_EXTRA = {
    "po": "P.O",
    "po_2": "P.O",
    "p_o_2": "P.O",
    "invoice_2": "Invoice",
    "rep_hydee": "Rep. Hydee",
}


def _resolver_coluna_df(df: pd.DataFrame, slug: str, aliases: tuple[str, ...]) -> str | None:
    candidatos = (slug,) + aliases
    for c in candidatos:
        if c in df.columns:
            return c
    return None


def _coluna_tem_dados(serie: pd.Series) -> bool:
    """True se existir ao menos um valor preenchido na coluna."""
    if serie.empty:
        return False
    valores = serie.dropna()
    if valores.empty:
        return False
    texto = valores.astype(str).str.strip()
    texto = texto[~texto.str.lower().isin({"", "nan", "none", "null"})]
    return not texto.empty


def preparar_comissao_para_exibicao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reordena e renomeia colunas para o layout da planilha atual.
    Exibe somente colunas com pelo menos um valor preenchido.
    """
    if df.empty:
        return df

    partes: list[pd.Series] = []
    labels_usados: set[str] = set()
    colunas_usadas: set[str] = set()

    def _adicionar(col_df: str, label: str) -> None:
        if col_df in colunas_usadas or not _coluna_tem_dados(df[col_df]):
            return
        nome = label
        n = 2
        while nome in labels_usados:
            nome = f"{label} ({n})"
            n += 1
        labels_usados.add(nome)
        colunas_usadas.add(col_df)
        partes.append(df[col_df].rename(nome))

    for slug, label, aliases in _COLUNAS_LAYOUT_NOVO + _COLUNAS_LAYOUT_ANTIGO:
        col = _resolver_coluna_df(df, slug, aliases)
        if col:
            _adicionar(col, label)

    for col in df.columns:
        if col in colunas_usadas or col in _COLUNAS_OCULTAS:
            continue
        label = _SLUG_PARA_LABEL_EXTRA.get(col, col.replace("_", " ").strip().title())
        _adicionar(col, label)

    if not partes:
        return df.copy()

    return pd.concat(partes, axis=1)
