#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Injeta a linha 'Variação de Estoque' do Mapa Anual (Adaptive) nos JSONs da
DRE Postos (regime de competência, vindos da SQL única).

Por quê: a SQL única (DRE_Postos.xlsx → etl_dre_postos_sql.py) não traz a
variação contábil de estoque. Essa info só sai do relatório "Mapa Anual de
Resultados e Indicadores" do Adaptive (exportado manualmente pelo usuário).

Uso (sem argumento usa o Mapa Anual mais recente do Downloads):
  python3 merge_variacao_estoque.py [caminho_do_mapa.xlsx]

Roda DEPOIS do etl_dre_postos_sql.py. Se não houver Mapa Anual, sai sem nada.
"""
import os, sys, glob, json
import etl_dre_postos_adaptive as mapa

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "dados_dre_postos_adaptive")


def _achar_mapa():
    """Mais recente '*Mapa Anual*.xlsx' do Downloads (mesmo critério do ETL)."""
    cand = []
    for pat in ("*Mapa Anual*.xlsx", "*Mapa Anual*.xls"):
        cand += glob.glob(os.path.join(mapa.DOWNLOADS, pat))
    cand = [c for c in cand if not os.path.basename(c).startswith("~$")]
    if not cand:
        return None
    # Prioriza o maior arquivo (proxy de mais postos) — evita pegar um Mapa
    # exportado com 1 posto só. Em empate, o mais recente.
    return max(cand, key=lambda c: (os.path.getsize(c), os.path.getmtime(c)))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else _achar_mapa()
    if not path:
        print("  · (sem Mapa Anual em", mapa.DOWNLOADS, "— pulando merge de Variação de Estoque)")
        return
    print("  Mapa Anual:", path)
    # parse() retorna um dict único {ano, dados, postos, ...}
    dre = mapa.parse(path)
    ano = dre.get("ano")
    # Mergeia em TODOS os JSONs do ano (caixa {ano}.json + competência {ano}_competencia.json),
    # já que Variação de Estoque é contábil e independe do regime.
    alvos = [f"{ano}.json", f"{ano}_competencia.json"]
    postos_src = (dre or {}).get("dados", {})
    n_total = 0
    for alvo in alvos:
        dst_path = os.path.join(OUT_DIR, alvo)
        if not os.path.isfile(dst_path):
            continue
        n_total += _merge_into(dst_path, postos_src)
    if n_total == 0:
        print("  ✗ nenhum JSON de DRE encontrado pra mergear (rode etl_dre_postos_sql.py antes)")


def _merge_into(dst_path, postos_src):
    dst = json.load(open(dst_path, encoding="utf-8"))
    postos_dst = dst.get("dados", {})
    n = 0
    for nome, blk in postos_dst.items():
        src_blk = postos_src.get(nome)
        if not src_blk:
            continue
        ve = next((ln for ln in src_blk.get("dre", [])
                   if ln["label"] == "Variação de Estoque"), None)
        if not ve:
            continue
        d = blk.get("dre", [])
        d = [ln for ln in d if ln["label"] != "Variação de Estoque"]
        idx = next((i for i, ln in enumerate(d)
                    if ln["label"] == "(=) Lucro Bruto"), len(d))
        d.insert(idx + 1, ve)
        blk["dre"] = d
        n += 1
    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(dst, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  ✓ Variação de Estoque mergeada em {n} postos · {dst_path}")
    return n


if __name__ == "__main__":
    main()
