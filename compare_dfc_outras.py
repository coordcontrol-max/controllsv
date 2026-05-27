#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comparador: DFC OUTRAS direto do LUMI (MySQL) × JSON gabarito (Excel atual).

Saídas  = TITULO TIPO 4, por DTLIQUIDA, valor -VLPAGO.
Entradas= TITULO TIPO 9, por VENCIMENTO (DTLIQUIDA vazio), valor +VLPAGO.
Classificação de linha = natureza do TABMOVTO (melhor-prefixo no HISTORICO/DESCRICAO)
mapeada para a linha amigável da DFC. EMPRE2 = "Transferencia Bancaria" (pragmático).
Imprime, por mês, linha a linha: GABARITO | LUMI | DIFF.
"""
import os, json, glob, pymysql
from collections import defaultdict

LUMI = dict(host="10.17.0.100", port=3306, user="sac",
            password=os.environ["LUMI_PW"], db="SAC",
            connect_timeout=8, charset="utf8mb4")

# natureza (TABMOVTO.DESCRICAO) -> linha amigável da DFC
NAT2LINE = {
    "AGUA": "Agua", "ALUG": "Aluguel", "ALUGREC": "Recebmto de Aluguéis",
    "ENERGI": "Energia Eletrica", "INSS": "INSS", "FGTS": "FGTS",
    "PIS": "PIS", "COFINS": "COFINS",
    "IRPJ": "Impostos Federais Pagos", "CSLL": "Impostos Federais Pagos",
    "IRRF": "Impostos Federais Pagos", "IRPF": "Impostos Federais Pagos",
    "DAS": "Impostos Federais Pagos", "ISS": "Impostos Federais Pagos",
    "NPRVPA": "Impostos Federais Pagos", "ICMSPA": "Imposto",
    "IPTU": "IPTU", "ITBI": "ITBI", "IPVA": "Imposto",
    "ORDSAL": "Salarios", "ADIASAL": "Salarios", "VALETR": "Salarios", "RECISAO": "Salarios",
    "BONUS": "Premiação/Bonus", "CONT": "Honorarios Contabeis",
    "INFOLI": "Licença De Software", "PLANO": "Plano de Saúde",
    "SEGURV": "Seguro Veicular", "SERVT": "Serviços De Terceiros", "SERVTS": "Segurança",
    "TARBAN": "Despesa Bancária", "TAXADM": "Taxas Administrativas",
    "IMOV": "Investimento Compra De Imoveis", "AQUISE": "Investimento Compra De Equipamentos",
    "LOGFIN": "Aquisição e Financiamento de Veículos", "LOGV": "Aquisição e Financiamento de Veículos",
    "EMPRES": "Mútuo a Pagar (Entre Grupos)", "EMPREC": "Mútuos a Receber",
    "MUTUO A PAGAR": "Mútuo a Pagar (Entre Grupos)", "MUTUO A RECEBER": "Mútuos a Receber",
    "EMPRE2": "Transferencia Bancaria", "TED/DOC": "Transferencia Bancaria",
    "DUPP": "Despesas Gerais", "DESPU": "Material De Uso E Consumo",
    "DIRET": "Socio 30", "DIRET2": "Socio 30", "DIRET3": "Socio 30", "DIRET4": "Socio 30",
    "CUSCOR": "Outras Despesas", "IMPCC": "Outras Despesas", "CONVFA": "Outras Despesas",
    "INCOMP": "Outras Despesas", "CUSTJU": "Outras Despesas", "ADIAFO": "Outras Despesas",
}

def load_gabarito():
    gab = defaultdict(lambda: defaultdict(float))  # mes -> {linha: v}
    for f in sorted(glob.glob("dados_fluxo_outras/2026-0[1-4].json")):
        d = json.load(open(f)); mes = d["mes"]; linhas = d["dim"]["linhas"]
        for e in d["porLinha"]:
            if e["d"] == 0:
                gab[mes][linhas[e["n"]]] += e["v"]
    return gab

def lumi_por_linha():
    conn = pymysql.connect(**LUMI); cur = conn.cursor()
    cur.execute("SELECT REGISTRO,TRIM(DESCRICAO),TRIM(HISTORICO) FROM TABMOVTO")
    tab = cur.fetchall()
    def nat(h):
        h = (h or "").upper(); best=None; bl=-1
        for reg, desc, hist in tab:
            for k in (hist, desc):
                k = (k or "").upper().strip()
                if k and h.startswith(k) and len(k) > bl: best=desc; bl=len(k)
        return best
    out = defaultdict(lambda: defaultdict(float))   # mes -> {linha: v}
    unmapped = defaultdict(float)
    # saídas
    cur.execute("""SELECT LEFT(DTLIQUIDA,6),VLPAGO,TRIM(HISTORICO) FROM TITULO
                   WHERE TIPO=4 AND DTLIQUIDA>='20260101' AND DTLIQUIDA<'20270101' AND VLPAGO>0""")
    for ym, vlpago, h in cur.fetchall():
        n = nat(h); linha = NAT2LINE.get(n, "Outras Despesas")
        if n not in NAT2LINE: unmapped[n or "(?)"] -= float(vlpago)
        out[int(ym[4:6])][linha] -= float(vlpago)
    # entradas
    cur.execute("""SELECT LEFT(VENCIMENTO,6),VLPAGO,TRIM(HISTORICO) FROM TITULO
                   WHERE TIPO=9 AND VENCIMENTO>='20260101' AND VENCIMENTO<'20270101' AND VLPAGO>0""")
    for ym, vlpago, h in cur.fetchall():
        n = nat(h); linha = NAT2LINE.get(n, "Outras Receitas")
        if n not in NAT2LINE: unmapped[n or "(?)"] += float(vlpago)
        out[int(ym[4:6])][linha] += float(vlpago)
    conn.close()
    return out, unmapped

def main():
    gab = load_gabarito(); lumi, unmapped = lumi_por_linha()
    for mes in sorted(gab):
        linhas = sorted(set(gab[mes]) | set(lumi[mes]),
                        key=lambda l: -abs(gab[mes].get(l, 0) or lumi[mes].get(l, 0)))
        print(f"\n================== MÊS {mes:02d} ==================")
        print(f"{'LINHA':<38}{'GABARITO':>16}{'LUMI':>16}{'DIFF':>16}")
        tg = tl = 0.0
        for l in linhas:
            g = gab[mes].get(l, 0.0); v = lumi[mes].get(l, 0.0); tg += g; tl += v
            flag = "" if abs(g - v) < 1 else ("  <<" if abs(g - v) > 1000 else "  <")
            print(f"{l:<38}{g:>16,.2f}{v:>16,.2f}{g-v:>16,.2f}{flag}")
        print(f"{'TOTAL':<38}{tg:>16,.2f}{tl:>16,.2f}{tg-tl:>16,.2f}")
    if unmapped:
        print("\n##### NATUREZAS NÃO MAPEADAS (caíram em Outras) #####")
        for n, v in sorted(unmapped.items(), key=lambda x: -abs(x[1])):
            print(f"   {v:>14,.2f}  {n}")

if __name__ == "__main__":
    main()
