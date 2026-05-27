#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL — Títulos em Aberto dos POSTOS (A Pagar e A Receber), fonte Adaptive.

Lê os exports da Consulta SQL do Petros (OLE2 .xls disfarçado de .xlsx →
lê-se com xlrd, NÃO openpyxl):
  - TITABERTO*pagar*.xlsx     (pagar_receber=1, título a título)
  - TITABERTO*RECEBER*.xlsx   (pagar_receber=2; cartão vem AGREGADO)

Gera dados_dre_postos_adaptive/titulos_aberto_{ano}.json no formato que a
tela "Títulos em Aberto · Postos" consome:
  dados[<codigo>][PAGAR|RECEBER] = {
     total, vencido, vence_hoje, a_vencer, qtd,
     aging: {a_vencer, d1_30, d31_60, d61_90, d90},
     porNatureza: {nat: {total, vencido, vence_hoje, a_vencer, qtd}},
     titulos: [ {titulo,parcela,pessoa,natureza,dt_emissao,dt_venc,
                 vl_original,vl_aberto,dias,situacao,obs,agregado,qtd} ]
  }

Aceita tanto o export NOVO (colunas posto=codigo + posto_nome) quanto o
ANTIGO (posto = id_empresa numérico → mapeado por ID_MAP).

Uso: python3 etl_titulos_aberto.py
"""
import os, sys, glob, json, datetime as dt
import xlrd

EXPORT_DIRS = [
    "/mnt/controller/03 - POSTOS/Automate",
    "/mnt/c/Users/wesley/Downloads",
]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_dre_postos_adaptive")

# Fallback p/ export antigo (coluna posto = id_empresa numérico) → codigo + nome
ID_MAP = {
    1:         ("001", "AUTO POSTO VS COMERCIAL DE COMBUSTIVEL LTDA"),
    10482193:  ("002", "AUTO POSTO IRMAOS PACIFICOS LTDA"),
    62803617:  ("003", "AUTO POSTO CIDADE OCIDENTAL LTDA - ME"),
    106823750: ("004", "AUTO POSTO INFINITO LTDA"),
    128348475: ("005", "AUTO POSTO RIACHO FUNDO 02 COMERCIAL DE COMBUSTIVEIS LTDA"),
    136594463: ("006", "AUTO POSTO SAMAMBAIA LTDA"),
    138111312: ("007", "AUTO POSTO EPTG COMERCIAL DE COMBUSTIVEIS LTDA"),
    218683007: ("008", "AUTO POSTO SM COMBUSTIVEIS LTDA"),
    281287885: ("009", "SETOR SUL COMERCIO DE COMBUSTIVEIS LTDA"),
    279354826: ("010", "GM CENTRAL COMERCIO DE COMBUSTIVEIS LTDA"),
    292600011: ("011", "AUTO POSTO SAO SEBASTIAO LTDA"),
}

# Naturezas que NÃO são título em aberto real (movimento interno / antecipações).
EXCLUIR = {
    "Diferença de Caixa Negativa", "Diferença de Caixa Positiva",
    "Pagamento Antecipado", "Baixa de Pagamento Antecipado",
}


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _int(v):
    n = _num(v)
    return int(n) if n is not None else None


def _data_iso(cell, datemode):
    if cell is None or cell == "":
        return ""
    if isinstance(cell, (int, float)):
        if cell <= 0:
            return ""
        try:
            return xlrd.xldate.xldate_as_datetime(cell, datemode).strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = str(cell).strip()
    import re
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return m.group(0) if m else ""


def achar(dirs, *needles):
    """Acha o .xls(x) mais recente cujo nome contém TODOS os needles (case-insensitive)."""
    ok = []
    for folder in dirs:
        if not os.path.isdir(folder):
            continue
        for pat in ("*.xls", "*.xlsx"):
            for c in glob.glob(os.path.join(folder, pat)):
                b = os.path.basename(c).upper()
                if b.startswith("~$"):
                    continue
                if all(n.upper() in b for n in needles):
                    ok.append(c)
    return max(ok, key=os.path.getmtime) if ok else None


def _resolve_posto(row, H):
    """Retorna (codigo, nome) lidando com export novo (codigo+nome) e antigo (id)."""
    raw = row[H["posto"]] if H.get("posto") is not None else None
    nome = ""
    if H.get("posto_nome") is not None:
        nome = str(row[H["posto_nome"]]).strip()
    # codigo: se posto for número grande (id_empresa) usa o mapa; se for 1..11 ou "001" usa direto
    cod = None
    if isinstance(raw, (int, float)):
        iv = int(raw)
        if iv in ID_MAP:
            cod, nm = ID_MAP[iv]
            nome = nome or nm
        elif 1 <= iv <= 99:
            cod = f"{iv:03d}"
        else:
            cod = str(iv)
    else:
        s = str(raw).strip()
        cod = s.zfill(3) if s.isdigit() else s
    return cod or "?", (nome or cod or "?")


def parse(path, tipo):
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    H = {str(sh.cell_value(0, c)).strip().lower(): c for c in range(sh.ncols)}
    out = []   # (codigo, nome, registro)
    for r in range(1, sh.nrows):
        row = [sh.cell_value(r, c) for c in range(sh.ncols)]
        nat = str(row[H["natureza"]]).strip() if H.get("natureza") is not None else ""
        if not nat or nat in EXCLUIR:
            continue
        vab = _num(row[H["vl_aberto"]]) or 0.0 if H.get("vl_aberto") is not None else 0.0
        if abs(vab) < 0.005:
            continue
        cod, nome = _resolve_posto(row, H)
        if cod == "?":
            continue
        situ = str(row[H["situacao"]]).strip().upper() if H.get("situacao") is not None else "A VENCER"
        dias = _int(row[H["dias_atraso"]]) or 0 if H.get("dias_atraso") is not None else 0
        agg = (_int(row[H["agregado"]]) or 0) if H.get("agregado") is not None else 0
        parc = str(row[H["parcela"]]).strip() if H.get("parcela") is not None else ""
        qtd = (_int(parc) or 1) if agg else 1
        reg = {
            "titulo": str(row[H["titulo"]]).strip() if H.get("titulo") is not None else "",
            "parcela": parc,
            "pessoa": str(row[H["pessoa"]]).strip() if H.get("pessoa") is not None else "",
            "natureza": nat,
            "dt_emissao": _data_iso(row[H["dt_emissao"]], wb.datemode) if H.get("dt_emissao") is not None else "",
            "dt_venc": _data_iso(row[H["dt_vencimento"]], wb.datemode) if H.get("dt_vencimento") is not None else "",
            "vl_original": round(_num(row[H["vl_original"]]) or 0.0, 2) if H.get("vl_original") is not None else 0.0,
            "vl_aberto": round(vab, 2),
            "dias": dias,
            "situacao": situ,
            "obs": (str(row[H["observacao"]]).strip()[:120] if H.get("observacao") is not None else ""),
            "agregado": agg,
            "qtd": qtd,
        }
        out.append((cod, nome, reg))
    return out


def _bucket(reg):
    if reg["situacao"] == "VENCIDO" and reg["dias"] > 0:
        d = reg["dias"]
        if d <= 30:  return "d1_30"
        if d <= 60:  return "d31_60"
        if d <= 90:  return "d61_90"
        return "d90"
    return "a_vencer"


CARTAO = {"Débito", "Crédito"}


def agrega(registros):
    """registros: lista de (cod, nome, reg) → dict por codigo.

    Os totais/aging/porNatureza são exatos (somam TODOS os registros). No
    DETALHE (drilldown), cartão é colapsado por pessoa+natureza+vencimento
    pra não inflar o JSON (caso rodem a query antiga, não-agregada)."""
    postos = {}     # cod -> nome
    dados = {}      # cod -> bloco
    cardmerge = {}  # cod -> chave -> reg colapsado
    for cod, nome, reg in registros:
        postos[cod] = nome
        b = dados.setdefault(cod, {
            "total": 0.0, "vencido": 0.0, "vence_hoje": 0.0, "a_vencer": 0.0, "qtd": 0,
            "aging": {"a_vencer": 0.0, "d1_30": 0.0, "d31_60": 0.0, "d61_90": 0.0, "d90": 0.0},
            "porNatureza": {}, "titulos": [],
        })
        v = reg["vl_aberto"]
        b["total"] += v
        b["qtd"] += reg["qtd"]
        if reg["situacao"] == "VENCIDO":     b["vencido"] += v
        elif reg["situacao"] == "VENCE HOJE": b["vence_hoje"] += v
        else:                                 b["a_vencer"] += v
        b["aging"][_bucket(reg)] += v
        n = b["porNatureza"].setdefault(reg["natureza"],
            {"total": 0.0, "vencido": 0.0, "vence_hoje": 0.0, "a_vencer": 0.0, "qtd": 0})
        n["total"] += v
        n["qtd"] += reg["qtd"]
        if reg["situacao"] == "VENCIDO":     n["vencido"] += v
        elif reg["situacao"] == "VENCE HOJE": n["vence_hoje"] += v
        else:                                 n["a_vencer"] += v
        if reg["natureza"] in CARTAO and not reg["agregado"]:
            ck = (cod, reg["pessoa"], reg["natureza"], reg["dt_venc"])
            m = cardmerge.get(ck)
            if m is None:
                m = dict(reg); m["titulo"] = "(agregado)"; m["agregado"] = 1
                m["dt_emissao"] = ""; m["obs"] = ""; m["qtd"] = 0; m["vl_aberto"] = 0.0; m["vl_original"] = 0.0
                cardmerge[ck] = m
                b["titulos"].append(m)
            m["vl_aberto"] = round(m["vl_aberto"] + reg["vl_aberto"], 2)
            m["vl_original"] = round(m["vl_original"] + reg["vl_original"], 2)
            m["qtd"] += reg["qtd"]
            m["parcela"] = str(m["qtd"])
        else:
            b["titulos"].append(reg)
    # arredonda e ordena
    for cod, b in dados.items():
        for k in ("total", "vencido", "vence_hoje", "a_vencer"):
            b[k] = round(b[k], 2)
        for k in b["aging"]:
            b["aging"][k] = round(b["aging"][k], 2)
        for n in b["porNatureza"].values():
            for k in ("total", "vencido", "vence_hoje", "a_vencer"):
                n[k] = round(n[k], 2)
        b["titulos"].sort(key=lambda t: (0 if t["situacao"] == "VENCIDO" else 1,
                                          t["dt_venc"] or "9999", -t["vl_aberto"]))
    return postos, dados


def main():
    arq_p = achar(EXPORT_DIRS, "TITABERTO", "pagar")
    arq_r = achar(EXPORT_DIRS, "TITABERTO", "receber")
    if not arq_p and not arq_r:
        print("  · (sem exports TITABERTO em", EXPORT_DIRS, "— nada a fazer)")
        return
    print("  pagar  :", arq_p or "(ausente)")
    print("  receber:", arq_r or "(ausente)")

    regs_p = parse(arq_p, "PAGAR") if arq_p else []
    regs_r = parse(arq_r, "RECEBER") if arq_r else []
    postos_p, dados_p = agrega(regs_p)
    postos_r, dados_r = agrega(regs_r)

    # união dos postos (codigo → nome)
    postos = {}
    postos.update(postos_r)
    postos.update(postos_p)
    lista = [{"codigo": c, "nome": n} for c, n in postos.items()]
    lista.sort(key=lambda p: p["codigo"])

    dados = {}
    for p in lista:
        c = p["codigo"]
        dados[c] = {"PAGAR": dados_p.get(c), "RECEBER": dados_r.get(c)}

    # ano de referência: do vencimento mais comum
    anos = [t["dt_venc"][:4] for c, n, t in (regs_p + regs_r) if t["dt_venc"]]
    ano = int(max(set(anos), key=anos.count)) if anos else dt.date.today().year

    out = {
        "geradoEm": dt.datetime.now().isoformat(timespec="seconds"),
        "ano": ano,
        "fonte": "Consulta SQL Títulos em Aberto (Adaptive) — vencimento em aberto",
        "arquivos": {"pagar": os.path.basename(arq_p) if arq_p else None,
                     "receber": os.path.basename(arq_r) if arq_r else None},
        "postos": lista,
        "dados": dados,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    outp = os.path.join(OUT_DIR, f"titulos_aberto_{ano}.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    tp = sum((dados_p.get(p["codigo"]) or {}).get("total", 0) for p in lista)
    tr = sum((dados_r.get(p["codigo"]) or {}).get("total", 0) for p in lista)
    print(f"  ✓ {outp} ({os.path.getsize(outp)//1024} KB · {len(lista)} postos)")
    print(f"    PAGAR  : R$ {tp:>16,.2f}  ({len(regs_p)} linhas)")
    print(f"    RECEBER: R$ {tr:>16,.2f}  ({len(regs_r)} linhas)")


if __name__ == "__main__":
    main()
