#!/usr/bin/env python3
# =============================================================================
# ETL Perdas e Sobras (Variação de Estoque) dos postos — fonte: query perdas.sql
# exportada na pasta Automate (perdas.xlsx = .xls BIFF). Agrega variação (litros)
# e venda_litros por posto/ano/mês e grava perdas_postos_{ano}.json.
# Variação = Sobra − Perda (litros). Card mostra variação% = variação ÷ volume.
# =============================================================================
import sys, os, json, glob
import xlrd

SAIDA = "dados_dre_postos_adaptive"
DEFAULT_XLS = "/mnt/controller/03 - POSTOS/Automate/perdas.xlsx"


def _achar_export():
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        return sys.argv[1]
    if os.path.exists(DEFAULT_XLS):
        return DEFAULT_XLS
    cands = glob.glob("/mnt/controller/03 - POSTOS/Automate/*erda*")
    cands = [c for c in cands if c.lower().endswith((".xls", ".xlsx"))]
    cands.sort(key=os.path.getmtime, reverse=True)
    return cands[0] if cands else None


def parse(path):
    wb = xlrd.open_workbook(path)
    ws = wb.sheet_by_index(0)
    hdr = [str(ws.cell_value(0, c)).strip().lower() for c in range(ws.ncols)]

    def col(name):
        for i, h in enumerate(hdr):
            if h == name:
                return i
        raise KeyError(f"coluna '{name}' não encontrada em {hdr}")

    ip, ia, im = col("posto"), col("ano"), col("mes")
    iv, ivl = col("variacao"), col("venda_litros")
    ipe, iso = col("perda"), col("sobra")

    ipr = col("produto")
    # anos -> {posto -> {mes -> {var, vol, perda, sobra, prod:{produto:{vol,var}}}}}
    por_ano = {}
    for r in range(1, ws.nrows):
        a = ws.cell_value(r, ia)
        if a == "" or a is None:
            continue
        ano = int(a)
        posto = str(ws.cell_value(r, ip)).strip()
        mes = str(int(ws.cell_value(r, im)))
        d = por_ano.setdefault(ano, {}).setdefault(posto, {}).setdefault(
            mes, {"var": 0.0, "vol": 0.0, "perda": 0.0, "sobra": 0.0, "prod": {}})
        var = float(ws.cell_value(r, iv) or 0)
        vol = float(ws.cell_value(r, ivl) or 0)
        d["var"] += var
        d["vol"] += vol
        d["perda"] += float(ws.cell_value(r, ipe) or 0)
        d["sobra"] += float(ws.cell_value(r, iso) or 0)
        # quebra por combustível (produto) — p/ drill por combustível na tabela
        prod = str(ws.cell_value(r, ipr) or "").strip()
        if prod:
            pp = d["prod"].setdefault(prod, {"vol": 0.0, "var": 0.0})
            pp["vol"] += vol
            pp["var"] += var
    return por_ano


def main():
    path = _achar_export()
    if not path:
        print("ERRO: export de perdas não encontrado.")
        sys.exit(1)
    print(f"Lendo {path}")
    por_ano = parse(path)
    os.makedirs(SAIDA, exist_ok=True)
    for ano, postos in sorted(por_ano.items()):
        # arredonda pra reduzir tamanho do JSON
        for p in postos:
            for m in postos[p]:
                rec = postos[p][m]
                for k in ("var", "vol", "perda", "sobra"):
                    rec[k] = round(rec[k], 3)
                for prod in rec.get("prod", {}):
                    rec["prod"][prod]["vol"] = round(rec["prod"][prod]["vol"], 3)
                    rec["prod"][prod]["var"] = round(rec["prod"][prod]["var"], 3)
        out = {"ano": ano, "postos": postos}
        fp = os.path.join(SAIDA, f"perdas_postos_{ano}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        nmes = sum(len(v) for v in postos.values())
        print(f"  {fp} · {len(postos)} postos · {nmes} posto-mês")


if __name__ == "__main__":
    main()
