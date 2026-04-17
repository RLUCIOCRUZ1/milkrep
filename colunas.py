"""Normalização de cabeçalhos e mapeamento para nomes canônicos usados no app."""


def normalizar_header(nome: str) -> str:
    s = str(nome).strip()
    for ch in ("\n", "*", "#", "%", ".", "/", "°", "ª"):
        s = s.replace(ch, "")
    s = s.replace("º", "_")
    s = s.replace(" ", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_").lower()


# Ordem: do mais específico ao mais genérico (evita pegar coluna errada cedo demais)
ALIASES = {
    "customer": (
        "customer_codigo_cliente",
        "codigo_cliente",
        "cod_cliente",
        "cd_cliente",
        "cliente_codigo",
        "customer",
        "cliente",
    ),
    "store": (
        "store_codigo_loja",
        "codigo_loja",
        "cod_loja",
        "store",
        "loja",
    ),
    "customer_name": (
        "customer_name_razao_social_do_grupo",
        "razao_social_do_grupo",
        "customer_name",
        "nome_cliente",
        "razao_social",
        "cliente_nome",
    ),
    "order_no": (
        "order_no_n_pedido_skechers",
        "n_pedido_skechers",
        "pedido_skechers",
        "numero_pedido",
        "n_pedido",
        "order_no",
        "pedido",
    ),
    "style": (
        "style_modelo",
        "modelo",
        "style",
        "estilo",
    ),
    "rsn": (
        "rsn",
        "status_rsn",
    ),
    "sku": (
        "sku",
        "codigo_sku",
        "cod_sku",
        "product_sku",
    ),
}

# Colunas adicionais da planilha que devem ir para a tabela pedidos (slug = nome no Supabase)
COLUNAS_EXTRAS_PEDIDO = (
    "descricao_modelo",
    "genero",
    "cod_desconto",
    "total",
    "cfop",
    "status_customer",
    "campanha",
    "confirmado",
)

COLUNAS_RESERVADAS = frozenset(ALIASES.keys())


def alinhar_colunas_extras(df):
    """Garante slugs iguais ao banco (ex.: 'Descrição modelo' → descricao_modelo)."""
    rename = {}
    for c in df.columns:
        if c in COLUNAS_RESERVADAS:
            continue
        n = normalizar_header(c)
        if n in COLUNAS_EXTRAS_PEDIDO and c != n:
            rename[c] = n
    if rename:
        df.rename(columns=rename, inplace=True)
    return df


def mapear_colunas_clientes(df):
    """
    Renomeia colunas vindas do Google Sheets para os nomes esperados pelo app.
    Usa cabeçalhos originais e compara com aliases normalizados.
    """
    raw_cols = list(df.columns)
    norm_por_raw = {c: normalizar_header(c) for c in raw_cols}
    usados = set()
    rename = {}

    for canon, aliases in ALIASES.items():
        found = None
        for alvo in aliases:
            alvo_n = normalizar_header(alvo)
            for raw, norm in norm_por_raw.items():
                if raw in usados:
                    continue
                if norm == alvo_n:
                    found = raw
                    break
            if found:
                break
        if found is None:
            for alvo in aliases:
                alvo_n = normalizar_header(alvo)
                if len(alvo_n) < 3:
                    continue
                for raw, norm in norm_por_raw.items():
                    if raw in usados:
                        continue
                    if alvo_n in norm:
                        found = raw
                        break
                if found:
                    break
        if found:
            rename[found] = canon
            usados.add(found)

    return df.rename(columns=rename, copy=False)
