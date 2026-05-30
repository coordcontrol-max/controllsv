#!/usr/bin/env python3
"""Extrato Bancário SUPERMERCADO — por loja (AUTORIZADO DIRETORIA + SALDO PLANILHA).

Fonte: \\10.61.1.102\\exporta\\FINANCEIRO\\CONCILIAÇÃO\\PLANILHA DE CONCILIAÇÃO\\
       2026\\05 - MAIO\\DDMMAA - CONCILIAÇÃO BANCARIA.xlsx
(montado em /mnt/exporta). Um arquivo por dia útil.

Cada arquivo tem aba PAINEL com ~47 blocos (lojas + holdings) no formato:
  • [linha N]    "01-POLEN"
  • [linha N+1]  "AUTORIZADO DIRETORIA"  Banco | Conta | Valor | Destino
  • [linha N+2]  <valor autorizado>      SANTANDER | 13000793-6 | - | ...
  • [linha N+3..]  DEBITATO CC / TARIFAS / OUTROS PAG / PAG TESOURARIA / Dif
  • [linha N+10]  "SALDOS"   "R$ "  "DIFERENÇA"
  • [linha N+11]  "SALDO PLANILHA"   <valor saldo>
  • [linha N+12]  "SALDO CONCINCO"   ...

Saída: extratoBancario/{AAAA-MM} no Firestore (mesma coleção que postos/outras
usam pra pagamentoAutorizado/totalBancos GLOBAIS), mas adicionando porLoja:

  dias[DD] = {
    totalBancos:         <soma sobre lojas>,
    pagamentoAutorizado: <soma sobre lojas>,
    porLoja: {
      "L01": { totalBancos, pagamentoAutorizado },
      "L02": { ... },
      ...
    }
  }

Holdings (997-TIGO, 998-WITHI etc.) entram no porLoja com a tag literal
("L997"/"L998"); cabe ao consumidor (server.js) decidir se ignora.

Uso:
    python3 gera_extrato_supermercados.py [ANO] [MES]   # default = ano/mês corrente
"""
import os
import re
import sys
import warnings
import datetime as dt
import unicodedata
from collections import defaultdict
from openpyxl import load_workbook

warnings.filterwarnings("ignore")

import firebase_admin
from firebase_admin import credentials, firestore

_HERE = os.path.dirname(os.path.abspath(__file__))
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(os.path.join(_HERE, "serviceAccount.json")))
db = firestore.client()

CONC_BASE = "/mnt/exporta/FINANCEIRO/CONCILIAÇÃO/PLANILHA DE CONCILIAÇÃO"
MESES_NOMES = ["01 - JANEIRO", "02 - FEVEREIRO", "03 - MARÇO", "04 - ABRIL",
               "05 - MAIO", "06 - JUNHO", "07 - JULHO", "08 - AGOSTO",
               "09 - SETEMBRO", "10 - OUTUBRO", "11 - NOVEMBRO", "12 - DEZEMBRO"]

# Regex pra extrair dia do nome do arquivo (DDMMAA + sufixo).
RE_DIA = re.compile(r"^(\d{2})(\d{2})(\d{2})\s*-\s*CONCILIA", re.I)
# Regex pra extrair o código L de loja do nome do bloco. Pega tanto "01-POLEN"
# (sem L explícito → vira "L01") quanto "997-TIGO" → "L997".
RE_LOJA = re.compile(r"^\s*L?\s*(\d{1,3})\s*[-–]\s*(.+?)\s*$", re.I)
LBL_AUTORIZ = "AUTORIZADO DIRETORIA"
LBL_SALDO   = "SALDO PLANILHA"


def _norm(s) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return s.upper().strip()


def _num(v) -> float:
    if v is None: return 0.0
    if isinstance(v, (int, float)): return float(v)
    try:
        s = str(v).replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(s) if s else 0.0
    except Exception:
        return 0.0


def _extrai_blocos(ws) -> list[dict]:
    """Lê todos os blocos da aba PAINEL → [{loja, autorizado, saldo}]."""
    blocos = []
    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if not v: continue
            if "AUTORIZADO DIRETOR" not in _norm(v):
                continue
            # nome da loja: 1 linha acima, mesma col
            nome = ws.cell(r - 1, c).value
            # valor autorizado: 1 linha abaixo, mesma col
            autoriz = _num(ws.cell(r + 1, c).value)
            # saldo planilha: procura LBL_SALDO em col mesma, ~10-15 linhas pra baixo
            saldo = 0.0
            for rr in range(r + 5, min(r + 20, ws.max_row + 1)):
                lbl = ws.cell(rr, c).value
                if lbl and "SALDO PLANILHA" in _norm(lbl):
                    saldo = _num(ws.cell(rr, c + 2).value)
                    break
            mat = RE_LOJA.match(str(nome or ""))
            if not mat: continue   # "TOTAL DE OPERAÇÕES" etc.
            loja_num = mat.group(1).lstrip("0") or "0"
            loja_cod = f"L{int(loja_num):02d}"
            blocos.append({"loja": loja_cod, "nome_raw": str(nome).strip(),
                            "autorizado": autoriz, "saldo": saldo})
    return blocos


def _processa_dia(path: str) -> tuple[str | None, dict]:
    """Retorna ('DD', {loja: {totalBancos, pagamentoAutorizado}})."""
    fname = os.path.basename(path)
    mat = RE_DIA.match(fname)
    if not mat: return None, {}
    dd = mat.group(1)
    wb = load_workbook(path, data_only=True)
    if "PAINEL" not in wb.sheetnames: return dd, {}
    blocos = _extrai_blocos(wb["PAINEL"])
    porLoja = {}
    for b in blocos:
        l = b["loja"]
        if l in porLoja:
            porLoja[l]["totalBancos"]         += b["saldo"]
            porLoja[l]["pagamentoAutorizado"] += b["autorizado"]
        else:
            porLoja[l] = {"totalBancos": b["saldo"], "pagamentoAutorizado": b["autorizado"]}
    return dd, porLoja


def gerar(ano: int, mes: int) -> None:
    pasta = os.path.join(CONC_BASE, str(ano), MESES_NOMES[mes - 1])
    if not os.path.isdir(pasta):
        print(f"✗ pasta não existe: {pasta}")
        return
    arquivos = sorted([f for f in os.listdir(pasta)
                       if f.lower().endswith(".xlsx") and not f.startswith("~$")])
    if not arquivos:
        print(f"  (sem arquivos em {pasta})"); return

    # Lê o doc atual (pra preservar dias gerados por outros ETLs).
    chave = f"{ano:04d}-{mes:02d}"
    ref = db.collection("extratoBancario").document(chave)
    doc_atual = ref.get().to_dict() or {}
    dias_atual = doc_atual.get("dias", {}) or {}

    print(f"\n>>> Extrato Supermercado {chave} — {len(arquivos)} arquivo(s)")
    for fname in arquivos:
        path = os.path.join(pasta, fname)
        try:
            dd, porLoja = _processa_dia(path)
        except Exception as e:
            print(f"  ✗ {fname}: {e}"); continue
        if not dd or not porLoja:
            print(f"  ⚠ {fname}: sem dado"); continue
        total_bancos = sum(v["totalBancos"] for v in porLoja.values())
        autoriz_total = sum(v["pagamentoAutorizado"] for v in porLoja.values())
        # mescla com o doc existente: mantém keys que esse ETL não toca; sobrescreve totalBancos/pagamentoAutorizado/porLoja.
        antigo = dias_atual.get(dd, {}) or {}
        dias_atual[dd] = {
            **antigo,
            "totalBancos": round(total_bancos, 2),
            "pagamentoAutorizado": round(autoriz_total, 2),
            "porLoja": {k: {"totalBancos": round(v["totalBancos"], 2),
                              "pagamentoAutorizado": round(v["pagamentoAutorizado"], 2)}
                          for k, v in porLoja.items()},
        }
        print(f"  ✓ dia {dd}: {len(porLoja)} lojas, totalBancos R$ {total_bancos:,.2f}, autorizDir R$ {autoriz_total:,.2f}")

    ref.set({
        "ano": ano, "mes": mes,
        "dias": dias_atual,
        "atualizadoEm": firestore.SERVER_TIMESTAMP,
        "origem": "gera_extrato_supermercados.py (per-loja)",
    }, merge=True)
    print(f"\n✓ extratoBancario/{chave}: {len(dias_atual)} dias gravados")


if __name__ == "__main__":
    hoje = dt.date.today()
    ano = int(sys.argv[1]) if len(sys.argv) > 1 else hoje.year
    mes = int(sys.argv[2]) if len(sys.argv) > 2 else hoje.month
    gerar(ano, mes)
