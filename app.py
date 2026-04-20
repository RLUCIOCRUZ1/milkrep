import io
from datetime import datetime

import pandas as pd
import streamlit as st

from colunas import (
    COLUNAS_EXTRAS_PEDIDO,
    alinhar_colunas_extras,
    mapear_colunas_clientes,
)
from database import (
    carregar_vw_pedido_itens,
    filtrar_dataframe_pedidos_para_insert,
    limpar_dados_automacao,
    montar_comissao_com_preposto,
    salvar_comissao,
    salvar_itens,
    salvar_pedidos,
)
from excel_colunas import (
    RENOME_COLUNAS_CANONICAS_SUPABASE,
    garantir_coluna_sku_por_letra,
    enriquecer_pedidos_colunas_excel,
    indices_excel_selecionados,
    indices_excel_somente_pedidos,
    montar_de_para_planilha_supabase,
)
from sheets import ler_dados
from utils import tratar_status


def _excel_pedidos_e_de_para(df_ped: pd.DataFrame, df_de_para: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_ped.to_excel(writer, sheet_name="pedidos", index=False)
        df_de_para.to_excel(writer, sheet_name="de_para", index=False)
    buf.seek(0)
    return buf.read()


def _excel_view_pedido_itens(df_vw: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_vw.to_excel(writer, sheet_name="vw_pedido_itens", index=False)
    buf.seek(0)
    return buf.read()


st.title("Automação")

COLUNAS_OBRIGATORIAS = [
    "customer",
    "store",
    "customer_name",
    "order_no",
    "style",
    "rsn",
]

executar = st.button("🚀 Executar Automação")

if executar:

    (
        df_clientes,
        df_comissao,
        df_vendedores,
        aba_clientes,
        aba_comissao,
        aba_vendedores,
    ) = ler_dados()

    if df_clientes.empty:
        st.error("A aba dados_clientes está vazia ou sem linhas de dados.")
        st.stop()

    headers_orig = list(df_clientes.columns)

    df_clientes = mapear_colunas_clientes(df_clientes)
    alinhar_colunas_extras(df_clientes)
    df_clientes = garantir_coluna_sku_por_letra(df_clientes)

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df_clientes.columns]
    if faltando:
        st.error(
            "Não foi possível identificar estas colunas na planilha: "
            + ", ".join(faltando)
            + ". Verifique os cabeçalhos na aba dados_clientes. "
            + "Colunas lidas: "
            + ", ".join(str(c) for c in df_clientes.columns)
        )
        st.stop()

    df_clientes["status_pedido"] = df_clientes["rsn"].apply(tratar_status)

    colunas_base = [
        "customer",
        "store",
        "customer_name",
        "order_no",
        "style",
        "rsn",
        "status_pedido",
    ]
    extras = [c for c in COLUNAS_EXTRAS_PEDIDO if c in df_clientes.columns]
    df_pedidos = df_clientes[colunas_base + extras]

    df_pedidos = df_pedidos.rename(columns=RENOME_COLUNAS_CANONICAS_SUPABASE)

    indices_pedidos = indices_excel_somente_pedidos()
    indices_de_para = indices_excel_selecionados()
    df_pedidos = enriquecer_pedidos_colunas_excel(
        df_clientes, df_pedidos, headers_orig, indices_pedidos
    )
    df_de_para = montar_de_para_planilha_supabase(
        headers_orig, df_clientes, indices_de_para
    )

    limpar_dados_automacao()
    salvar_pedidos(df_pedidos)
    salvar_itens(df_clientes)
    df_comissao_final = montar_comissao_com_preposto(df_comissao, df_vendedores)
    tabela_comissao, qtd_comissao = salvar_comissao(df_comissao_final)

    extras_ausentes = [c for c in COLUNAS_EXTRAS_PEDIDO if c not in df_pedidos.columns]
    st.session_state["preview_conferencia"] = filtrar_dataframe_pedidos_para_insert(
        df_pedidos
    ).copy()
    st.session_state["preview_de_para"] = df_de_para.copy()
    st.session_state["extras_pedido_ausentes"] = extras_ausentes
    st.session_state["conferencia_xlsx_nome"] = (
        f"milkrep_conferencia_{datetime.now():%Y%m%d_%H%M}.xlsx"
    )
    st.session_state["preview_comissao"] = df_comissao_final.copy()
    st.session_state["comissao_tabela_usada"] = tabela_comissao
    st.session_state["comissao_qtd"] = qtd_comissao
    try:
        df_vw, nome_vw = carregar_vw_pedido_itens()
        st.session_state["preview_vw_pedido_itens"] = df_vw.copy()
        st.session_state["nome_vw_pedido_itens"] = nome_vw
        st.session_state.pop("erro_vw_pedido_itens", None)
    except Exception as e:
        st.session_state["erro_vw_pedido_itens"] = str(e)

    msg_comissao = (
        f" | comissão: {qtd_comissao} linhas em `{tabela_comissao}`"
        if tabela_comissao
        else " | comissão: sem linhas para carregar"
    )
    st.success(f"✅ Dados enviados com sucesso!{msg_comissao}")

if st.button("🔄 Atualizar tabela da view pedido_itens"):
    try:
        df_vw, nome_vw = carregar_vw_pedido_itens()
        st.session_state["preview_vw_pedido_itens"] = df_vw.copy()
        st.session_state["nome_vw_pedido_itens"] = nome_vw
        st.session_state.pop("erro_vw_pedido_itens", None)
        st.success(f"View `{nome_vw}` atualizada.")
    except Exception as e:
        st.session_state["erro_vw_pedido_itens"] = str(e)
        st.error(f"Não foi possível carregar a view: {e}")

if "preview_conferencia" in st.session_state:
    st.divider()
    st.subheader("De-para: planilha → Supabase")
    st.caption(
        "Colunas **D, E, O, Q, V, Y, Z, AS, AD, AF** → `pedidos`. "
        "Coluna **L** → `itens_pedido.sku`. Faixa **AV–CC** → só `itens_pedido` (quantidades); "
        "aparecem aqui só no de-para, não no insert de `pedidos`."
    )
    dp = st.session_state.get("preview_de_para")
    if dp is not None and not dp.empty:
        st.dataframe(dp, use_container_width=True, height=400)

    st.subheader("Conferência — payload gravado em `pedidos`")
    st.caption(
        "Igual ao insert em `pedidos`: só colunas listadas em `database.py` "
        "(`COLUNAS_INSERT_PEDIDOS` + opcionais em `COLUNAS_PEDIDO_EXTRAS_NO_SUPABASE`). "
        "Sem colunas AU–CC. Células vazias → `NULL`."
    )
    df_c = st.session_state["preview_conferencia"]
    aus = st.session_state.get("extras_pedido_ausentes") or []
    if aus:
        lista = ", ".join(f"`{x}`" for x in aus)
        st.info(
            "Extras definidos em `COLUNAS_EXTRAS_PEDIDO` que **não apareceram** após o mapeamento: "
            f"{lista}."
        )
    st.dataframe(df_c, use_container_width=True, height=520)

    nome_xlsx = st.session_state.get(
        "conferencia_xlsx_nome", "milkrep_conferencia.xlsx"
    )
    dp_df = st.session_state.get("preview_de_para")
    if dp_df is not None and not dp_df.empty:
        data_xlsx = _excel_pedidos_e_de_para(df_c, dp_df)
    else:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df_c.to_excel(w, sheet_name="pedidos", index=False)
        buf.seek(0)
        data_xlsx = buf.read()
    st.download_button(
        label="Exportar pedidos + de-para para Excel (.xlsx)",
        data=data_xlsx,
        file_name=nome_xlsx,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel_conferencia",
    )

if "preview_comissao" in st.session_state:
    st.divider()
    tabela = st.session_state.get("comissao_tabela_usada", "comissao")
    qtd = st.session_state.get("comissao_qtd", 0)
    st.subheader(f"Conferência — comissão carregada em `{tabela}`")
    st.caption(
        f"Total de linhas enviadas: {qtd}. "
        "Inclui coluna `preposto` via lookup por código do cliente (Grupo x CUSTOMER)."
    )
    st.dataframe(st.session_state["preview_comissao"], use_container_width=True, height=360)

if "preview_vw_pedido_itens" in st.session_state:
    st.divider()
    nome_vw = st.session_state.get("nome_vw_pedido_itens", "vw_pedido_itens")
    st.subheader(f"Cópia completa da view `{nome_vw}`")
    df_vw = st.session_state["preview_vw_pedido_itens"]
    st.caption(
        f"Dados extraídos do banco unindo pedidos + itens_pedido. "
        f"Total de linhas carregadas: {len(df_vw)}."
    )
    st.dataframe(df_vw, use_container_width=True, height=520)
    st.download_button(
        label="Exportar view para Excel (.xlsx)",
        data=_excel_view_pedido_itens(df_vw),
        file_name=f"{nome_vw}_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel_view_pedido_itens",
    )
elif "erro_vw_pedido_itens" in st.session_state:
    st.warning(
        "A tabela da view ainda não está disponível na tela: "
        + st.session_state["erro_vw_pedido_itens"]
    )
