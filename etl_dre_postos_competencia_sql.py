#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL DRE Postos COMPETÊNCIA — fonte: export da Consulta SQL única em competência.

Espelha `etl_dre_postos_sql.py` (regime de caixa) mas:
  • lê arquivos com 'competencia' / 'COMPETENCIA' no nome (export da SQL de
    competência — ver query_dre_postos_competencia.sql);
  • grava em `{ano}_competencia.json` e `despesas_{ano}_competencia.json`;
  • NÃO sobrescreve o caixa.

Roda no run_etl.sh logo após o [4d] (caixa). Se não houver export de competência,
sai silenciosamente — o Mapa Anual ETL ([4c]) continua sendo o fallback de
totalizadores em competência (sem drilldown).
"""
import os, sys, glob
import etl_dre_postos_sql as caixa   # reusa parse()/achar_export logic

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "dados_dre_postos_adaptive")
# Mesmas pastas do caixa
EXPORT_DIRS = caixa.EXPORT_DIRS


def achar_export_competencia(dirs):
    """Acha o .xls/.xlsx mais recente cujo nome contém 'competencia' (qualquer
    case/acento) E cujo header casa com o esperado (14 colunas)."""
    import unicodedata
    def norm(s):
        s = unicodedata.normalize("NFD", s)
        return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    ok = []
    for folder in dirs:
        if not os.path.isdir(folder):
            continue
        for pat in ("*.xls", "*.xlsx", "**/*.xls", "**/*.xlsx"):
            for c in glob.glob(os.path.join(folder, pat), recursive=True):
                bn = os.path.basename(c)
                if bn.startswith("~$"):
                    continue
                if "competencia" not in norm(bn):
                    continue
                if caixa._casa_header(c):
                    ok.append(c)
    return max(set(ok), key=os.path.getmtime) if ok else None


def _anos_no_export(path):
    """Lê o XLS e retorna o conjunto de anos presentes (coluna 'ano')."""
    import xlrd
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    hdr = [str(sh.cell_value(0, i)).strip() for i in range(sh.ncols)]
    if "ano" not in hdr:
        return set()
    idx = hdr.index("ano")
    anos = set()
    for r in range(1, sh.nrows):
        try:
            a = int(float(sh.cell_value(r, idx) or 0))
            if a > 0:
                anos.add(a)
        except (TypeError, ValueError):
            pass
    return anos


def _processa_ano(path, ano):
    import json
    print(f"  · ano {ano}…")
    _, dre, det = caixa.parse(path, filter_ano=ano)
    if not dre.get("postos"):
        print(f"    (sem dados pra {ano} — pulando)")
        return
    out1 = os.path.join(OUT_DIR, f"{ano}_competencia.json")
    out2 = os.path.join(OUT_DIR, f"despesas_{ano}_competencia.json")
    dre["fonte"] = "Consulta SQL única (Adaptive) — regime de competência"
    det["fonte"] = "Consulta SQL única (Adaptive) — títulos por competência"
    # Preserva indicadores do Mapa Anual em out1, se existir
    try:
        prev = json.load(open(out1, encoding="utf-8"))
        for nome, blk in (prev.get("dados") or {}).items():
            ind = blk.get("indicadores") or []
            if ind and nome in dre["dados"] and not dre["dados"][nome].get("indicadores"):
                dre["dados"][nome]["indicadores"] = ind
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    with open(out1, "w", encoding="utf-8") as f:
        json.dump(dre, f, ensure_ascii=False, separators=(",", ":"))
    with open(out2, "w", encoding="utf-8") as f:
        json.dump(det, f, ensure_ascii=False, separators=(",", ":"))
    npost = len(dre["postos"])
    ndoc = sum(len(l) for p in det["titulos"].values() for m in p.values() for l in m.values())
    print(f"    ✓ {out1} ({os.path.getsize(out1)//1024} KB · {npost} postos)")
    print(f"    ✓ {out2} ({os.path.getsize(out2)//1024} KB · {ndoc} títulos)")


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = achar_export_competencia(EXPORT_DIRS)
        if not path:
            print("  · (sem export 'competencia*.xls' — pulando; o Mapa Anual ETL "
                  "continua provendo os totalizadores em competência)")
            return
    print("  fonte:", path)
    os.makedirs(OUT_DIR, exist_ok=True)
    anos = sorted(_anos_no_export(path))
    if not anos:
        print("  · (nenhum ano detectado na coluna 'ano' — abortando)")
        return
    for a in anos:
        _processa_ano(path, a)


if __name__ == "__main__":
    main()
