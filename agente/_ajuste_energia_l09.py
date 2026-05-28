"""Ajuste de competência da Energia Elétrica da L09 (decisão do usuário 2026-05-28).

O "lump" de abril/2026 (-243.919,42, 25 títulos lançados todos em abril mas com
competências out/2025→abr/2026) é redistribuído pelas competências reais da
planilha que o usuário rastreou. Os títulos avulsos já lançados nos outros meses
são MANTIDOS (decisão: "só redistribuir o lump de abril").

Mecanismo: adiciona 1 fato de ajuste por mês em fatosClassificados, com
_fonte='energia_competencia_l09'. Os ajustes SOMAM ZERO (estorna o excedente de
abril e joga nas competências) → total da energia L09 conservado (274k).
Durável: meses fechados não reprocessam; e gravar_classificados preserva fatos
de _fonte fora das QUERIES.

Roda: python3 _ajuste_energia_l09.py
"""
import agente
from agente import db, engine, firestore

FONTE = "energia_competencia_l09"
NRO_L09 = 9   # L09 = nro 9/29; ajuste consolidado em 9 (rateio agrega ambos → L09)

# valor = ajuste a SOMAR no mês (negativo aumenta despesa; +abril estorna o lump)
AJUSTES = {
    "2025-10": -19008.59,
    "2025-11": -23917.20,
    "2025-12": -35179.73,
    "2026-01": -56526.56,
    "2026-02": -34650.85,
    "2026-03": -38852.68,
    "2026-04": +208135.61,   # 243.919,42 − 35.783,81 (deixa só a competência abril)
}
assert abs(sum(AJUSTES.values())) < 0.01, f"ajustes não somam zero: {sum(AJUSTES.values())}"

for chave, ajuste in AJUSTES.items():
    ano, mes = int(chave[:4]), int(chave[5:7])
    ref = db.collection("fatosClassificados").document(chave)
    snap = ref.get()
    if not snap.exists:
        print(f"  ⚠ {chave}: fatosClassificados não existe — pulando")
        continue
    data = snap.to_dict() or {}
    fatos = data.get("fatos") or []
    # Remove ajuste anterior desta fonte (idempotente — pode rodar de novo)
    fatos = [f for f in fatos if f.get("_fonte") != FONTE]
    fatos.append({
        "ano": ano, "mes": mes, "nroempresa": NRO_L09,
        "linha": "Energia Eletrica", "valor": round(ajuste, 2),
        "_fonte": FONTE,
        "_obs": "Ajuste competência energia L09 (redistribuição do lump de abril)",
    })
    ref.set({**data, "fatos": fatos, "totalFatos": len(fatos)}, merge=False)
    print(f"  ✓ {chave}: ajuste {ajuste:+,.2f} gravado")

print("\n>> Recomputando rateio dos 7 meses…")
for chave in AJUSTES:
    ano, mes = int(chave[:4]), int(chave[5:7])
    r = engine.executar_rateio(db, ano, mes, "realizado")
    print(f"  ✓ meses/{chave}: {r['lojas']} lojas, {r['pontos']} pontos")
print("\n=== ajuste energia L09 concluído ===")
