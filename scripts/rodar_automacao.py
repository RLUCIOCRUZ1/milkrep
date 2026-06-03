"""Executa a automação completa (pedidos + comissão) sem interface Streamlit."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from colunas import COLUNAS_EXTRAS_PEDIDO, alinhar_colunas_extras, mapear_colunas_clientes
from database import (
    limpar_dados_automacao,
    montar_comissao_com_preposto,
    montar_pedidos_com_preposto,
    salvar_comissao,
    salvar_itens,
    salvar_pedidos,
)
from excel_colunas import (
    RENOME_COLUNAS_CANONICAS_SUPABASE,
    enriquecer_pedidos_colunas_excel,
    garantir_coluna_sku_por_letra,
    indices_excel_somente_pedidos,
)
from sheets import ler_dados
from utils import tratar_status

COLUNAS_OBRIGATORIAS = ("customer", "store", "customer_name", "order_no", "style", "rsn")


def main() -> None:
    print("Carregando planilhas...")
    df_clientes, df_comissao, df_vendedores, *_ = ler_dados()
    print(f"  dados_clientes: {len(df_clientes)} linhas")
    print(f"  dados_comissao: {len(df_comissao)} linhas")
    print(f"  lista_vendedor: {len(df_vendedores)} linhas")

    if df_clientes.empty:
        raise SystemExit("ERRO: aba dados_clientes vazia")

    headers_orig = list(df_clientes.columns)
    df_clientes = mapear_colunas_clientes(df_clientes)
    alinhar_colunas_extras(df_clientes)
    df_clientes = garantir_coluna_sku_por_letra(df_clientes)

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df_clientes.columns]
    if faltando:
        raise SystemExit(f"ERRO: colunas obrigatorias ausentes: {faltando}")

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
    df_pedidos = enriquecer_pedidos_colunas_excel(
        df_clientes, df_pedidos, headers_orig, indices_excel_somente_pedidos()
    )
    df_pedidos["status_pedido"] = df_pedidos.apply(
        lambda row: tratar_status(row.get("rsn"), row.get("pick_date")),
        axis=1,
    )
    df_pedidos = montar_pedidos_com_preposto(df_pedidos, df_vendedores)
    print(f"Pedidos preparados: {len(df_pedidos)} linhas")
    if "preposto" in df_pedidos.columns:
        print(f"  com preposto: {int(df_pedidos['preposto'].notna().sum())}")
    if "nome_fantasia" in df_pedidos.columns:
        print(f"  com nome_fantasia: {int(df_pedidos['nome_fantasia'].notna().sum())}")

    print("Limpando e gravando pedidos/itens...")
    limpar_dados_automacao()
    pedidos_salvos = salvar_pedidos(df_pedidos)
    print(f"  pedidos inseridos: {len(pedidos_salvos) if pedidos_salvos else 0}")
    salvar_itens(df_clientes)
    print("  itens gravados")

    df_comissao_final = montar_comissao_com_preposto(df_comissao, df_vendedores)
    if "preposto" in df_comissao_final.columns:
        n = int(df_comissao_final["preposto"].notna().sum())
        print(f"Comissao: {len(df_comissao_final)} linhas, preposto preenchido: {n}")
    tabela, qtd = salvar_comissao(df_comissao_final)
    print(f"OK: comissao {qtd} linhas em {tabela!r}")


if __name__ == "__main__":
    main()
