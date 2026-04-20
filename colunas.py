"""Normalização de cabeçalhos e mapeamento para nomes canônicos usados no app."""

import unicodedata


def normalizar_header(nome: str) -> str:
    s = str(nome).strip()
    for ch in ("\n", "*", "#", "%", ".", "/", "°", "ª", "(", ")", "$", ",", "€"):
        s = s.replace(ch, "")
    s = s.replace("º", "_")
    s = s.replace(" ", "_")
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_").lower()
    # Cabeçalhos em PT costumam ter acentos; o banco usa slug sem acento (ex.: descricao_modelo).
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s


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

# Cabeçalhos de planilha que devem ir para a coluna numérica `total` no Supabase.
_SINONIMOS_SLUG_TOTAL = frozenset(
    {
        "valor_total",
        "total_valor",
        "total_geral",
        "total_pedido",
        "total_do_pedido",
        "valor_do_pedido",
        "amount_total",
        "order_total",
        "total_a_pagar",
        "total_liquido",
        "total_bruto",
        "sum_total",
        "linetotal",
    }
)


def _slug_extra_para_banco(n: str) -> str | None:
    """
    Converte o slug normalizado do cabeçalho para o nome da coluna extra no Supabase.
    Trata variações comuns da planilha (ex.: 'DESCRIÇÃO DO MODELO' → descricao_do_modelo).
    """
    if n in COLUNAS_EXTRAS_PEDIDO:
        return n
    # Planilha: "DESCRIÇÃO DO MODELO" / duas linhas no mesmo cabeçalho (Style Desc + descrição).
    if n == "descricao_do_modelo" or "descricao_do_modelo" in n:
        return "descricao_modelo"
    if n == "style_desc" or (n.startswith("style_desc") and "descricao" in n):
        return "descricao_modelo"
    # Planilha: "Discount" + "COD DESCONTO" (duas linhas) → discountcod_desconto (já coberto o caso exato acima).
    if "cod_desconto" in n:
        return "cod_desconto"
    if n == "dept_cfop" or (n.startswith("dept") and n.endswith("cfop")):
        return "cfop"
    if n == "status_customer_service" or (
        "status" in n and "customer" in n and "service" in n
    ):
        return "status_customer"
    if n.startswith("confirmed_yn") or (
        "confirmada" in n and "importacao" in n
    ):
        return "confirmado"
    # Total do pedido / valor: evita depender só do slug exato "total".
    if n in _SINONIMOS_SLUG_TOTAL:
        return "total"
    # Planilha: "Total Price" + "TOTAL COM DESCONTO" → total_price_total_com_desconto (contém "desconto").
    if n.startswith("total_price") or "total_com_desconto" in n:
        return "total"
    if ("valor" in n or "amount" in n) and "total" in n:
        return "total"
    if n.startswith("total") and "parcial" not in n and "subtotal" not in n:
        # Evita só rótulos claramente de desconto isolado (ex.: total_desconto sem "price"/valor).
        if "desconto" in n and not (
            "price" in n or "preco" in n or "valor" in n or "amount" in n
        ):
            pass
        else:
            return "total"
    return None


def alinhar_colunas_extras(df):
    """Garante slugs iguais ao banco (ex.: 'Descrição modelo' → descricao_modelo)."""
    rename = {}
    for c in df.columns:
        if c in COLUNAS_RESERVADAS:
            continue
        n = normalizar_header(c)
        destino = _slug_extra_para_banco(n)
        if destino and c != destino:
            rename[c] = destino
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
                    # Evita que "modelo" em "DESCRIÇÃO DO MODELO" vire coluna `style`.
                    if canon == "style" and (
                        "descricao" in norm or "description" in norm
                    ):
                        continue
                    # Evita que "pedido" em "TOTAL PEDIDO" / "VALOR DO PEDIDO" vire coluna `order_no`.
                    if canon == "order_no" and alvo == "pedido" and (
                        "total" in norm
                        or "valor" in norm
                        or "amount" in norm
                        or "sum" in norm
                    ):
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
