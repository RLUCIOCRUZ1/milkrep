import io
import os
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from database import carregar_vw_pedido_itens

st.set_page_config(page_title="Pedidos", layout="wide")
_logo_env_path = os.getenv("APP_LOGO_PATH", "").strip().replace("\\", "/")
_logo_candidates = [
    _logo_env_path,
    str(Path(__file__).resolve().parents[1] / _logo_env_path) if _logo_env_path else "",
    str(Path(__file__).resolve().parents[1] / "logo.png"),
    str(Path(__file__).resolve().parents[1] / "assets" / "logo.png"),
]
_logo_url = os.getenv("APP_LOGO_URL", "").strip()
_logo_source = _logo_url
if not _logo_source:
    for _logo_path in _logo_candidates:
        if _logo_path and Path(_logo_path).is_file():
            _logo_source = _logo_path
            break
if _logo_source:
    st.logo(_logo_source, size="large")
st.markdown(
    """
<style>
    .block-container {
        max-width: 100%;
        padding-top: 1rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
    div[data-testid="stButton"] > button,
    div[data-testid="stDownloadButton"] > button {
        border-radius: 14px !important;
        border: 1px solid #1e4f8d !important;
        background: linear-gradient(135deg, #0a3f7a 0%, #145ea8 100%) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        box-shadow: 0 8px 20px rgba(10, 63, 122, 0.25) !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease !important;
    }
    div[data-testid="stButton"] > button:hover,
    div[data-testid="stDownloadButton"] > button:hover {
        transform: translateY(-2px) scale(1.01) !important;
        box-shadow: 0 12px 24px rgba(10, 63, 122, 0.35) !important;
        filter: brightness(1.06) !important;
    }
    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(20, 94, 168, 0.12);
    }
    section[data-testid="stSidebar"] [data-testid="stLogo"] img,
    section[data-testid="stSidebar"] .stLogo img {
        max-height: 72px !important;
        height: 72px !important;
        width: auto !important;
    }
    .kpi-card {
        border: 1px solid rgba(20, 94, 168, 0.18);
        border-radius: 14px;
        padding: 12px 14px;
        background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
        box-shadow: 0 8px 20px rgba(10, 63, 122, 0.08);
    }
    .kpi-label {
        color: #3b4a5a;
        font-size: 0.85rem;
        margin-bottom: 2px;
    }
    .kpi-value {
        color: #0a3f7a;
        font-size: 1.25rem;
        font-weight: 700;
        line-height: 1.2;
    }
</style>
""",
    unsafe_allow_html=True,
)
def _excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    buf.seek(0)
    return buf.read()


def _to_float_series(serie: pd.Series) -> pd.Series:
    s = serie.astype(str).str.strip()
    s = s.replace({"": None, "None": None, "nan": None})
    s = s.str.replace(r"[^\d,.\-]", "", regex=True)
    mask_both = s.str.contains(",", na=False) & s.str.contains(r"\.", na=False)
    s.loc[mask_both] = s.loc[mask_both].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    mask_comma = s.str.contains(",", na=False) & ~s.str.contains(r"\.", na=False)
    s.loc[mask_comma] = s.loc[mask_comma].str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _to_datetime_faturamento(serie: pd.Series) -> pd.Series:
    """
    Faz parsing robusto sem warnings de dayfirst:
    - ISO (YYYY-MM-DD): parse direto sem dayfirst
    - demais formatos: parse com dayfirst=True
    """
    s = serie.astype(str).str.strip()
    dt = pd.to_datetime(
        s.where(s.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)),
        errors="coerce",
    )
    faltantes = dt.isna()
    if faltantes.any():
        dt.loc[faltantes] = pd.to_datetime(
            s.loc[faltantes], errors="coerce", dayfirst=True
        )
    return dt


def _format_brl(valor: float) -> str:
    if pd.isna(valor):
        return "R$ 0,00"
    txt = f"{float(valor):,.2f}"
    txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {txt}"


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_view_cache() -> tuple[pd.DataFrame, str]:
    return carregar_vw_pedido_itens()


def _carregar_view(force: bool = False) -> None:
    if force:
        _carregar_view_cache.clear()
    try:
        df_vw, nome_vw = _carregar_view_cache()
        st.session_state["pedidos_vw_df"] = df_vw.copy()
        st.session_state["pedidos_vw_nome"] = nome_vw
        st.session_state.pop("pedidos_vw_erro", None)
    except Exception as e:
        st.session_state["pedidos_vw_erro"] = str(e)


def _aplicar_filtros(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    st.subheader("Filtros")
    c0, c00, c1, c2, c3, c4, c5 = st.columns([0.8, 0.9, 1, 1, 1, 1, 1.2])

    def opcoes(col: str) -> list[str]:
        if col not in df.columns:
            return []
        return sorted(df[col].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist())

    # Evita cópia completa da base em cada rerun (ganho de performance em bases grandes).
    df_filtrado = df
    if "data_faturamento" in df_filtrado.columns:
        dt = _to_datetime_faturamento(df_filtrado["data_faturamento"])
        anos_disp = sorted(dt.dt.year.dropna().astype(int).unique().tolist())
        f_anos = c0.multiselect("Ano", anos_disp)
        meses_disp = list(range(1, 13))
        f_meses = c00.multiselect("Mês", meses_disp)
        if f_anos:
            df_filtrado = df_filtrado[dt.dt.year.isin(f_anos)]
            dt = _to_datetime_faturamento(df_filtrado["data_faturamento"])
        if f_meses:
            df_filtrado = df_filtrado[dt.dt.month.isin(f_meses)]

    f_cnpj = c1.multiselect("CNPJ", opcoes("cnpj"))
    f_nome = c2.multiselect("Nome Fantasia", opcoes("nome_fantasia"))
    f_preposto = c3.multiselect("Preposto", opcoes("preposto"))
    f_desc = c4.multiselect("Descrição Modelo", opcoes("descricao_modelo"))
    pedido_pk_txt = c5.text_input("Pedido_pk")

    if f_cnpj and "cnpj" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["cnpj"].astype(str).isin(f_cnpj)]
    if f_nome and "nome_fantasia" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["nome_fantasia"].astype(str).isin(f_nome)]
    if f_preposto and "preposto" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["preposto"].astype(str).isin(f_preposto)]
    if f_desc and "descricao_modelo" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["descricao_modelo"].astype(str).isin(f_desc)]

    if pedido_pk_txt and "pedido_pk" in df_filtrado.columns:
        ids = [x.strip() for x in pedido_pk_txt.split(",") if x.strip()]
        if ids:
            df_filtrado = df_filtrado[df_filtrado["pedido_pk"].astype(str).isin(ids)]

    return df_filtrado


def _dashboards(df: pd.DataFrame) -> None:
    if df.empty:
        return

    chave_pedido = "pedido_pk" if "pedido_pk" in df.columns else "order_no"
    if chave_pedido not in df.columns:
        return

    base = df.drop_duplicates(subset=[chave_pedido], keep="first").copy()
    base["total_num"] = _to_float_series(base["total"]) if "total" in base.columns else 0
    df_qtd = df.copy()
    df_qtd["quantidade_num"] = _to_float_series(df_qtd["quantidade"]) if "quantidade" in df_qtd.columns else 0

    total_faturado = base["total_num"].sum()
    total_pedidos = int(base["pedido_pk"].nunique()) if "pedido_pk" in base.columns else 0
    total_itens = int(df_qtd["quantidade_num"].fillna(0).sum()) if "quantidade_num" in df_qtd.columns else 0
    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>Total Valor</div><div class='kpi-value'>{_format_brl(total_faturado)}</div></div>",
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>Total de Pedidos</div><div class='kpi-value'>{total_pedidos}</div></div>",
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>Total de Itens</div><div class='kpi-value'>{total_itens}</div></div>",
            unsafe_allow_html=True,
        )

    st.subheader("Tabela / Dashboard Mês/Ano - Faturamento")
    if "data_faturamento" in base.columns:
        base["data_faturamento_dt"] = _to_datetime_faturamento(base["data_faturamento"])
        d1 = (
            base.dropna(subset=["data_faturamento_dt"])
            .assign(mes_ano=lambda x: x["data_faturamento_dt"].dt.strftime("%m/%Y"))
            .groupby("mes_ano", as_index=False)["total_num"]
            .sum()
        )
        if not d1.empty:
            d1_qtd = (
                df_qtd.assign(
                    data_faturamento_dt=_to_datetime_faturamento(df_qtd["data_faturamento"])
                )
                .dropna(subset=["data_faturamento_dt"])
                .assign(mes_ano=lambda x: x["data_faturamento_dt"].dt.strftime("%m/%Y"))
                .groupby("mes_ano", as_index=False)["quantidade_num"]
                .sum()
                .rename(columns={"quantidade_num": "quantidade_mes"})
            )
            d1 = d1.merge(d1_qtd, on="mes_ano", how="left")
            d1["quantidade_mes"] = d1["quantidade_mes"].fillna(0)
            d1["total_em_reais"] = d1["total_num"].map(_format_brl)
            d1["quantidade_fmt"] = d1["quantidade_mes"].map(
                lambda x: f"{int(round(float(x))):,}".replace(",", ".")
            )
            c_mes_tbl, c_mes_chart = st.columns([1, 2])
            with c_mes_tbl:
                st.dataframe(
                    d1[["mes_ano", "total_em_reais", "quantidade_fmt"]].rename(
                        columns={"quantidade_fmt": "quantidade"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            with c_mes_chart:
                chart = (
                    alt.Chart(d1)
                    .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
                    .encode(
                        x=alt.X("mes_ano:N", title="Mês/Ano"),
                        y=alt.Y("total_num:Q", title="Total"),
                        tooltip=[
                            alt.Tooltip("mes_ano:N", title="Mês/Ano"),
                            alt.Tooltip("total_em_reais:N", title="Total"),
                            alt.Tooltip("quantidade_fmt:N", title="Quantidade"),
                        ],
                    )
                )
                st.altair_chart(chart, use_container_width=True)

    c_nf, c_dm = st.columns(2)
    with c_nf:
        st.subheader("Tabela Clientes")
        if "nome_fantasia" in base.columns:
            total_nf = base.groupby("nome_fantasia", as_index=False)["total_num"].sum()
            qtd_nf = df_qtd.groupby("nome_fantasia", as_index=False)["quantidade_num"].sum()
            d2 = total_nf.merge(qtd_nf, on="nome_fantasia", how="left")
            d2 = d2.sort_values("total_num", ascending=False).head(20)
            if not d2.empty:
                d2["total_em_reais"] = d2["total_num"].map(_format_brl)
                d2["soma_quantidade"] = d2["quantidade_num"].fillna(0)
                st.dataframe(
                    d2[["nome_fantasia", "total_em_reais", "soma_quantidade"]],
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )

    with c_dm:
        st.subheader("Tabela Modelos")
        if "descricao_modelo" in base.columns:
            total_dm = base.groupby("descricao_modelo", as_index=False)["total_num"].sum()
            qtd_dm = df_qtd.groupby("descricao_modelo", as_index=False)["quantidade_num"].sum()
            d3 = total_dm.merge(qtd_dm, on="descricao_modelo", how="left")
            d3 = d3.sort_values("total_num", ascending=False).head(20)
            if not d3.empty:
                d3["total_em_reais"] = d3["total_num"].map(_format_brl)
                d3["soma_quantidade"] = d3["quantidade_num"].fillna(0)
                st.dataframe(
                    d3[["descricao_modelo", "total_em_reais", "soma_quantidade"]],
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )


st.title("Pedidos")
st.caption("A automacao roda na pagina inicial `app`.")

if st.button("🔄 Atualizar dados", use_container_width=False):
    _carregar_view(force=True)
else:
    _carregar_view()

if "pedidos_vw_erro" in st.session_state:
    st.error(f"Nao foi possivel carregar a view: {st.session_state['pedidos_vw_erro']}")
elif "pedidos_vw_df" in st.session_state:
    df_vw = st.session_state["pedidos_vw_df"].copy()
    nome_vw = st.session_state.get("pedidos_vw_nome", "vw_pedidos_itens")
    st.caption(f"Fonte dos dados: `{nome_vw}` | Total de linhas: {len(df_vw)}")

    df_filtrado = _aplicar_filtros(df_vw)
    st.caption(f"Linhas apos filtros: {len(df_filtrado)}")
    modo_rapido = st.toggle(
        "⚡ Modo rapido",
        value=True,
        help="Quando ativo, pula os dashboards pesados e acelera abertura da pagina.",
    )
    if not modo_rapido:
        _dashboards(df_filtrado)

    st.subheader("Tabela Dados completo")
    exibir_tabela = st.checkbox(
        "Exibir tabela detalhada",
        value=False,
        help="Desative para acelerar a navegacao quando não precisar visualizar linhas.",
    )
    if exibir_tabela:
        linhas_exibir = st.selectbox(
            "Linhas para exibir na tabela",
            options=[200, 500, 1000, 2000, 5000],
            index=1,
            help="Exibir menos linhas deixa a pagina muito mais rapida.",
        )
        st.dataframe(df_filtrado.head(linhas_exibir), use_container_width=True, height=520)
    st.download_button(
        label="⬇️ Exportar para Excel (.xlsx)",
        data=_excel_bytes(df_filtrado, "vw_pedidos_itens"),
        file_name=f"vw_pedidos_itens_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_vw_pedidos_itens",
    )
