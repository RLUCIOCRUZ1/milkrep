import pandas as pd
from supabase_client import supabase


def _valor_para_api(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def _esvaziar_itens_pedido():
    """Apaga todas as linhas de itens_pedido (PostgREST exige filtro no DELETE)."""
    supabase.table("itens_pedido").delete().gte("pedido_id", 0).execute()


def limpar_dados_automacao():
    """Remove itens_pedido e pedidos (filhos antes, por FK)."""
    _esvaziar_itens_pedido()
    supabase.table("pedidos").delete().gte("order_no", 0).execute()


def _montar_sku_item(row, tamanho, pedido_id):
    """
    SKU por linha: coluna sku + tamanho, ou modelo (style) + tamanho, ou pedido + tamanho.
    """
    base = row.get("sku")
    vb = _valor_para_api(base)
    if vb:
        return f"{vb}-{tamanho}"
    style = row.get("style")
    vs = _valor_para_api(style)
    if vs:
        return f"{vs}-{tamanho}"
    pid = _valor_para_api(pedido_id)
    if pid is not None:
        return f"{pid}-{tamanho}"
    return None


# 🔹 salvar pedidos
def salvar_pedidos(df):

    dados = [
        {k: _valor_para_api(val) for k, val in row.items()}
        for row in df.to_dict(orient="records")
    ]

    response = supabase.table("pedidos").insert(dados).execute()

    return response.data


# 🔹 salvar itens (tamanhos)
def salvar_itens(df):

    _esvaziar_itens_pedido()

    tamanhos = [
        "21","22","23","24","25","26","27","28","29","30",
        "31","32","33","34","35","36","37","38","39","40",
        "41","42","43","44","45","46","47","48",
        "XS","S","M","L","XL"
    ]

    itens = []

    for _, row in df.iterrows():

        pedido_id = row.get("order_no")

        for tamanho in tamanhos:

            qtd = row.get(tamanho)

            try:
                qtd_float = float(qtd)
            except:
                qtd_float = 0

            if qtd_float > 0:
                item = {
                    "pedido_id": _valor_para_api(pedido_id),
                    "tamanho": tamanho,
                    "quantidade": qtd_float,
                    "sku": _montar_sku_item(row, tamanho, pedido_id),
                }
                itens.append(item)

    if itens:
        supabase.table("itens_pedido").insert(itens).execute()