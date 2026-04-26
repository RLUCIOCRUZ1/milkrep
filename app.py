import io
import logging
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from openpyxl.styles import Font

from colunas import COLUNAS_EXTRAS_PEDIDO, alinhar_colunas_extras, mapear_colunas_clientes
from database import (
    carregar_vw_pedido_itens,
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
from mailer import enviar_email_com_anexo, validar_config_smtp
from sheets import ler_dados, ler_lista_email
from utils import tratar_status

st.set_page_config(page_title="Milkyrep", layout="wide")

logger = logging.getLogger("milkyrep.app")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

# Em produção (Render/Linux), caminhos absolutos do Windows quebram.
# Tenta usar um caminho configurado por variável de ambiente ou arquivos locais conhecidos.
_logo_env_path = os.getenv("APP_LOGO_PATH", "").strip().replace("\\", "/")
_logo_candidates = [
    _logo_env_path,
    str(Path(__file__).resolve().parent / _logo_env_path) if _logo_env_path else "",
    str(Path(__file__).with_name("logo.png")),
    str(Path(__file__).with_name("assets") / "logo.png"),
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
</style>
""",
    unsafe_allow_html=True,
)
COLUNAS_OBRIGATORIAS = ("customer", "store", "customer_name", "order_no", "style", "rsn")
ASSINATURA_EMAIL = (
    "Atenciosamente,\n\n"
    "Maísa Gomes\n"
    "MILKY REPRESENTAÇÕES COMERCIAIS LTDA\n"
    "(62) 3271-1026 / whatsapp 99275-3077"
)


def _to_float_series(serie: pd.Series) -> pd.Series:
    s = serie.astype(str).str.strip()
    s = s.replace({"": None, "None": None, "nan": None})
    s = s.str.replace(r"[^\d,.\-]", "", regex=True)
    mask_both = s.str.contains(",", na=False) & s.str.contains(r"\.", na=False)
    s.loc[mask_both] = (
        s.loc[mask_both]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    mask_comma = s.str.contains(",", na=False) & ~s.str.contains(r"\.", na=False)
    s.loc[mask_comma] = s.loc[mask_comma].str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _format_brl(valor: float) -> str:
    txt = f"{float(valor):,.2f}"
    txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {txt}"


def _format_pecas(valor: float) -> str:
    v = float(valor)
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))} peças"
    txt = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{txt} peças"


def _normalizar_texto(valor: str) -> str:
    txt = unicodedata.normalize("NFKD", str(valor))
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return txt.lower().strip()


def _status_para_resumo(status_original: str) -> tuple[str, int, int]:
    meses = {
        "janeiro": 1,
        "jan": 1,
        "fevereiro": 2,
        "fev": 2,
        "marco": 3,
        "mar": 3,
        "abril": 4,
        "abr": 4,
        "maio": 5,
        "mai": 5,
        "junho": 6,
        "jun": 6,
        "julho": 7,
        "jul": 7,
        "agosto": 8,
        "ago": 8,
        "setembro": 9,
        "set": 9,
        "outubro": 10,
        "out": 10,
        "novembro": 11,
        "nov": 11,
        "dezembro": 12,
        "dez": 12,
    }
    nomes_meses = {
        1: "Janeiro",
        2: "Fevereiro",
        3: "Março",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        7: "Julho",
        8: "Agosto",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }
    texto = str(status_original or "").strip()
    txt_norm = _normalizar_texto(texto)
    if txt_norm.startswith("liberacao"):
        mes_ordem = 99
        for token in txt_norm.split():
            if token in meses:
                mes_ordem = meses[token]
        if mes_ordem != 99:
            return f"Liberação {nomes_meses[mes_ordem]}", 0, mes_ordem
        return "Liberação (Sem mês)", 0, 99
    return texto or "Sem informação", 1, 999


def _montar_resumo_excel(df: pd.DataFrame) -> pd.DataFrame:
    base = df.copy()
    col_status = _resolver_coluna(base, ("status_pedido", "status"))
    col_modelo = _resolver_coluna(base, ("descricao_modelo",))
    col_qtd = _resolver_coluna(base, ("quantidade", "qtd", "quantity"))
    col_valor = _resolver_coluna(base, ("valor", "total", "valor_total"))

    if col_status is None and "rsn" in base.columns:
        base["status_pedido"] = base.apply(
            lambda row: tratar_status(row.get("rsn"), row.get("pick_date")), axis=1
        )
        col_status = "status_pedido"
    if col_status is None:
        base["status_pedido"] = "Sem informação"
        col_status = "status_pedido"

    if col_modelo is None:
        base["descricao_modelo"] = "Sem informação"
        col_modelo = "descricao_modelo"

    if col_qtd:
        base["__qtd_num"] = _to_float_series(base[col_qtd])
    else:
        base["__qtd_num"] = 0

    if col_valor:
        base["__valor_num"] = _to_float_series(base[col_valor])
    else:
        base["__valor_num"] = 0

    status_meta = base[col_status].map(_status_para_resumo)
    base["status_resumo"] = status_meta.map(lambda x: x[0])
    base["grupo_tipo"] = status_meta.map(lambda x: x[1])
    base["ordem_mes"] = status_meta.map(lambda x: x[2])

    status_ordenado = (
        base.groupby("status_resumo", dropna=False, as_index=False)[
            ["__qtd_num", "__valor_num", "grupo_tipo", "ordem_mes"]
        ]
        .agg(
            {
                "__qtd_num": "sum",
                "__valor_num": "sum",
                "grupo_tipo": "min",
                "ordem_mes": "min",
            }
        )
        .rename(columns={"__qtd_num": "quantidade", "__valor_num": "valor"})
        .sort_values(["grupo_tipo", "ordem_mes", "status_resumo"], ascending=True)
    )

    detalhes_modelo = (
        base.groupby(["status_resumo", col_modelo], dropna=False, as_index=False)[
            ["__qtd_num", "__valor_num"]
        ]
        .sum()
        .rename(
            columns={
                col_modelo: "descricao_modelo",
                "__qtd_num": "quantidade",
                "__valor_num": "valor",
            }
        )
        .sort_values(["status_resumo", "valor", "quantidade"], ascending=[True, False, False])
    )

    linhas_resumo: list[dict[str, str]] = []
    for _, row_status in status_ordenado.iterrows():
        status_nome = row_status["status_resumo"]
        linhas_resumo.append(
            {
                "status_pedido": status_nome,
                "quantidade": _format_pecas(row_status["quantidade"]),
                "valor": _format_brl(row_status["valor"]),
            }
        )
        detalhes_status = detalhes_modelo[detalhes_modelo["status_resumo"] == status_nome]
        for row_modelo in detalhes_status.itertuples(index=False):
            nome_modelo = str(row_modelo.descricao_modelo).strip() or "Sem informação"
            linhas_resumo.append(
                {
                    "status_pedido": f"    {nome_modelo}",
                    "quantidade": _format_pecas(row_modelo.quantidade),
                    "valor": _format_brl(row_modelo.valor),
                }
            )
        linhas_resumo.append({"status_pedido": "", "quantidade": "", "valor": ""})

    if linhas_resumo and not linhas_resumo[-1]["status_pedido"]:
        linhas_resumo.pop()

    return pd.DataFrame(linhas_resumo, columns=["status_pedido", "quantidade", "valor"])


def _excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    resumo_df = _montar_resumo_excel(df)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        resumo_df.to_excel(writer, sheet_name="resumo", index=False, startrow=0)
        ws_resumo = writer.book["resumo"]
        fonte_negrito = Font(bold=True)
        # Linha de total/status: texto preenchido e sem indentação inicial.
        for row_idx in range(2, ws_resumo.max_row + 1):
            valor_col_a = ws_resumo.cell(row=row_idx, column=1).value
            if isinstance(valor_col_a, str) and valor_col_a.strip() and not valor_col_a.startswith("    "):
                for col_idx in (1, 2, 3):
                    ws_resumo.cell(row=row_idx, column=col_idx).font = fonte_negrito
    buf.seek(0)
    return buf.read()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def _resolver_coluna(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    mapa = {str(c): _slug(c) for c in df.columns}
    por_slug: dict[str, str] = {}
    for col, n in mapa.items():
        if n not in por_slug:
            por_slug[n] = col
    for alias in aliases:
        col = por_slug.get(_slug(alias))
        if col is not None:
            return col
    return None


def _key_customer(v) -> str | None:
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
    s = re.sub(r"\s+", "", s)
    if re.fullmatch(r"\d+(\.0+)?", s):
        return str(int(float(s)))
    return s.upper()


def _destinatarios(texto: str) -> list[str]:
    if not texto:
        return []
    parts = re.split(r"[;,]", str(texto))
    return [p.strip() for p in parts if p.strip() and "@" in p]


def _saudacao_horario() -> str:
    h = datetime.now().hour
    if h < 12:
        return "Bom dia"
    if h < 18:
        return "Boa tarde"
    return "Boa noite"


def _referencia_cliente(df: pd.DataFrame, customer_chave: str) -> str:
    for coluna_nome in ("nome_fantasia", "customer_name"):
        if coluna_nome not in df.columns:
            continue
        nomes_validos = df[coluna_nome].dropna().map(lambda v: str(v).strip())
        nomes_validos = nomes_validos[
            nomes_validos.map(lambda v: bool(v) and v.lower() not in {"nan", "none"})
        ]
        if not nomes_validos.empty:
            return nomes_validos.iloc[0]
    return f"Customer {customer_chave}"


def _montar_corpo_email(referencia_cliente: str) -> str:
    return (
        f"{_saudacao_horario()},\n\n"
        "Segue em anexo sua carteira Skechers.\n"
        f"Cliente: {referencia_cliente}.\n\n"
        "Qualquer dúvida, estamos à disposição.\n\n"
        f"{ASSINATURA_EMAIL}"
    )


def _enviar_carteiras_email() -> None:
    inicio_exec = time.perf_counter()
    logger.info("Iniciando envio em lote de carteiras por e-mail.")
    ok_cfg, msg_cfg = validar_config_smtp()
    if not ok_cfg:
        logger.error("Config SMTP inválida para envio em lote: %s", msg_cfg)
        st.error(msg_cfg)
        st.info(
            "Para responderem ao e-mail, configure `SMTP_FROM` e `SMTP_REPLY_TO` no .env "
            "com uma caixa real monitorada."
        )
        return

    barra = st.progress(0)
    status = st.empty()

    def avancar(p: int, m: str) -> None:
        barra.progress(max(0, min(100, p)))
        status.caption(f"{p}% - {m}")

    avancar(5, "Lendo lista_email...")
    df_lista, _ = ler_lista_email()
    if df_lista.empty:
        logger.warning("Envio em lote abortado: aba lista_email vazia.")
        st.error("A aba `lista_email` esta vazia.")
        return

    col_customer = _resolver_coluna(df_lista, ("customer", "codigo_cliente", "cliente"))
    col_email = _resolver_coluna(df_lista, ("email", "e_mail", "mail"))
    if not col_customer or not col_email:
        logger.error("Envio em lote abortado: colunas customer/email não encontradas em lista_email.")
        st.error("Nao encontrei as colunas `customer` e `email` na aba `lista_email`.")
        return

    avancar(20, "Carregando vw_pedidos_itens...")
    df_vw, nome_vw = carregar_vw_pedido_itens()
    if df_vw.empty:
        logger.warning("Envio em lote abortado: view %s vazia.", nome_vw)
        st.error(f"A view `{nome_vw}` esta vazia.")
        return

    if "customer" not in df_vw.columns:
        logger.error("Envio em lote abortado: coluna customer ausente na view.")
        st.error("A view nao possui a coluna `customer` para filtrar os dados.")
        return

    df_vw = df_vw.copy()
    df_vw["_key_customer"] = df_vw["customer"].map(_key_customer)

    base_envio = (
        pd.DataFrame(
            {
                "customer": df_lista[col_customer].map(_key_customer),
                "emails": df_lista[col_email].astype(str).str.strip(),
            }
        )
        .dropna(subset=["customer"])
        .drop_duplicates(subset=["customer", "emails"], keep="first")
    )
    base_envio["destinatarios"] = base_envio["emails"].map(_destinatarios)
    base_envio = base_envio[base_envio["destinatarios"].map(bool)]
    if base_envio.empty:
        logger.warning("Envio em lote abortado: nenhum destinatário válido na lista_email.")
        st.error("Nenhum destinatario valido encontrado na aba `lista_email`.")
        return
    logger.info("Envio em lote iniciado com %s customers elegíveis.", len(base_envio))

    hoje = datetime.now().strftime("%d/%m/%Y")
    assunto = f"Carteira Skechers - {hoje}"
    enviados = 0
    sem_dados = 0
    erros: list[str] = []
    total = len(base_envio)

    for i, row in enumerate(base_envio.itertuples(index=False), start=1):
        customer = row.customer
        destinatarios = row.destinatarios
        ini_customer = time.perf_counter()
        progresso = 20 + int((i / max(total, 1)) * 75)
        avancar(progresso, f"Enviando {i}/{total} para customer {customer}...")

        df_cliente = df_vw[df_vw["_key_customer"] == customer].drop(columns=["_key_customer"])
        if df_cliente.empty:
            sem_dados += 1
            logger.info("Customer %s sem dados na view. Pulando.", customer)
            continue

        anexo = _excel_bytes(df_cliente, "vw_pedidos_itens")
        nome_anexo = f"carteira_skechers_{customer}_{datetime.now():%Y%m%d}.xlsx"
        referencia_cliente = _referencia_cliente(df_cliente, customer)
        corpo = _montar_corpo_email(referencia_cliente)
        try:
            logger.info(
                "Enviando customer %s para %s destinatários (%s linhas).",
                customer,
                len(destinatarios),
                len(df_cliente),
            )
            enviar_email_com_anexo(
                destinatarios=destinatarios,
                assunto=assunto,
                corpo_texto=corpo,
                anexo_bytes=anexo,
                anexo_nome=nome_anexo,
            )
            enviados += 1
            logger.info(
                "Envio customer %s concluído em %.2fs.",
                customer,
                time.perf_counter() - ini_customer,
            )
        except Exception as e:
            logger.exception("Falha no envio para customer %s: %s", customer, e)
            erros.append(f"{customer}: {e}")

    avancar(100, "Processo de envio concluido.")
    st.success(
        f"Envio finalizado. Enviados: {enviados} | Sem dados: {sem_dados} | Erros: {len(erros)}"
    )
    if erros:
        st.warning("Falhas:\n- " + "\n- ".join(erros[:10]))
    logger.info(
        "Envio em lote finalizado em %.2fs | enviados=%s | sem_dados=%s | erros=%s",
        time.perf_counter() - inicio_exec,
        enviados,
        sem_dados,
        len(erros),
    )


def _enviar_carteira_por_customer(customer_informado: str) -> None:
    inicio_exec = time.perf_counter()
    logger.info("Iniciando envio por customer: entrada=%s", customer_informado)
    ok_cfg, msg_cfg = validar_config_smtp()
    if not ok_cfg:
        logger.error("Config SMTP inválida para envio por customer: %s", msg_cfg)
        st.error(msg_cfg)
        return

    customer_chave = _key_customer(customer_informado)
    if not customer_chave:
        logger.warning("Envio por customer abortado: customer inválido.")
        st.error("Informe um customer valido para envio.")
        return

    barra = st.progress(0)
    status = st.empty()

    def avancar(p: int, m: str) -> None:
        barra.progress(max(0, min(100, p)))
        status.caption(f"{p}% - {m}")

    avancar(10, "Lendo lista_email...")
    df_lista, _ = ler_lista_email()
    if df_lista.empty:
        logger.warning("Envio por customer abortado: lista_email vazia.")
        st.error("A aba `lista_email` esta vazia.")
        return

    col_customer = _resolver_coluna(df_lista, ("customer", "codigo_cliente", "cliente"))
    col_email = _resolver_coluna(df_lista, ("email", "e_mail", "mail"))
    if not col_customer or not col_email:
        logger.error("Envio por customer abortado: colunas customer/email ausentes.")
        st.error("Nao encontrei as colunas `customer` e `email` na aba `lista_email`.")
        return

    base_envio = pd.DataFrame(
        {
            "customer": df_lista[col_customer].map(_key_customer),
            "destinatarios": df_lista[col_email].map(_destinatarios),
        }
    ).dropna(subset=["customer"])
    base_envio = base_envio[base_envio["destinatarios"].map(bool)]
    base_customer = base_envio[base_envio["customer"] == customer_chave]
    if base_customer.empty:
        logger.warning("Envio por customer abortado: customer %s sem destinatários na lista_email.", customer_chave)
        st.error(
            f"Nao encontrei destinatarios para o customer `{customer_chave}` na aba `lista_email`."
        )
        return

    destinatarios = sorted(
        {d for lista in base_customer["destinatarios"] for d in lista if d.strip()}
    )
    if not destinatarios:
        logger.warning("Envio por customer abortado: customer %s sem e-mails válidos.", customer_chave)
        st.error(
            f"O customer `{customer_chave}` foi encontrado, mas sem e-mails validos para envio."
        )
        return

    avancar(35, "Carregando dados da vw_pedidos_itens...")
    df_vw, nome_vw = carregar_vw_pedido_itens()
    if df_vw.empty:
        logger.warning("Envio por customer abortado: view %s vazia.", nome_vw)
        st.error(f"A view `{nome_vw}` esta vazia para envio.")
        return
    if "customer" not in df_vw.columns:
        logger.error("Envio por customer abortado: coluna customer ausente na view.")
        st.error("A view nao possui a coluna `customer` para filtrar o envio.")
        return

    df_vw = df_vw.copy()
    df_vw["_key_customer"] = df_vw["customer"].map(_key_customer)
    df_customer = df_vw[df_vw["_key_customer"] == customer_chave].drop(columns=["_key_customer"])
    if df_customer.empty:
        logger.warning("Envio por customer abortado: customer %s sem linhas na view.", customer_chave)
        st.error(
            f"Nao encontrei linhas na `vw_pedidos_itens` para o customer `{customer_chave}`."
        )
        return

    avancar(60, "Gerando anexo Excel filtrado por customer...")
    anexo = _excel_bytes(df_customer, "vw_pedidos_itens")

    hoje = datetime.now().strftime("%d/%m/%Y")
    assunto = f"Carteira Skechers - {hoje}"
    referencia_cliente = _referencia_cliente(df_customer, customer_chave)
    corpo = _montar_corpo_email(referencia_cliente)

    avancar(85, f"Enviando carteira para customer {customer_chave}...")
    try:
        logger.info(
            "Enviando customer %s para %s destinatários (%s linhas).",
            customer_chave,
            len(destinatarios),
            len(df_customer),
        )
        enviar_email_com_anexo(
            destinatarios=destinatarios,
            assunto=assunto,
            corpo_texto=corpo,
            anexo_bytes=anexo,
            anexo_nome=f"carteira_skechers_{customer_chave}_{datetime.now():%Y%m%d_%H%M}.xlsx",
        )
    except Exception as e:
        logger.exception("Falha no envio por customer %s: %s", customer_chave, e)
        st.error(f"Falha no envio da carteira para customer `{customer_chave}`: {e}")
        return

    avancar(100, "Envio concluido.")
    st.success(
        f"Carteira enviada com sucesso para o customer `{customer_chave}` "
        f"({len(destinatarios)} destinatario(s), {len(df_customer)} linha(s))."
    )
    logger.info(
        "Envio por customer finalizado em %.2fs para %s.",
        time.perf_counter() - inicio_exec,
        customer_chave,
    )


def _executar_automacao_completa() -> None:
    barra = st.progress(0)
    status = st.empty()

    def avancar(percentual: int, msg: str) -> None:
        barra.progress(max(0, min(100, percentual)))
        status.caption(f"{percentual}% - {msg}")

    avancar(5, "Iniciando automacao...")

    (
        df_clientes,
        df_comissao,
        df_vendedores,
        _aba_clientes,
        _aba_comissao,
        _aba_vendedores,
    ) = ler_dados()
    avancar(20, "Planilhas carregadas.")

    if df_clientes.empty:
        st.error("A aba dados_clientes esta vazia ou sem linhas de dados.")
        return

    headers_orig = list(df_clientes.columns)
    df_clientes = mapear_colunas_clientes(df_clientes)
    alinhar_colunas_extras(df_clientes)
    df_clientes = garantir_coluna_sku_por_letra(df_clientes)
    avancar(35, "Colunas mapeadas e normalizadas.")

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df_clientes.columns]
    if faltando:
        st.error(
            "Nao foi possivel identificar estas colunas na planilha: "
            + ", ".join(faltando)
        )
        return

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
    avancar(55, "Dados de pedidos preparados.")

    limpar_dados_automacao()
    avancar(70, "Tabelas limpas.")
    salvar_pedidos(df_pedidos)
    avancar(82, "Pedidos gravados.")
    salvar_itens(df_clientes)
    avancar(90, "Itens gravados.")

    df_comissao_final = montar_comissao_com_preposto(df_comissao, df_vendedores)
    tabela_comissao, qtd_comissao = salvar_comissao(df_comissao_final)
    avancar(100, "Comissionamento atualizado.")

    st.success(
        "Automacao concluida com sucesso. "
        f"Comissao: {qtd_comissao} linhas em `{tabela_comissao}`."
    )


st.title("Milkyrep")
st.caption("Central de automacao e navegacao do projeto.")

if st.button("🚀 Rodar automacao completa (Pedidos + Comissao)", use_container_width=True):
    _executar_automacao_completa()

if st.button("📧 Enviar carteira por e-mail (lista_email)", use_container_width=True):
    _enviar_carteiras_email()

st.subheader("Envio por Customer")
customer_envio = st.text_input(
    "Customer para envio",
    value="",
    help="Informe o customer. O sistema busca os e-mails na aba `lista_email`, filtra os dados e envia a carteira.",
)
if st.button("🧪 Enviar carteira por customer", use_container_width=True):
    _enviar_carteira_por_customer(customer_envio)

st.subheader("Navegação")
c1, c2 = st.columns(2)
with c1:
    if st.button("📦 Ir para Pedidos", use_container_width=True):
        st.switch_page("pages/1_Pedidos.py")
with c2:
    if st.button("💰 Ir para Comissionamento", use_container_width=True):
        st.switch_page("pages/2_Comissionamento.py")
