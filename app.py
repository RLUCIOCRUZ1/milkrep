import streamlit as st
from colunas import (
    COLUNAS_EXTRAS_PEDIDO,
    alinhar_colunas_extras,
    mapear_colunas_clientes,
)
from sheets import ler_dados
from utils import tratar_status
from database import limpar_dados_automacao, salvar_pedidos, salvar_itens

st.title("Automação")

COLUNAS_OBRIGATORIAS = [
    "customer",
    "store",
    "customer_name",
    "order_no",
    "style",
    "rsn",
]

if st.button("🚀 Executar Automação"):

    df_clientes, df_comissao, aba_clientes, aba_comissao = ler_dados()

    if df_clientes.empty:
        st.error("A aba dados_clientes está vazia ou sem linhas de dados.")
        st.stop()

    df_clientes = mapear_colunas_clientes(df_clientes)
    alinhar_colunas_extras(df_clientes)

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

    # Nomes das colunas no Supabase (planilha / canônico → tabela)
    df_pedidos = df_pedidos.rename(
        columns={
            "store": "codigo_loja",
            "customer_name": "razao_social",
            "style": "modelo",
        }
    )

    limpar_dados_automacao()
    salvar_pedidos(df_pedidos)

    # 🔹 salvar tamanhos
    salvar_itens(df_clientes)

    st.success("✅ Dados enviados com sucesso!")