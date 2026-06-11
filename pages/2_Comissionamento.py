import io
import os
import re
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from comissao_colunas import preparar_comissao_para_exibicao
from database import carregar_comissionamento

st.set_page_config(page_title="Comissionamento", layout="wide")
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
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] img {
        margin-bottom: 12px;
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


@st.cache_data(ttl=300, show_spinner=False)
def _carregar_cache() -> tuple[pd.DataFrame, str]:
    df, nome = carregar_comissionamento()
    return df, nome


def _atualizar_cache_comissionamento() -> None:
    _carregar_cache.clear()


def _carregar() -> tuple[pd.DataFrame, str, str | None]:
    try:
        df, nome = _carregar_cache()
        return df, nome, None
    except Exception as e:
        return pd.DataFrame(), "", str(e)


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


def _to_datetime_vencto(serie: pd.Series) -> pd.Series:
    s = serie.astype(str).str.strip()
    dt = pd.to_datetime(
        s.where(s.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)),
        errors="coerce",
    )
    faltantes = dt.isna()
    if faltantes.any():
        dt.loc[faltantes] = pd.to_datetime(s.loc[faltantes], errors="coerce", dayfirst=True)
    return dt


def _format_brl(valor: float) -> str:
    if pd.isna(valor):
        return "R$ 0,00"
    txt = f"{float(valor):,.2f}"
    txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {txt}"


def _opcoes(df_base: pd.DataFrame, col: str) -> list[str]:
    if col not in df_base.columns:
        return []
    return sorted(
        df_base[col]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )


def _normalizar_doc_exibicao(df: pd.DataFrame) -> pd.DataFrame:
    if "doc" not in df.columns or df.empty:
        return df
    out = df.copy()

    def _norm(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        s = str(v).strip()
        if not s:
            return None
        s_num = re.sub(r"[^\d,.\-]", "", s)
        if s_num:
            try:
                s_aux = s_num
                if "," in s_aux and "." in s_aux:
                    if s_aux.rfind(",") > s_aux.rfind("."):
                        s_aux = s_aux.replace(".", "").replace(",", ".")
                    else:
                        s_aux = s_aux.replace(",", "")
                elif "," in s_aux:
                    s_aux = s_aux.replace(".", "").replace(",", ".")
                n = float(s_aux)
                if n.is_integer():
                    return str(int(n))
            except Exception:
                pass
        s = s.replace(".", "").replace(",", "")
        s = re.sub(r"\s+", "", s)
        return s or None

    out["doc"] = out["doc"].map(_norm)
    return out


def _preparar_dashboard(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    base = df.copy()
    if "previsao" in base.columns:
        base["previsao_num"] = _to_float_series(base["previsao"])
    else:
        base["previsao_num"] = 0.0
    if "dt_vencto" in base.columns:
        base["dt_vencto_dt"] = _to_datetime_vencto(base["dt_vencto"])
        base["ano_vencto"] = base["dt_vencto_dt"].dt.year
        base["mes_vencto"] = base["dt_vencto_dt"].dt.month
        base["mes_ano_vencto"] = base["dt_vencto_dt"].dt.strftime("%m/%Y")
    return base


def _aplicar_filtros(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    st.subheader("Filtros")
    c1, c2, c3, c4, c5 = st.columns(5)

    df_filtrado = df
    dt = df_filtrado["dt_vencto_dt"] if "dt_vencto_dt" in df_filtrado.columns else pd.Series(dtype="datetime64[ns]")

    anos_disp = sorted(dt.dt.year.dropna().astype(int).unique().tolist()) if not dt.empty else []
    f_anos = c4.multiselect("Ano", anos_disp)
    f_meses = c5.multiselect("Mês", list(range(1, 13)))
    if f_anos and "ano_vencto" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["ano_vencto"].isin(f_anos)]
    if f_meses and "mes_vencto" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["mes_vencto"].isin(f_meses)]

    f_preposto = c1.multiselect("Preposto", _opcoes(df_filtrado, "preposto"))
    if f_preposto and "preposto" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["preposto"].astype(str).isin(f_preposto)]

    f_grupo = c2.multiselect("Grupo", _opcoes(df_filtrado, "grupo"))
    if f_grupo and "grupo" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["grupo"].astype(str).isin(f_grupo)]

    f_invoice = c3.multiselect("Invoice", _opcoes(df_filtrado, "invoice"))
    if f_invoice and "invoice" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["invoice"].astype(str).isin(f_invoice)]

    return df_filtrado


def _dashboard(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nenhum dado para exibir com os filtros selecionados.")
        return

    total_previsao = float(df["previsao_num"].fillna(0).sum())
    qtd_titulos = len(df)

    k1, k2 = st.columns(2)
    with k1:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>Total Valor Previsão</div>"
            f"<div class='kpi-value'>{_format_brl(total_previsao)}</div></div>",
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>Títulos no filtro</div>"
            f"<div class='kpi-value'>{qtd_titulos}</div></div>",
            unsafe_allow_html=True,
        )

    st.subheader("Previsão por Preposto")
    if "preposto" in df.columns:
        por_preposto = (
            df.groupby("preposto", as_index=False)
            .agg(valor_previsao=("previsao_num", "sum"), titulos=("previsao_num", "count"))
            .sort_values("valor_previsao", ascending=False)
        )
        por_preposto["valor_previsao_fmt"] = por_preposto["valor_previsao"].map(_format_brl)
        c_tbl, c_chart = st.columns([1, 2])
        with c_tbl:
            st.dataframe(
                por_preposto[["preposto", "valor_previsao_fmt", "titulos"]].rename(
                    columns={
                        "preposto": "Preposto",
                        "valor_previsao_fmt": "Valor Previsão",
                        "titulos": "Títulos",
                    }
                ),
                use_container_width=True,
                hide_index=True,
                height=360,
            )
        with c_chart:
            chart_preposto = (
                alt.Chart(por_preposto)
                .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
                .encode(
                    x=alt.X("preposto:N", title="Preposto", sort="-y"),
                    y=alt.Y("valor_previsao:Q", title="Valor Previsão"),
                    tooltip=[
                        alt.Tooltip("preposto:N", title="Preposto"),
                        alt.Tooltip("valor_previsao_fmt:N", title="Valor Previsão"),
                        alt.Tooltip("titulos:Q", title="Títulos"),
                    ],
                )
            )
            st.altair_chart(chart_preposto, use_container_width=True)

    st.subheader("Previsão por Mês/Ano (Dt. Vencto)")
    if "mes_ano_vencto" in df.columns:
        por_mes = (
            df.dropna(subset=["mes_ano_vencto", "dt_vencto_dt"])
            .groupby("mes_ano_vencto", as_index=False)
            .agg(
                valor_previsao=("previsao_num", "sum"),
                titulos=("previsao_num", "count"),
                ordem=("dt_vencto_dt", "min"),
            )
            .sort_values("ordem")
            .drop(columns=["ordem"])
        )
        if not por_mes.empty:
            por_mes["valor_previsao_fmt"] = por_mes["valor_previsao"].map(_format_brl)
            c_mes_tbl, c_mes_chart = st.columns([1, 2])
            with c_mes_tbl:
                st.dataframe(
                    por_mes[["mes_ano_vencto", "valor_previsao_fmt", "titulos"]].rename(
                        columns={
                            "mes_ano_vencto": "Mês/Ano",
                            "valor_previsao_fmt": "Valor Previsão",
                            "titulos": "Títulos",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            with c_mes_chart:
                chart_mes = (
                    alt.Chart(por_mes)
                    .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
                    .encode(
                        x=alt.X("mes_ano_vencto:N", title="Mês/Ano", sort=None),
                        y=alt.Y("valor_previsao:Q", title="Valor Previsão"),
                        tooltip=[
                            alt.Tooltip("mes_ano_vencto:N", title="Mês/Ano"),
                            alt.Tooltip("valor_previsao_fmt:N", title="Valor Previsão"),
                            alt.Tooltip("titulos:Q", title="Títulos"),
                        ],
                    )
                )
                st.altair_chart(chart_mes, use_container_width=True)
        else:
            st.info("Sem datas de vencimento válidas para agrupar por mês/ano.")


st.title("Comissionamento")
st.caption("A automacao roda na pagina inicial `app`.")
if st.button("🔄 Atualizar dados", use_container_width=False):
    _atualizar_cache_comissionamento()

df, nome_origem, erro = _carregar()
if erro:
    st.error(f"Nao foi possivel carregar comissionamento: {erro}")
else:
    df = _normalizar_doc_exibicao(df)
    df_base = _preparar_dashboard(df)
    st.caption(f"Fonte dos dados: `{nome_origem}` | Total de linhas: {len(df)}")

    st.subheader("Dashboard")
    df_filtrado = _aplicar_filtros(df_base)
    _dashboard(df_filtrado)

    st.divider()
    df_exibir = preparar_comissao_para_exibicao(df_filtrado)
    exibir_tabela = st.checkbox(
        "Exibir tabela detalhada",
        value=False,
        help="Desative para acelerar a pagina quando não precisar visualizar linhas.",
    )
    if exibir_tabela:
        linhas_exibir = st.selectbox(
            "Linhas para exibir na tabela",
            options=[200, 500, 1000, 2000, 5000],
            index=1,
        )
        st.dataframe(df_exibir.head(linhas_exibir), use_container_width=True, height=520)
    st.download_button(
        label="Exportar comissionamento para Excel (.xlsx)",
        data=_excel_bytes(df_exibir, nome_origem or "comissionamento"),
        file_name=f"comissionamento_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
