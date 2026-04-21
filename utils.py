import pandas as pd

def _tem_valor(v) -> bool:
    if v is None:
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and not v.strip():
        return False
    return True


def traduzir_mes(numero):
    meses = {
        "01": "Janeiro", "02": "Fevereiro", "03": "Março",
        "04": "Abril", "05": "Maio", "06": "Junho",
        "07": "Julho", "08": "Agosto", "09": "Setembro",
        "10": "Outubro", "11": "Novembro", "12": "Dezembro"
    }
    return meses.get(numero, numero)


MESES_ABREV_PT = {
    "JAN": "Janeiro", "FEV": "Fevereiro", "MAR": "Março",
    "ABR": "Abril", "MAI": "Maio", "JUN": "Junho",
    "JUL": "Julho", "AGO": "Agosto", "SET": "Setembro",
    "OUT": "Outubro", "NOV": "Novembro", "DEZ": "Dezembro",
}


def tratar_status(valor, pick_date=None):
    # Regra de negócio: sem RSN, mas com pick_date preenchido = em separação.
    if not _tem_valor(valor):
        if _tem_valor(pick_date):
            return "em_separação"
        return "Sem informação"

    valor = str(valor).upper().strip()

    # ****** (sem previsão)
    if "*****" in valor:
        return "Sem previsão de chegada"

    # INVT
    if "INVT" in valor:
        return "Disponível para faturar"

    # BULK
    if "BULK" in valor:
        return "Faturamento imediato"

    # WAITING / WAITIN (planilha ou coluna curta costuma vir truncado)
    if valor.startswith("WAITIN"):
        return "Disponível para faturar"

    # Lmes/ano
    if valor.startswith("L"):
        try:
            mes = valor[1:3]
            ano = valor[4:]
            return f"Previsão de chegada {traduzir_mes(mes)} / {ano}"
        except:
            return "Previsão indefinida"

    # Data com barra: MAI/30 ou 03/15 → "Liberação 30 Maio"
    if "/" in valor:
        try:
            p1, p2 = valor.split("/", 1)
            p1, p2 = p1.strip(), p2.strip()
            if p1 in MESES_ABREV_PT and p2.isdigit():
                return f"Liberação {int(p2)} {MESES_ABREV_PT[p1]}"
            if p1.isdigit() and p2.isdigit():
                mes = p1.zfill(2)
                return f"Liberação {int(p2)} {traduzir_mes(mes)}"
        except (ValueError, TypeError):
            pass

    return "Não identificado"