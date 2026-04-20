from datetime import date, datetime
import re

import pandas as pd
from colunas import COLUNAS_EXTRAS_PEDIDO, normalizar_header
from supabase_client import supabase

# Nomes exatos das colunas na tabela `pedidos` (iguais ao Table Editor do Supabase).
_COLUNAS_BASE_PEDIDO = (
    "customer",
    "store",
    "customer_name",
    "order_no",
    "style",
    "rsn",
    "status_pedido",
)

# Depois de criar colunas extras no painel SQL, acrescente o identificador aqui (slug igual ao da planilha normalizado).
COLUNAS_PEDIDO_EXTRAS_NO_SUPABASE: tuple[str, ...] = (
    "preco_bruto",
    "preco_liquido",
    "pick_date",
    "data_original",
    "data_faturamento",
    # "payment_type_condicao_de_pagamento",
)

COLUNAS_INSERT_PEDIDOS = (
    frozenset(_COLUNAS_BASE_PEDIDO)
    | frozenset(COLUNAS_EXTRAS_PEDIDO)
    | frozenset(COLUNAS_PEDIDO_EXTRAS_NO_SUPABASE)
)

# Para carregar 100% dos campos da aba dados_comissao, use tabela dedicada com schema completo.
TABELAS_COMISSAO_CANDIDATAS = ("comissao_complete",)


def filtrar_dataframe_pedidos_para_insert(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém só colunas que existem na tabela `pedidos` (evita PGRST204)."""
    cols = [c for c in df.columns if c in COLUNAS_INSERT_PEDIDOS]
    return df[cols].copy()


def _carregar_tabela_completa(nome_tabela: str, page_size: int = 1000) -> list[dict]:
    """
    Lê todos os registros da tabela/view em páginas.
    Evita limite padrão de linhas por chamada no PostgREST.
    """
    registros: list[dict] = []
    start = 0
    while True:
        end = start + page_size - 1
        response = (
            supabase.table(nome_tabela).select("*").range(start, end).execute()
        )
        chunk = response.data or []
        if not chunk:
            break
        registros.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return registros


def carregar_vw_pedido_itens() -> tuple[pd.DataFrame, str]:
    """
    Lê a view de consolidação pedidos+itens no Supabase.
    Tenta os dois nomes comuns para evitar quebra por variação de nomenclatura.
    """
    candidatas = ("vw_pedido_itens", "vw_pedidos_itens")
    ultimo_erro = None
    for nome in candidatas:
        try:
            dados = _carregar_tabela_completa(nome)
            return pd.DataFrame(dados), nome
        except Exception as e:
            ultimo_erro = e
    if ultimo_erro:
        raise ultimo_erro
    return pd.DataFrame(), candidatas[0]


def _normalizar_colunas_unicas(colunas: list[str]) -> list[str]:
    usados: dict[str, int] = {}
    saida: list[str] = []
    for c in colunas:
        base = normalizar_header(c)
        # Reforça sanitização para identificador SQL/PostgREST.
        base = (
            base.replace("+", "_")
            .replace("-", "_")
            .replace("(", "")
            .replace(")", "")
        )
        while "__" in base:
            base = base.replace("__", "_")
        base = base.strip("_")
        if not base:
            base = "coluna"
        n = usados.get(base, 0) + 1
        usados[base] = n
        saida.append(base if n == 1 else f"{base}_{n}")
    return saida


def _serie_texto_limpa(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().replace({"": None, "nan": None, "None": None})


def montar_comissao_com_preposto(
    df_comissao: pd.DataFrame, df_vendedores: pd.DataFrame
) -> pd.DataFrame:
    """
    Aplica PROCV por código de cliente:
    dados_comissao!O (Grupo) -> lista_vendedor!B (CUSTOMER) retornando lista_vendedor!J (PREPOSTOS).
    """
    if df_comissao.empty:
        return pd.DataFrame()

    dfc = df_comissao.copy()
    dfc.columns = _normalizar_colunas_unicas([str(c) for c in dfc.columns])

    if df_vendedores.empty:
        dfc["preposto"] = None
        return dfc

    dfv = df_vendedores.copy()
    # Coluna B (index 1) = CUSTOMER, coluna J (index 9) = PREPOSTOS.
    if len(dfv.columns) < 10:
        dfc["preposto"] = None
        return dfc

    col_customer = str(dfv.columns[1])
    col_prepostos = str(dfv.columns[9])

    chave_preposto = (
        pd.DataFrame(
            {
                "grupo": _serie_texto_limpa(dfv[col_customer]),
                "preposto": _serie_texto_limpa(dfv[col_prepostos]),
            }
        )
        .dropna(subset=["grupo"])
        .drop_duplicates(subset=["grupo"], keep="first")
    )

    if "grupo" not in dfc.columns:
        # Segurança: caso a coluna O não normalize como "grupo".
        dfc["preposto"] = None
        return dfc

    dfc["grupo"] = _serie_texto_limpa(dfc["grupo"])
    dfc = dfc.merge(chave_preposto, on="grupo", how="left")
    return dfc


def _limpar_tabela_generica(nome_tabela: str) -> None:
    """
    Limpa tabela com tentativas de filtros compatíveis com PostgREST.
    """
    filtros = (
        ("id", "gte", 0),
        ("grupo", "neq", "__nunca__"),
        ("customer", "neq", "__nunca__"),
    )
    for col, op, val in filtros:
        try:
            req = supabase.table(nome_tabela).delete()
            req = getattr(req, op)(col, val)
            req.execute()
            return
        except Exception:
            continue
    raise Exception(f"Não foi possível limpar a tabela `{nome_tabela}` com filtros padrão.")


def salvar_comissao(df_comissao_final: pd.DataFrame) -> tuple[str, int]:
    """
    Limpa e recarrega tabela de comissão (comissao_complete ou comissao).
    Retorna (nome_tabela_usada, quantidade_inserida).
    """
    if df_comissao_final.empty:
        return "", 0

    dados = [
        {k: _valor_para_api(v) for k, v in row.items()}
        for row in df_comissao_final.to_dict(orient="records")
    ]
    if not dados:
        return "", 0

    ultimo_erro = None
    for nome_tabela in TABELAS_COMISSAO_CANDIDATAS:
        try:
            _limpar_tabela_generica(nome_tabela)
            tam_lote = 500
            for i in range(0, len(dados), tam_lote):
                lote = dados[i : i + tam_lote]
                supabase.table(nome_tabela).insert(lote).execute()
            return nome_tabela, len(dados)
        except Exception as e:
            ultimo_erro = e
            continue

    if ultimo_erro:
        raise ultimo_erro
    return "", 0

# Colunas da planilha (letras Excel) usadas só para itens_pedido (quantidades por tamanho/variante).
_ITENS_COLUNA_INICIO = "AV"
_ITENS_COLUNA_FIM = "CC"
_ITENS_SUPORTA_CONTEXTO: bool | None = None


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


def _itens_suporta_contexto() -> bool:
    """
    Detecta se `itens_pedido` já possui colunas de contexto (`rsn`, `style`).
    Mantém retrocompatibilidade com schema antigo.
    """
    global _ITENS_SUPORTA_CONTEXTO
    if _ITENS_SUPORTA_CONTEXTO is not None:
        return _ITENS_SUPORTA_CONTEXTO
    try:
        supabase.table("itens_pedido").select("id,rsn,style").limit(1).execute()
        _ITENS_SUPORTA_CONTEXTO = True
    except Exception:
        _ITENS_SUPORTA_CONTEXTO = False
    return _ITENS_SUPORTA_CONTEXTO


def _parse_numero_flexivel(v):
    """Converte texto tipo planilha (ex.: 1.234,56 ou 1234.56) em float ou None."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).replace("\xa0", " ").strip()
    if not s:
        return None
    # Remove moeda e caracteres inválidos para número.
    s = re.sub(r"(?i)\br\$\s*", "", s)
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s or s in {"-", ".", ","}:
        return None

    # Trata formatos BR/EN com separadores de milhar/decimal.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # 1.234,56 -> 1234.56
            s = s.replace(".", "").replace(",", ".")
        else:
            # 1,234.56 -> 1234.56
            s = s.replace(",", "")
    elif "," in s:
        # 475,00 -> 475.00
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        # 1.234 -> 1234
        s = s.replace(".", "")

    try:
        return float(s)
    except ValueError:
        return None


_COLUNAS_NUMERICAS_PEDIDO = frozenset({"total", "preco_bruto", "preco_liquido"})
_COLUNAS_DATA_PEDIDO = frozenset({"pick_date", "data_original", "data_faturamento"})


def _parse_data_iso(v):
    """
    Converte datas da planilha (ex.: 15/04/2026) para ISO (YYYY-MM-DD) aceito pelo Postgres.
    Retorna None para vazio/inválido.
    """
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()

    s = str(v).strip()
    if not s:
        return None

    formatos = (
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    )
    for fmt in formatos:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue

    dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.date().isoformat()


def _valor_para_api_pedido(coluna: str, v):
    """Igual a _valor_para_api, com coerção numérica em colunas conhecidas da tabela pedidos."""
    if coluna in _COLUNAS_NUMERICAS_PEDIDO:
        n = _parse_numero_flexivel(v)
        return n
    if coluna in _COLUNAS_DATA_PEDIDO:
        return _parse_data_iso(v)
    return _valor_para_api(v)


def _esvaziar_itens_pedido():
    """Apaga todas as linhas de itens_pedido (PostgREST exige filtro no DELETE)."""
    # Usar PK numérica evita deixar lixo quando pedido_id está vazio/texto.
    supabase.table("itens_pedido").delete().gte("id", 0).execute()


def limpar_dados_automacao():
    """Remove itens_pedido e pedidos (filhos antes, por FK)."""
    _esvaziar_itens_pedido()
    # Limpa por PK para remover também registros antigos com order_no vazio.
    supabase.table("pedidos").delete().gte("id", 0).execute()


def _excel_letras_para_indice_1based(letras: str) -> int:
    """Converte letras de coluna estilo Excel ('A', 'Z', 'AA', 'AU', 'CC') em número 1-based."""
    s = str(letras).strip().upper()
    if not s or any(c < "A" or c > "Z" for c in s):
        raise ValueError(f"Letras de coluna Excel inválidas: {letras!r}")
    n = 0
    for c in s:
        n = n * 26 + (ord(c) - ord("A") + 1)
    return n


def itens_colunas_faixa_planilha(df: pd.DataFrame) -> list[str]:
    """Nomes das colunas da planilha na faixa AV–CC (quantidades por item)."""
    return _nomes_colunas_faixa_excel(df, _ITENS_COLUNA_INICIO, _ITENS_COLUNA_FIM)


def montar_dataframe_itens_horizontal(
    df: pd.DataFrame,
    colunas_chave: tuple[str, ...] = ("order_no", "customer", "store", "style", "sku"),
) -> pd.DataFrame:
    """
    Uma linha por linha da planilha, com chaves do pedido + colunas AV–CC como na planilha
    (valores iguais aos enviados para itens_pedido quando quantidade > 0).
    """
    cols_qtd = itens_colunas_faixa_planilha(df)
    chave = [c for c in colunas_chave if c in df.columns]
    if not cols_qtd:
        return pd.DataFrame(columns=chave)
    return df[chave + cols_qtd].copy()


def _nomes_colunas_faixa_excel(df: pd.DataFrame, ini: str, fim: str) -> list[str]:
    """Nomes das colunas do DataFrame entre ini e fim (inclusive), na ordem da planilha."""
    a = _excel_letras_para_indice_1based(ini)
    b = _excel_letras_para_indice_1based(fim)
    i0 = a - 1
    i1 = b
    cols = list(df.columns)
    if i0 < 0 or i0 >= len(cols):
        return []
    i1 = min(i1, len(cols))
    return [str(c) for c in cols[i0:i1]]


def _montar_sku_item(row, tamanho, pedido_id):
    """
    SKU do item: prioriza coluna L (sku da planilha), sem concatenar tamanho.
    Fallback para style e depois pedido_id, mantendo valor-base.
    """
    base = row.get("sku")
    vb = _valor_para_api(base)
    if vb:
        return str(vb)
    style = row.get("style")
    vs = _valor_para_api(style)
    if vs:
        return str(vs)
    pid = _valor_para_api(pedido_id)
    if pid is not None:
        return str(pid)
    return None


# 🔹 salvar pedidos
def salvar_pedidos(df):
    df = filtrar_dataframe_pedidos_para_insert(df)

    # Evita duplicidade no mesmo lote: mesma combinação de pedido/produto/status/cliente.
    chaves_duplicidade = [c for c in ("order_no", "style", "rsn", "customer_name") if c in df.columns]
    if chaves_duplicidade:
        df = df.drop_duplicates(subset=chaves_duplicidade, keep="first")

    dados_brutos = [
        {k: _valor_para_api_pedido(k, val) for k, val in row.items()}
        for row in df.to_dict(orient="records")
    ]

    # Evita inserir linhas "vazias" (com apenas status_pedido preenchido automaticamente).
    dados = [
        row
        for row in dados_brutos
        if any(v is not None for k, v in row.items() if k != "status_pedido")
    ]

    # Só persiste pedido com pelo menos uma chave de negócio preenchida.
    campos_chave = ("order_no", "customer", "style", "customer_name")
    dados = [
        row
        for row in dados
        if any(row.get(c) is not None for c in campos_chave)
    ]

    if not dados:
        return []

    response = supabase.table("pedidos").insert(dados).execute()

    return response.data


# 🔹 salvar itens (tamanhos)
def salvar_itens(df):

    _esvaziar_itens_pedido()

    colunas_qtd = itens_colunas_faixa_planilha(df)
    if not colunas_qtd:
        return

    itens = []
    itens_tem_contexto = _itens_suporta_contexto()

    for _, row in df.iterrows():

        pedido_id = row.get("order_no")
        pedido_id_api = _valor_para_api(pedido_id)
        if pedido_id_api is None:
            continue

        for nome_col in colunas_qtd:

            qtd = row.get(nome_col)

            try:
                qtd_float = float(qtd)
            except (TypeError, ValueError):
                qtd_float = 0

            if qtd_float > 0:
                tamanho = normalizar_header(nome_col)
                item = {
                    "pedido_id": pedido_id_api,
                    "tamanho": tamanho,
                    "quantidade": qtd_float,
                    "sku": _montar_sku_item(row, tamanho, pedido_id),
                }
                if itens_tem_contexto:
                    item["rsn"] = _valor_para_api(row.get("rsn"))
                    item["style"] = _valor_para_api(row.get("style"))
                itens.append(item)

    if itens:
        supabase.table("itens_pedido").insert(itens).execute()