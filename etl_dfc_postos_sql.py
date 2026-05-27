#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL DFC Postos (Adaptive) — fonte: export DFC_Postos.xlsx (query única do DFC).

Lê o export da query única do DFC (entradas/saídas título-a-título + dinheiro,
regime de caixa) e gera dados_dre_postos_adaptive/dfc_postos_{ano}.json, no
formato que a tela "DFC Diário" dos postos consome:
  - agregado diário por posto → fluxo → grupo → conta → {AAAA-MM-DD: valor}
  - detalhe (drilldown) por posto → AAAA-MM-DD → grupo → [títulos]

Colunas esperadas (12): fluxo, posto, posto_nome, ano, mes, grupo, conta,
                        dt, doc, pessoa, obs, valor
fluxo ∈ {ENTRADA, SAIDA}

Uso: python3 etl_dfc_postos_sql.py [arquivo.xls(x)]
"""
import os, sys, glob, json, datetime as dt
import xlrd

EXPORT_DIRS = [
    "/mnt/controller/03 - POSTOS/Automate",
    "/mnt/c/Users/wesley/Downloads",
]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_dre_postos_adaptive")
HDR = ["fluxo", "posto", "posto_nome", "ano", "mes", "grupo", "conta",
       "dt", "doc", "pessoa", "obs", "valor"]

# Grupos que NÃO entram no DFC (movimento de caixa interno / antecipações,
# não fluxo operacional real). Pedido do usuário.
EXCLUIR_DFC = {
    "Baixa de Pagamento Antecipado", "Pagamento Antecipado",
    "Diferença de Caixa Negativa", "Diferença de Caixa Positiva",
}


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


def _casa(path):
    try:
        wb = xlrd.open_workbook(path)
        sh = wb.sheet_by_index(0)
        return [str(sh.cell_value(0, i)).strip() for i in range(min(sh.ncols, 12))] == HDR
    except Exception:
        return False


def achar_export(dirs):
    ok = achar_exports(dirs)
    return max(ok, key=os.path.getmtime) if ok else None


def achar_exports(dirs):
    """Retorna TODOS os exports DFC válidos (header bate, nome contém 'DFC')."""
    ok = []
    for folder in dirs:
        if not os.path.isdir(folder):
            continue
        for pat in ("*.xls", "*.xlsx"):
            for c in glob.glob(os.path.join(folder, pat)):
                b = os.path.basename(c)
                if b.startswith("~$"):
                    continue
                if "DFC" in b.upper() and _casa(c):
                    ok.append(c)
    return ok


def _data_iso(cell, datemode, ano, mes):
    """Serial Excel / texto → 'AAAA-MM-DD'. Dinheiro mensal (dt vazio) cai no dia 01."""
    if cell is None or cell == "":
        return f"{ano:04d}-{mes:02d}-01"
    if isinstance(cell, (int, float)):
        try:
            d = xlrd.xldate.xldate_as_datetime(cell, datemode)
            return d.strftime("%Y-%m-%d")
        except Exception:
            return f"{ano:04d}-{mes:02d}-01"
    s = str(cell).strip()
    import re
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return f"{ano:04d}-{mes:02d}-01"


def parse(path):
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    H = {str(sh.cell_value(0, c)).strip(): c for c in range(sh.ncols)}
    ano_ref = None
    postos = {}                 # codigo -> nome
    agg = {}                    # nome -> fluxo -> grupo -> conta -> {dia: valor}
    det = {}                    # nome -> dia -> grupo -> [ {f,conta,doc,pessoa,obs,v} ]

    # Pré-scan: nomes dos nossos postos (coluna posto_nome). Receitas/entradas
    # cujo fornecedor é um deles são transferências internas → mútuos (igual RETA).
    POSTO_NOMES = set()
    for r in range(1, sh.nrows):
        nm = str(sh.cell_value(r, H["posto_nome"])).strip().upper()
        if nm:
            POSTO_NOMES.add(nm)

    for r in range(1, sh.nrows):
        fluxo = str(sh.cell_value(r, H["fluxo"])).strip()
        if fluxo not in ("ENTRADA", "SAIDA"):
            continue
        cod = str(sh.cell_value(r, H["posto"])).strip()
        nome = str(sh.cell_value(r, H["posto_nome"])).strip()
        ano = int(_num(sh.cell_value(r, H["ano"])) or 0)
        mes = int(_num(sh.cell_value(r, H["mes"])) or 0)
        grupo = str(sh.cell_value(r, H["grupo"])).strip() or "Outros"
        conta = str(sh.cell_value(r, H["conta"])).strip() or grupo
        valor = _num(sh.cell_value(r, H["valor"])) or 0.0
        if not cod or mes < 1 or mes > 12:
            continue
        if grupo in EXCLUIR_DFC or conta in EXCLUIR_DFC:
            continue   # caixa interno / antecipações — fora do DFC
        ano_ref = ano_ref or ano
        postos[cod] = nome
        dia = _data_iso(sh.cell_value(r, H["dt"]), wb.datemode, ano, mes)

        doc = str(sh.cell_value(r, H["doc"])).strip() if H.get("doc") is not None else ""
        pessoa = str(sh.cell_value(r, H["pessoa"])).strip() if H.get("pessoa") is not None else ""
        obs = str(sh.cell_value(r, H["obs"])).strip() if H.get("obs") is not None else ""

        # Reclassificação: RETA COMERCIAL é empresa do grupo → transferências com
        # ela são MÚTUOS ENTRE GRUPOS (igual ao DFC das lojas), não receita/transf.
        pu = pessoa.strip().upper()
        du = (doc or "").strip().upper()
        if du.startswith("TRANS") or "RETA COMERCIAL" in pu or pu in POSTO_NOMES:
            # Transferências (doc TRANSF/TRANSRETA/TRANSFTARE/TRANSPEGUI/TRANS…),
            # RETA COMERCIAL, ou um dos nossos próprios postos como contraparte →
            # transferência entre empresas do grupo (mútuos), não receita/despesa.
            if fluxo == "ENTRADA":
                grupo = conta = "Mútuos a Receber (entre grupos)"
            else:
                grupo = conta = "Mútuos a Pagar (entre grupos)"
        elif fluxo == "ENTRADA" and pu == "PIX":
            # PIX entra como natureza "Débito"; separa numa linha própria.
            grupo = conta = "Recebimento de Venda em PIX"
        elif fluxo == "ENTRADA" and grupo == "Crédito":
            # Crédito "comum" = só as bandeiras VISA, MASTER, ELO e AMEX.
            # Todo o restante (SERVNET, VALE SHOP, CTF, TICKET, FITCARD…) é
            # cartão-frota → "Crédito (Frotas)".
            if ("VISA" in pu) or ("MASTER" in pu) or ("ELO" in pu) or ("AMEX" in pu):
                grupo = conta = "Recebimento de Venda em Crédito"
            else:
                grupo = conta = "Recebimento de Venda em Crédito (Frotas)"
        elif fluxo == "ENTRADA" and grupo == "Débito":
            grupo = conta = "Recebimento de Venda em Débito"
        elif fluxo == "ENTRADA" and grupo == "Dinheiro":
            # Dinheiro = depósito da PROTEGE (valor recebido da transportadora).
            grupo = conta = "Recebimento de Venda em Dinheiro (Protege)"

        (agg.setdefault(nome, {}).setdefault(fluxo, {})
            .setdefault(grupo, {}).setdefault(conta, {}))
        agg[nome][fluxo][grupo][conta][dia] = agg[nome][fluxo][grupo][conta].get(dia, 0.0) + valor
        if doc or pessoa or obs:     # só guarda detalhe de títulos (dinheiro não tem)
            (det.setdefault(nome, {}).setdefault(dia, {}).setdefault(grupo, []).append(
                {"f": fluxo, "conta": conta, "doc": doc, "pessoa": pessoa,
                 "obs": obs[:80], "v": round(valor, 2)}))

    # arredonda agregados
    for nome in agg:
        for fl in agg[nome]:
            for g in agg[nome][fl]:
                for c in agg[nome][fl][g]:
                    for d in agg[nome][fl][g][c]:
                        agg[nome][fl][g][c][d] = round(agg[nome][fl][g][c][d], 2)

    lista = [{"codigo": c, "nome": n} for c, n in postos.items()]
    lista.sort(key=lambda p: p["codigo"])
    return ano_ref or dt.date.today().year, {
        "ano": ano_ref,
        "geradoEm": dt.datetime.now().isoformat(timespec="seconds"),
        "fonte": "Consulta SQL DFC (Adaptive) — regime de caixa",
        "arquivo": os.path.basename(path),
        "postos": lista,
        "dados": {n: {"agg": agg.get(n, {}), "det": det.get(n, {})} for n in postos.values()},
    }


def _emit(path):
    print("  fonte:", path)
    ano, data = parse(path)
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"dfc_postos_{ano}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    ndet = sum(len(l) for n in data["dados"].values()
               for d in n["det"].values() for l in d.values())
    print(f"  ✓ {out} ({os.path.getsize(out)//1024} KB · {len(data['postos'])} postos · {ndet} títulos)")


def main():
    if len(sys.argv) > 1:
        _emit(sys.argv[1])
        return
    # Sem argumento: processa TODOS os exports DFC válidos (cobre histórico+ano corrente).
    paths = achar_exports(EXPORT_DIRS)
    if not paths:
        print("  · (sem export DFC_Postos em", EXPORT_DIRS, "— nada a fazer)")
        return
    for p in sorted(paths, key=os.path.getmtime):
        _emit(p)


if __name__ == "__main__":
    main()
