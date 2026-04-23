import json
import os

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _headers_unicos(headers):
    novos_headers = []
    contagem = {}
    for h in headers:
        if h in contagem:
            contagem[h] += 1
            novos_headers.append(f"{h}_{contagem[h]}")
        else:
            contagem[h] = 1
            novos_headers.append(h)
    return novos_headers


def conectar():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if creds_json:
        creds_info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            "credenciais.json",
            scopes=SCOPES
        )
    client = gspread.authorize(creds)
    return client

def ler_dados():
    client = conectar()

    SPREADSHEET_ID = "1faq_Zxtm8Qs7nenLDCLdQmpsqj-34wVvmCLywcFe55I"

    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    aba_clientes = spreadsheet.worksheet("dados_clientes")
    aba_comissao = spreadsheet.worksheet("dados_comissao")
    aba_vendedores = spreadsheet.worksheet("lista_vendedor")

    raw_cli = aba_clientes.get_all_values()
    if not raw_cli:
        df_clientes = pd.DataFrame()
    else:
        h_cli = _headers_unicos(raw_cli[0])
        df_clientes = pd.DataFrame(raw_cli[1:], columns=h_cli)

    dados = aba_comissao.get_all_values()
    if dados and dados[0]:
        headers = dados[0]
        linhas = dados[1:]
        df_comissao = pd.DataFrame(linhas, columns=_headers_unicos(headers))
    else:
        df_comissao = pd.DataFrame()

    dados_vendedores = aba_vendedores.get_all_values()
    if dados_vendedores and dados_vendedores[0]:
        headers_v = dados_vendedores[0]
        linhas_v = dados_vendedores[1:]
        df_vendedores = pd.DataFrame(linhas_v, columns=_headers_unicos(headers_v))
    else:
        df_vendedores = pd.DataFrame()

    return (
        df_clientes,
        df_comissao,
        df_vendedores,
        aba_clientes,
        aba_comissao,
        aba_vendedores,
    )


def ler_lista_email():
    client = conectar()
    spreadsheet = client.open_by_key("1faq_Zxtm8Qs7nenLDCLdQmpsqj-34wVvmCLywcFe55I")
    aba = spreadsheet.worksheet("lista_email")
    dados = aba.get_all_values()
    if dados and dados[0]:
        headers = _headers_unicos(dados[0])
        linhas = dados[1:]
        return pd.DataFrame(linhas, columns=headers), aba
    return pd.DataFrame(), aba