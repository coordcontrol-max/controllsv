#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL DRE Postos (Adaptive) — fonte: EXPORT ÚNICO da Consulta SQL.

Lê o export da "query única" (vendas + despesas 3.3.x título-a-título + taxas de
cartão + receitas) que o agente roda no Adaptive, e gera os MESMOS arquivos que
o dashboard já consome:
  dados_dre_postos_adaptive/{ano}.json          → a DRE (Análise Vertical)
  dados_dre_postos_adaptive/despesas_{ano}.json → drilldown de títulos

Colunas esperadas no export (14):
  tipo, posto, posto_nome, ano, mes, grupo, conta, dt, doc, fornecedor, obs,
  litros, valor, custo
tipo ∈ {VENDA, DESPESA, INVESTIMENTO, RETIRADA, RECEITA}

Uso:
  python3 etl_dre_postos_sql.py [arquivo.xls]   (sem arg = acha o mais recente)
"""
import os, sys, glob, json, re, datetime as dt
import xlrd

# Pastas onde o export da query única pode estar, em ordem de preferência.
# 1ª = pasta de rede onde o agente RPA salva (\\10.61.1.13\controller\03 - POSTOS\Automate);
# 2ª = Downloads (fallback / testes manuais).
EXPORT_DIRS = [
    "/mnt/controller/03 - POSTOS/Automate",
    "/mnt/c/Users/wesley/Downloads",
]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_dre_postos_adaptive")
HDR7 = ["tipo", "posto", "posto_nome", "ano", "mes", "grupo", "conta"]

MESES_NOME = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
              "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _casa_header(path):
    try:
        wb = xlrd.open_workbook(path)
        sh = wb.sheet_by_index(0)
        hdr = [str(sh.cell_value(0, i)).strip() for i in range(min(sh.ncols, 7))]
        return hdr == HDR7
    except Exception:
        return False


def achar_export(dirs):
    """Acha o .xls/.xlsx mais recente, entre as pastas dadas (recursivo),
    cujo cabeçalho casa com a query única."""
    ok = []
    for folder in dirs:
        if not os.path.isdir(folder):
            continue
        for pat in ("*.xls", "*.xlsx", "**/*.xls", "**/*.xlsx"):
            for c in glob.glob(os.path.join(folder, pat), recursive=True):
                if os.path.basename(c).startswith("~$"):
                    continue
                if _casa_header(c):
                    ok.append(c)
    return max(set(ok), key=os.path.getmtime) if ok else None


def _data_br(cell, datemode):
    """Converte célula de data (serial Excel ou texto) → 'dd/mm/aaaa' + mês 1..12."""
    if cell is None or cell == "":
        return "", None
    if isinstance(cell, (int, float)):
        try:
            d = xlrd.xldate.xldate_as_datetime(cell, datemode)
            return d.strftime("%d/%m/%Y"), d.month
        except Exception:
            return "", None
    s = str(cell).strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    return (s, int(m.group(2))) if m else (s, None)


def parse(path, filter_ano=None):
    """Parse the XLS into (ano_ref, dre, det).

    filter_ano: se passado, ignora linhas de anos diferentes — usado pelo ETL
    de competência pra processar um export com múltiplos anos em chamadas
    separadas.
    """
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    hdr = [str(sh.cell_value(0, i)).strip() for i in range(sh.ncols)]
    col = {name: hdr.index(name) for name in
           ["tipo", "posto", "posto_nome", "ano", "mes", "grupo", "conta",
            "dt", "doc", "fornecedor", "obs", "litros", "valor", "custo"] if name in hdr}

    ano_ref = None
    postos = {}   # codigo -> nome
    # agregados por posto
    z12 = lambda: [0.0] * 12
    vendas = {}        # cod -> meses (valor)
    vendas_custo = {}  # cod -> meses (custo)
    vendas_fuel = {}   # cod -> conta -> meses
    desp = {}          # cod -> grupo -> conta -> meses
    inv = {}           # cod -> conta -> meses
    ret = {}           # cod -> conta -> meses
    rec = {}           # cod -> conta -> meses
    titulos = {}       # nome -> conta -> "MM" -> [ {d,f,doc,o,v} ]

    def acc(d, *keys):
        cur = d
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        return cur

    for r in range(1, sh.nrows):
        tipo = str(sh.cell_value(r, col["tipo"])).strip()
        if not tipo:
            continue
        cod = str(sh.cell_value(r, col["posto"])).strip()
        nome = str(sh.cell_value(r, col["posto_nome"])).strip()
        ano = int(_num(sh.cell_value(r, col["ano"])) or 0)
        mes = int(_num(sh.cell_value(r, col["mes"])) or 0)
        grupo = str(sh.cell_value(r, col["grupo"])).strip()
        conta = str(sh.cell_value(r, col["conta"])).strip()
        valor = _num(sh.cell_value(r, col["valor"])) or 0.0
        if not cod or mes < 1 or mes > 12:
            continue
        if filter_ano is not None and ano != filter_ano:
            continue
        ano_ref = ano_ref or ano
        postos[cod] = nome
        mi = mes - 1

        if tipo == "VENDA":
            vendas.setdefault(cod, z12())[mi] += valor
            custo = _num(sh.cell_value(r, col["custo"])) or 0.0
            vendas_custo.setdefault(cod, z12())[mi] += custo
            vendas_fuel.setdefault(cod, {}).setdefault(conta, z12())[mi] += valor
        elif tipo == "DESPESA":
            desp.setdefault(cod, {}).setdefault(grupo, {}).setdefault(conta, z12())[mi] += valor
            # drilldown (linhas detalhadas têm data)
            dtxt, _ = _data_br(sh.cell_value(r, col["dt"]) if "dt" in col else "", wb.datemode)
            forn = str(sh.cell_value(r, col["fornecedor"])).strip() if "fornecedor" in col else ""
            doc = str(sh.cell_value(r, col["doc"])).strip() if "doc" in col else ""
            obs = str(sh.cell_value(r, col["obs"])).strip() if "obs" in col else ""
            titulos.setdefault(nome, {}).setdefault(conta, {}).setdefault(f"{mes:02d}", []).append(
                {"d": dtxt, "f": forn, "doc": doc, "o": obs, "v": valor})
        elif tipo == "INVESTIMENTO":
            inv.setdefault(cod, {}).setdefault(conta, z12())[mi] += valor
        elif tipo == "RETIRADA":
            ret.setdefault(cod, {}).setdefault(conta, z12())[mi] += valor
        elif tipo == "RECEITA":
            rec.setdefault(cod, {}).setdefault(conta, z12())[mi] += valor

    # ---- monta a DRE por posto ----
    def soma(*arrs):
        out = z12()
        for a in arrs:
            for i in range(12):
                out[i] += a[i]
        return out

    def neg(a):
        return [-x for x in a]

    def grp_sum(gd):  # gd = {conta: meses}
        out = z12()
        for cont in gd.values():
            for i in range(12):
                out[i] += cont[i]
        return out

    def total(a):
        s = sum(a)
        return round(s, 2) if any(a) else (round(s, 2) if s else None)

    def linha(label, nivel, meses, grupo=None):
        return {"label": label, "nivel": nivel, "grupo": grupo,
                "meses": [round(x, 2) if x else (0.0 if x == 0 else x) for x in meses],
                "total": round(sum(meses), 2)}

    def ord_grupos(grupos):
        def key(g):
            m = re.match(r"(\d+)\.(\d+)\.(\d+)", g)
            if m:
                return (0, int(m.group(1)), int(m.group(2)), int(m.group(3)), g)
            if g.upper().startswith("OUTRAS"):
                return (1, 0, 0, 0, g)
            return (2, 0, 0, 0, g)
        return sorted(grupos, key=key)

    dados = {}
    for cod, nome in postos.items():
        v = vendas.get(cod, z12())
        c = vendas_custo.get(cod, z12())
        lb = [v[i] - c[i] for i in range(12)]        # lucro bruto
        dgrupos = desp.get(cod, {})
        dtot = z12()
        for gd in dgrupos.values():
            for i in range(12):
                dtot[i] += sum(cont[i] for cont in gd.values())
        rtot = z12()
        for cont in rec.get(cod, {}).values():
            for i in range(12):
                rtot[i] += cont[i]
        ll = [lb[i] - dtot[i] + rtot[i] for i in range(12)]   # lucro líquido
        ittot = z12()
        for cont in inv.get(cod, {}).values():
            for i in range(12):
                ittot[i] += cont[i]
        retot = z12()
        for cont in ret.get(cod, {}).values():
            for i in range(12):
                retot[i] += cont[i]
        sf = [ll[i] - retot[i] - ittot[i] for i in range(12)]  # saldo final

        dre = []
        # Vendas + combustíveis
        dre.append(linha("Total das Vendas", 0, v))
        for fuel, ms in sorted(vendas_fuel.get(cod, {}).items()):
            dre.append(linha(fuel, 1, ms))
        # Custo / Lucro Bruto
        dre.append(linha("(-) Custo Total", 0, c))
        dre.append(linha("(=) Lucro Bruto", 0, lb))
        # Despesas → grupos 3.3.x → folhas
        dre.append(linha("(-) Despesas", 0, dtot))
        for g in ord_grupos(dgrupos.keys()):
            gd = dgrupos[g]
            dre.append(linha(g, 1, grp_sum(gd)))
            for cont_nome, ms in sorted(gd.items(), key=lambda x: -sum(x[1])):
                dre.append(linha(cont_nome, 2, ms, grupo=g))
        # Receitas
        if any(rtot):
            dre.append(linha("(+) Receitas", 0, rtot))
            for cont_nome, ms in sorted(rec.get(cod, {}).items(), key=lambda x: -sum(x[1])):
                dre.append(linha(cont_nome, 1, ms))
        # Lucro Líquido
        dre.append(linha("(=) Lucro Líquido", 0, ll))
        # Retiradas
        if any(retot):
            dre.append(linha("(-) Retiradas", 0, retot))
            for cont_nome, ms in sorted(ret.get(cod, {}).items(), key=lambda x: -sum(x[1])):
                dre.append(linha(cont_nome, 1, ms))
        # Investimentos
        if any(ittot):
            dre.append(linha("(-) Investimentos", 0, ittot))
            for cont_nome, ms in sorted(inv.get(cod, {}).items(), key=lambda x: -sum(x[1])):
                dre.append(linha(cont_nome, 1, ms))
        # Saldo Final
        dre.append(linha("(=) Saldo Final", 0, sf))

        dados[nome] = {"dre": dre, "indicadores": []}

    lista = [{"codigo": c, "nome": n} for c, n in postos.items()]
    lista.sort(key=lambda p: p["codigo"])
    return ano_ref or dt.date.today().year, {
        "ano": ano_ref,
        "geradoEm": dt.datetime.now().isoformat(timespec="seconds"),
        "fonte": "Consulta SQL única (Adaptive) — regime de caixa",
        "arquivo": os.path.basename(path),
        "postos": lista,
        "dados": dados,
    }, {
        "ano": ano_ref,
        "geradoEm": dt.datetime.now().isoformat(timespec="seconds"),
        "fonte": "Consulta SQL única (Adaptive) — títulos de despesa",
        "titulos": titulos,
    }


def _anos_no_export(path):
    """Lê o XLS e retorna o conjunto de anos presentes (coluna 'ano')."""
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
    print(f"  · ano {ano}…")
    _, dre, det = parse(path, filter_ano=ano)
    if not dre.get("postos"):
        print(f"    (sem dados pra {ano} — pulando)")
        return
    out1 = os.path.join(OUT_DIR, f"{ano}.json")
    out2 = os.path.join(OUT_DIR, f"despesas_{ano}.json")
    # DRE Postos agora opera só em competência (decisão do usuário 2026-05-27).
    dre["fonte"] = "Consulta SQL única (Adaptive) — regime de competência"
    det["fonte"] = "Consulta SQL única (Adaptive) — títulos por competência"
    # Preserva 'indicadores' (Volume Vendido, Ticket Médio etc.) do Mapa Anual,
    # se ainda existir em arquivo legado *_competencia.json.
    legado = os.path.join(OUT_DIR, f"{ano}_competencia.json")
    for sp in (legado, out1):
        try:
            prev = json.load(open(sp, encoding="utf-8"))
            for nome, blk in (prev.get("dados") or {}).items():
                ind = blk.get("indicadores") or []
                if ind and nome in dre["dados"] and not dre["dados"][nome].get("indicadores"):
                    dre["dados"][nome]["indicadores"] = ind
            break
        except (FileNotFoundError, json.JSONDecodeError):
            continue
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
        path = achar_export(EXPORT_DIRS)
        if not path:
            print("  · (sem export da query única em", EXPORT_DIRS, "— nada a fazer)")
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
