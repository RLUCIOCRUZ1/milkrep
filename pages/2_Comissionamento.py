import io
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

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
    st.logo(_logo_source)
    st.sidebar.image(_logo_source, use_container_width=True)
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
            # Converte valores como 370.380,00 para inteiro sem separadores.
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


st.title("Comissionamento")
st.caption("A automacao roda na pagina inicial `app`.")
if st.button("🔄 Atualizar dados", use_container_width=False):
    _atualizar_cache_comissionamento()

df, nome_origem, erro = _carregar()
if erro:
    st.error(f"Nao foi possivel carregar comissionamento: {erro}")
else:
    df = _normalizar_doc_exibicao(df)
    st.caption(f"Fonte dos dados: `{nome_origem}` | Total de linhas: {len(df)}")
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
        st.dataframe(df.head(linhas_exibir), use_container_width=True, height=520)
    st.download_button(
        label="Exportar comissionamento para Excel (.xlsx)",
        data=_excel_bytes(df, nome_origem or "comissionamento"),
        file_name=f"comissionamento_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
