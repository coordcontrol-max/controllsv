#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o segmento INTERCOMPANY = consolidação do Fluxo de Caixa de
POSTOS (dados_fluxo_postos) + OUTRAS EMPRESAS (dados_fluxo_outras).

Junta as duas fontes num único conjunto de JSONs no MESMO schema que o
dashboard consome (dados_fluxo_intercompany/), com:
  • lojas  = todos os postos (P01..P11) + todas as outras (FLUXO/LP/PEGUI/RETA/TARES)
  • linhas = união das linhas dos dois planos de contas (por nome)
  • agrupamentos/grupos = união (postos já cobre os de outras)
  • {ano-mes}.json          → consolidado (soma de tudo), totais mensais (d=0)
  • {ano-mes}__{LOJA}.json  → cópia re-indexada de cada loja de cada fonte
  • saldos_iniciais.json    → soma dos saldos (total + porLoja unidos)
  • meta.json

Consolida no total do mês (d=0) pra alinhar as duas fontes (postos pode ser
mensal, outras é diário) — a aba DFC Mensal usa os totais mensais.

Uso: python3 gera_fluxo_intercompany.py
"""
import os, json, glob, re, datetime as dt
from collections import defaultdict, OrderedDict

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = [os.path.join(BASE, "dados_fluxo_postos"), os.path.join(BASE, "dados_fluxo_outras")]
OUT = os.path.join(BASE, "dados_fluxo_intercompany")
MES_RE = re.compile(r"^(\d{4})-(\d{2})(?:__(.+))?\.json$")


def carregar_taxonomia():
    """União ordenada das taxonomias dos dois segmentos → (grupos, agrupamentos,
       lista [(linha, grupo, agrupamento)])."""
    grupos, agrups, linhas = [], [], OrderedDict()
    for d in SRC:
        mp = os.path.join(d, "meta.json")
        if not os.path.exists(mp):
            continue
        meta = json.load(open(mp, encoding="utf-8"))
        for g in meta["dimensoes"]["grupos"]:
            if g not in grupos:
                grupos.append(g)
        for a in meta["dimensoes"]["agrupamentos"]:
            if a not in agrups:
                agrups.append(a)
        for t in meta.get("taxonomia", []):
            if t["nome"] not in linhas:
                linhas[t["nome"]] = (t["grupo"], t["agrupamento"])
    taxo = [(nome, gp, ag) for nome, (gp, ag) in linhas.items()]
    return grupos, agrups, taxo


def decode_doc(path):
    """Lê um doc de fluxo e devolve {linha: total_mes} (soma sobre os dias)."""
    d = json.load(open(path, encoding="utf-8"))
    linhas = d["dim"]["linhas"]
    acc = defaultdict(float)
    for e in d.get("porLinha", []):
        acc[linhas[e["n"]]] += e["v"]
    return acc


def montar_doc(ano, mes, linha_total, GRUPOS, AGRUPS, TAXO, loja=""):
    li = {l: i for i, (l, _, _) in enumerate(TAXO)}
    gi = {g: i for i, g in enumerate(GRUPOS)}
    ai = {a: i for i, a in enumerate(AGRUPS)}
    linhas = [l for l, _, _ in TAXO]
    porLinha, accA, accG = [], defaultdict(float), defaultdict(float)
    for linha, grupo, agrup in TAXO:
        v = linha_total.get(linha, 0.0)
        if round(v, 2) == 0:
            continue
        n, g, a = li[linha], gi[grupo], ai[agrup]
        porLinha.append({"d": 0, "g": g, "a": a, "n": n, "v": round(v, 2)})
        accA[(0, g, a)] += v
        accG[(0, g)] += v
    return {
        "ano": ano, "mes": mes, "v": 2, "segmento": "intercompany", "loja": loja,
        "dim": {"dias": [f"{x:02d}" for x in range(1, 32)],
                "grupos": GRUPOS, "agrupamentos": AGRUPS, "linhas": linhas},
        "porLinha": porLinha,
        "porAgrupamento": [{"d": d, "g": g, "a": a, "v": round(v, 2)} for (d, g, a), v in accA.items() if abs(v) >= 0.005],
        "porGrupo": [{"d": d, "g": g, "v": round(v, 2)} for (d, g), v in accG.items() if abs(v) >= 0.005],
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    # limpa saída antiga (só os JSONs que geramos)
    for f in glob.glob(os.path.join(OUT, "*.json")):
        os.remove(f)
    GRUPOS, AGRUPS, TAXO = carregar_taxonomia()

    # coleta: mes -> "" (consolidado) ou loja -> {linha: total}
    consol = defaultdict(lambda: defaultdict(float))     # mes -> linha -> v
    por_loja = defaultdict(lambda: defaultdict(float))   # (mes,loja) -> linha -> v
    lojas = []
    meses = set()
    for d in SRC:
        for fp in sorted(glob.glob(os.path.join(d, "*.json"))):
            m = MES_RE.match(os.path.basename(fp))
            if not m:
                continue
            ano, mesn, loja = int(m.group(1)), int(m.group(2)), m.group(3)
            acc = decode_doc(fp)
            if loja is None:
                # agregado do segmento → soma no consolidado intercompany
                meses.add((ano, mesn))
                for ln, v in acc.items():
                    consol[(ano, mesn)][ln] += v
            else:
                if loja not in lojas:
                    lojas.append(loja)
                for ln, v in acc.items():
                    por_loja[(ano, mesn, loja)][ln] += v

    nfiles = 0
    for (ano, mesn) in sorted(meses):
        doc = montar_doc(ano, mesn, consol[(ano, mesn)], GRUPOS, AGRUPS, TAXO, loja="")
        json.dump(doc, open(os.path.join(OUT, f"{ano}-{mesn:02d}.json"), "w", encoding="utf-8"), ensure_ascii=False)
        nfiles += 1
    for (ano, mesn, loja), acc in por_loja.items():
        doc = montar_doc(ano, mesn, acc, GRUPOS, AGRUPS, TAXO, loja=loja)
        json.dump(doc, open(os.path.join(OUT, f"{ano}-{mesn:02d}__{loja}.json"), "w", encoding="utf-8"), ensure_ascii=False)
        nfiles += 1

    # saldos iniciais: soma total + une porLoja
    saldos = defaultdict(lambda: {"total": 0.0, "porLoja": {}})
    for d in SRC:
        sp = os.path.join(d, "saldos_iniciais.json")
        if not os.path.exists(sp):
            continue
        s = json.load(open(sp, encoding="utf-8"))
        for chave, ent in s.items():
            saldos[chave]["total"] += float(ent.get("total") or 0)
            for lj, v in (ent.get("porLoja") or {}).items():
                saldos[chave]["porLoja"][lj] = float(v)
    for chave in saldos:
        saldos[chave]["total"] = round(saldos[chave]["total"], 2)
    json.dump(saldos, open(os.path.join(OUT, "saldos_iniciais.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # saldos OFICIAIS (âncora diária 27/04 etc.): une postos + outras por data, pra
    # o Intercompany ancorar igual aos dois segmentos (senão saldo não bate).
    saldos_of = defaultdict(lambda: {"total": 0.0, "porLoja": {}})
    for d in SRC:
        sp = os.path.join(d, "saldos_oficiais.json")
        if not os.path.exists(sp):
            continue
        s = json.load(open(sp, encoding="utf-8"))
        for chave, ent in s.items():
            if not isinstance(ent, dict) or "porLoja" not in ent:
                continue   # ignora _doc e afins
            saldos_of[chave]["total"] += float(ent.get("total") or 0)
            for lj, v in (ent.get("porLoja") or {}).items():
                saldos_of[chave]["porLoja"][lj] = float(v)
    for chave in saldos_of:
        saldos_of[chave]["total"] = round(saldos_of[chave]["total"], 2)
    if saldos_of:
        json.dump(saldos_of, open(os.path.join(OUT, "saldos_oficiais.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    # detalhe diário (concatena postos + outras por mês) — necessário pra o
    # front ancorar o Saldo no saldo OFICIAL (split diário do mês-âncora).
    det_meses = defaultdict(list)
    for d in SRC:
        for fp in sorted(glob.glob(os.path.join(d, "detalhe_*.json"))):
            base = os.path.basename(fp)              # detalhe_AAAA-MM.json
            try:
                items = (json.load(open(fp, encoding="utf-8")) or {}).get("items", [])
            except Exception:
                items = []
            det_meses[base].extend(items)
    for base, items in det_meses.items():
        json.dump({"items": items}, open(os.path.join(OUT, base), "w", encoding="utf-8"),
                  ensure_ascii=False)

    meta = {
        "geradoEm": dt.datetime.now().isoformat(), "segmento": "intercompany",
        "fonte": "Consolidação dados_fluxo_postos + dados_fluxo_outras",
        "dimensoes": {"anos": sorted({a for a, _ in meses}), "meses": sorted({mn for _, mn in meses}),
                      "lojas": lojas, "grupos": GRUPOS, "agrupamentos": AGRUPS,
                      "linhas": [l for l, _, _ in TAXO]},
        "taxonomia": [{"nome": l, "grupo": g, "agrupamento": a} for l, g, a in TAXO],
        "obs": "Intercompany = Postos + Outras Empresas. Consolidado no total mensal (d=0).",
    }
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✓ Intercompany: {nfiles+2} arquivos em {OUT}")
    print(f"  lojas ({len(lojas)}): {lojas}")
    print(f"  meses: {sorted(f'{a}-{m:02d}' for a,m in meses)} | linhas: {len(TAXO)} | agrupamentos: {AGRUPS}")


if __name__ == "__main__":
    main()
