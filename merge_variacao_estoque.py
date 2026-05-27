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
    return max(cand, key=os.path.getmtime) if cand else None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else _achar_mapa()
    if not path:
        print("  · (sem Mapa Anual em", mapa.DOWNLOADS, "— pulando merge de Variação de Estoque)")
        return
    print("  Mapa Anual:", path)
    # Reusa o parser do ETL Mapa Anual pra extrair as linhas.
    # Gera um JSON temporário e depois extrai só Variação de Estoque.
    tmp = os.path.join(OUT_DIR, "_tmp_mapa_anual.json")
    try:
        # O ETL grava em {ano}_competencia.json; chamamos o parse() interno.
        ano, dre = mapa.parse(path)
    except AttributeError:
        # Fallback: chama o main e lê o arquivo gerado
        sys.argv = ["etl_dre_postos_adaptive.py", path]
        mapa.main()
        ano = 2026
        comp = os.path.join(OUT_DIR, f"{ano}_competencia.json")
        if not os.path.isfile(comp):
            print("  ✗ não consegui gerar JSON do Mapa Anual")
            return
        dre = json.load(open(comp, encoding="utf-8"))
        try:
            os.remove(comp)   # arquivo transiente — DRE vem da SQL agora
        except OSError:
            pass
    dst_path = os.path.join(OUT_DIR, f"{ano}.json")
    if not os.path.isfile(dst_path):
        print(f"  ✗ {dst_path} não existe (rode etl_dre_postos_sql.py antes)")
        return
    dst = json.load(open(dst_path, encoding="utf-8"))
    postos_src = (dre or {}).get("dados", {})
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


if __name__ == "__main__":
    main()
