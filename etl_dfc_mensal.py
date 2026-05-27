#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL DFC Mensal (Adaptive)

Este script lê os arquivos JSON gerados por ``etl_dfc_postos_sql.py``
(`dados_dre_postos_adaptive/dfc_postos_{ano}.json`) e agrega os valores
por mês, produzindo ``dados_dre_postos_adaptive/dfc_mensal_{ano}.json``.

A estrutura de saída conserva o mesmo esquema de ``dfc_postos`` mas
substitui a granularidade de dia (``YYYY-MM-DD``) por mês (``YYYY-MM``).
É suficiente para a nova visualização ``DFC Mensal (Adaptive)`` que
exibe colunas mensais.
"""
import os, json, datetime as dt

IN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_dre_postos_adaptive")
OUT_DIR = IN_DIR

def aggregate_monthly(data):
    """Transforma a estrutura diária em mensal.
    ``data['dados'][posto]['agg'][fluxo][grupo][conta]`` tem chaves de dia.
    """
    out = {}
    for posto, info in data.get("dados", {}).items():
        agg = info.get("agg", {})
        new_agg = {}
        for fluxo, grps in agg.items():
            new_agg.setdefault(fluxo, {})
            for grp, contas in grps.items():
                new_agg[fluxo].setdefault(grp, {})
                for conta, dias in contas.items():
                    monthly = {}
                    for dia_str, val in dias.items():
                        # dia_str esperado como 'YYYY-MM-DD'
                        try:
                            month = dia_str[:7]  # keep YYYY-MM
                        except Exception:
                            continue
                        monthly[month] = monthly.get(month, 0.0) + val
                    # round values
                    for m in monthly:
                        monthly[m] = round(monthly[m], 2)
                    new_agg[fluxo][grp][conta] = monthly
        out[posto] = {"agg": new_agg, "det": info.get("det", {})}
    return out

def main():
    for fname in os.listdir(IN_DIR):
        if not fname.startswith("dfc_postos_") or not fname.endswith('.json'):
            continue
        path = os.path.join(IN_DIR, fname)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        monthly = aggregate_monthly(data)
        out_data = {
            "ano": data.get("ano"),
            "geradoEm": dt.datetime.now().isoformat(timespec='seconds'),
            "fonte": data.get("fonte"),
            "arquivo": data.get("arquivo"),
            "postos": data.get("postos"),
            "dados": monthly,
        }
        out_name = f"dfc_mensal_{data.get('ano', 'unknown')}.json"
        out_path = os.path.join(OUT_DIR, out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(out_data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"Generated {out_path}")

if __name__ == '__main__':
    main()
