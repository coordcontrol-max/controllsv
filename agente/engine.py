"""Engine de rateio: pega fatosClassificados + lancamentosManuais + rateios
e produz meses/{ano-mes} no formato compacto v=2 que o dashboard consome.

Fluxo:
  1. Lê fatosClassificados/{ano-mes}              (saída do classificador)
  2. Lê lancamentosManuais/ filtrado por mes      (provisões/ajustes manuais)
  3. Lê meta/lojas e meta/linhas                  (mapeamentos NROEMPRESA→loja
                                                    e LINHA→grupo/agrupamento)
  4. (V2 — TODO) aplica rateios/                  (driver / matriz / duplicacao)
  5. Agrega por (loja, grupo, agrupamento, linha)
  6. Aplica LINHAS_CALCULADAS                     (fórmulas tipo Margem Operacional)
  7. Empacota como doc compacto v=2 e grava meses/{ano-mes}
"""
from __future__ import annotations
from collections import defaultdict
from firebase_admin import firestore


# ─── Inferência de GRUPO pelo nome da LINHA ─────────────────────────────────
# 5 agrupamentos ('Despesas c/ Pessoal', 'Despesas Jurídicas', 'Despesas com
# Informática', 'Material de Expediente', 'Serviços Terceirizados') são
# compartilhados entre os grupos Despesas Operacionais / Despesas Comerciais /
# Despesas Administrativas. O nome da LINHA traz o sufixo (Operacao/Comercial/
# ADM) que diz a qual grupo ela pertence. Esta função aplica essa regra; pra
# LINHAs sem sufixo (a maioria), cai pro fallback agrupamento_para_grupo.
SUFIXO_PARA_GRUPO = [
    # Ordem importa: prefixos mais longos antes pra evitar match parcial.
    ("Operação", "Despesas Operacionais"),
    ("Operaçao", "Despesas Operacionais"),
    ("Operacao", "Despesas Operacionais"),
    ("Comercial", "Despesas Comerciais"),
    ("ADM",       "Despesas Administrativas"),
]


def _grupo_por_linha(nome_linha: str, agrupamento: str, agrup_para_grupo: dict) -> str:
    """Decide o grupo de uma LINHA usando sufixo + fallback."""
    for sufixo, grupo in SUFIXO_PARA_GRUPO:
        if nome_linha.endswith(" " + sufixo) or (" " + sufixo + " ") in nome_linha:
            return grupo
    return agrup_para_grupo.get(agrupamento, "")


# ─── Multiplicadores por LINHA ──────────────────────────────────────────────
# Oracle traz FGTS e INSS triplicados (1 conta por área: Operacao/Comercial/ADM)
# com o mesmo valor em cada — totaliza 3× o real. Rateio 90% Operação / 8% ADM /
# 2% Comercial (decisão do usuário 2026-05) pra bater com a divisão real do custo.
LINHA_MULTIPLIER = {
    "FGTS Operacao":          0.90,
    "INSS e GPS Operacao":    0.90,
    "FGTS ADM":               0.08,
    "INSS e GPS ADM":         0.08,
    "FGTS Comercial":         0.02,
    "INSS e GPS Comercial":   0.02,
}

# ─── Linhas que vêm DIRETO do drePB (PowerBI), 1:1 por loja ──────────────────
# A query de despesas (codoperacao=6) não bate com o ERP ("Inclusão de Títulos")
# nessas linhas — o valor correto é o do PowerBI. Quando há drePB do mês,
# SUBSTITUI o valor do op-6 pelo do PB. Sem drePB (ex: mês corrente), mantém op-6.
# (INSS é tratado à parte porque tem split 90/8/2 — ver _carregar_inss_pb.)
LINHAS_PB_DIRETO = {
    "FGTS Multa Recisoria Operacao",
}


# ─── LINHAs CALCULADAS ──────────────────────────────────────────────────────
# Fórmulas aplicadas POR LOJA depois da agregação base. Cada entrada cria
# uma LINHA derivada no DRE. `calc` recebe três funções de lookup:
#   l(nome) → valor da LINHA "nome" naquela loja        (0 se inexistente)
#   a(nome) → valor do AGRUPAMENTO "nome" naquela loja  (0 se inexistente)
#   g(nome) → valor do GRUPO "nome" naquela loja        (0 se inexistente)
# A ordem importa: linhas posteriores podem referenciar as anteriores.
# `agrupamento` é a coluna onde a LINHA derivada vai aparecer no plano.
LINHAS_CALCULADAS = [
    {
        # Margem S/ Acordos = Venda Bruta + grupo CMV (Mercadoria + Embalagens).
        # Sobrescreve o valor que o classificador grava (MARGEM - VERBA da
        # query venda_atual), garantindo que esteja consistente com o grupo
        # CMV completo — incluindo Consumo Interno, Etiquetas e Sacolas PDV.
        "nome":         "Margem S/ Acordos",
        "agrupamento":  "Margem S/ Acordos",
        "calc":         lambda l, a, g: l("Venda Bruta") + a("Mercadoria para Revenda") + a("Embalagens"),
    },
    {
        # Margem C/ Acordos = Margem S/ Acordos + GRUPO Receitas Comerciais.
        # Usa o GRUPO (não o agrupamento): o agrupamento "Receitas Comerciais"
        # carrega a linha "Acordo Comercial", que pertence ao grupo "Despesa
        # Comerciais" — usar o agrupamento a contava em dobro (~51k/mês).
        "nome":         "Margem C/ Acordos",
        "agrupamento":  "Margem C/ Acordos",
        "calc":         lambda l, a, g: l("Margem S/ Acordos") + g("Receitas Comerciais"),
    },
    {
        "nome":         "Margem Operacional",
        "agrupamento":  "Margem Operacional",
        "calc":         lambda l, a, g: l("Margem C/ Acordos") + a("Quebra Contábil"),
    },
    {
        # EBITDA = Margem Operacional + Despesas Op + Com + Adm + C/ Vendas.
        # Despesas são somadas (já vêm negativas), então deduzem da margem.
        "nome":         "EBITDA",
        "agrupamento":  "EBITDA",
        "calc":         lambda l, a, g: (
            l("Margem Operacional")
            + g("Despesas Operacionais")
            + g("Despesas Comerciais")
            + g("Despesas Administrativas")
            + g("Despesas C/ Vendas")
        ),
    },
    {
        "nome":         "LAIR",
        "agrupamento":  "LAIR",
        "calc":         lambda l, a, g: l("EBITDA") + g("Resultado Financeiro"),
    },
    {
        # IRPJ = 25% do LAIR (só se positivo, gravado como despesa negativa).
        "nome":         "IRPJ",
        "agrupamento":  "IRPJ/CSLL",
        "calc":         lambda l, a, g: -(l("LAIR") * 0.25) if l("LAIR") > 0 else 0.0,
    },
    {
        # CSLL = 9% do LAIR (só se positivo, gravado como despesa negativa).
        "nome":         "CSLL",
        "agrupamento":  "IRPJ/CSLL",
        "calc":         lambda l, a, g: -(l("LAIR") * 0.09) if l("LAIR") > 0 else 0.0,
    },
    {
        "nome":         "Lucro Líquido",
        "agrupamento":  "Lucro Líquido",
        "calc":         lambda l, a, g: l("LAIR") + l("IRPJ") + l("CSLL"),
    },
    {
        "nome":         "Lucro Líquido Ajustado",
        "agrupamento":  "Lucro Líquido Ajustado",
        "calc":         lambda l, a, g: l("Lucro Líquido") + a("Novas Unidades e Ajustes Gerenciais"),
    },
]


def _carregar_fatos_classificados(db, ano: int, mes: int) -> list[dict]:
    """Lê fatosClassificados/{ano-mes} → lista de fatos."""
    chave = f"{ano:04d}-{mes:02d}"
    snap = db.collection("fatosClassificados").document(chave).get()
    if not snap.exists:
        return []
    data = snap.to_dict() or {}
    return list(data.get("fatos") or [])


def _carregar_aluguel_pb(db, ano: int, mes: int) -> dict:
    """Lê drePB/{ano-mes} e devolve {loja: valor} da linha 'Aluguel de Imoveis'.
    Vazio se não houver snapshot do PowerBI pro mês."""
    chave = f"{ano:04d}-{mes:02d}"
    snap = db.collection("drePB").document(chave).get()
    if not snap.exists:
        return {}
    out: dict[str, float] = {}
    for p in (snap.to_dict() or {}).get("pontos", []):
        if p.get("linha") == "Aluguel de Imoveis":
            lo = p.get("loja")
            if lo:
                out[lo] = out.get(lo, 0.0) + float(p.get("valor") or 0)
    return out


def _carregar_aluguel_contrato(db) -> dict:
    """Lê meta/aluguelContrato → {loja: valor mensal do contrato} (negativo).
    Usado p/ provisionar o aluguel das lojas SEM lançamento no sistema a partir
    de mai/2026 (ver _agregar_em_doc_compacto)."""
    snap = db.collection("meta").document("aluguelContrato").get()
    if not snap.exists:
        return {}
    out = {}
    for lo, v in ((snap.to_dict() or {}).get("lojas") or {}).items():
        try:
            out[lo] = float(v)
        except (ValueError, TypeError):
            pass
    return out


def _carregar_inss_pb(db, ano: int, mes: int) -> dict:
    """Lê drePB/{ano-mes} e devolve {loja: valor} do INSS e GPS (valor cheio).
    A query de despesas (codoperacao=6) só captura parte do INSS; o total real
    (títulos incluídos) vem do PowerBI. As 3 áreas vêm idênticas no PB, então
    pega a 'INSS e GPS Operacao'. Vazio se não houver snapshot do mês."""
    chave = f"{ano:04d}-{mes:02d}"
    snap = db.collection("drePB").document(chave).get()
    if not snap.exists:
        return {}
    out: dict[str, float] = {}
    for p in (snap.to_dict() or {}).get("pontos", []):
        if p.get("linha") == "INSS e GPS Operacao":
            lo = p.get("loja")
            if lo:
                out[lo] = out.get(lo, 0.0) + float(p.get("valor") or 0)
    return out


def _carregar_pb_diretas(db, ano: int, mes: int) -> dict:
    """Lê drePB/{ano-mes} e devolve {linha: {loja: valor}} das linhas em
    LINHAS_PB_DIRETO (que vêm direto do PowerBI). Vazio se não houver snapshot."""
    chave = f"{ano:04d}-{mes:02d}"
    snap = db.collection("drePB").document(chave).get()
    if not snap.exists:
        return {}
    out: dict[str, dict] = {}
    for p in (snap.to_dict() or {}).get("pontos", []):
        ln = p.get("linha")
        lo = p.get("loja")
        if ln in LINHAS_PB_DIRETO and lo:
            out.setdefault(ln, {})[lo] = out.get(ln, {}).get(lo, 0.0) + float(p.get("valor") or 0)
    return out


def _carregar_lancamentos_manuais(db, ano: int, mes: int, cenario: str = "realizado") -> list[dict]:
    """Lê lancamentosManuais/ filtrando por mes (formato 'YYYY-MM') e cenario."""
    chave = f"{ano:04d}-{mes:02d}"
    out = []
    for d in db.collection("lancamentosManuais").stream():
        data = d.to_dict() or {}
        if data.get("mes") != chave:
            continue
        if data.get("cenario", "realizado") != cenario:
            continue
        # Lançamento manual ainda não tem nroempresa — engine de rateio
        # (V2) precisa distribuir nas lojas. Por enquanto, pula na agregação.
        out.append({
            "ano": ano, "mes": mes,
            "nroempresa": None,
            "linha": data.get("linha", ""),
            "valor": float(data.get("valor", 0) or 0),
            "_fonte": "lancamentoManual",
            "_obs": data.get("obs", ""),
        })
    return out


def _carregar_dimensoes(db) -> dict:
    """Carrega meta/lojas, meta/grupos, meta/agrupamentos e meta/linhas.

    O `meta/linhas` em geral tem `grupo` vazio — só `agrupamento`.
    O `meta/agrupamentos` traz o mapa agrupamento→grupo, que aplicamos pra
    inferir o grupo de cada LINHA. `meta/grupos` define a ordem dos grupos.
    """
    out = {
        "nroempresa_para_loja":   {},   # {1: "Loja Centro"}
        "agrupamento_para_grupo": {},   # {"Mercadoria para Revenda": "CMV"}
        "linha_para_grupo":       {},   # {"Venda Bruta": ("Venda Bruta", "Venda Bruta")}
        "linhas_ordenadas":       [],
        "grupos_ordenados":       [],
        "agrupamentos_ordenados": [],
    }

    snap = db.collection("meta").document("lojas").get()
    if snap.exists:
        for item in (snap.to_dict() or {}).get("items", []):
            nome = item.get("descricao") or ""
            ativo = item.get("ativo", True)
            if not nome or not ativo:
                continue
            for nro in item.get("nroempresa", []):
                try:
                    out["nroempresa_para_loja"][int(nro)] = nome
                except (ValueError, TypeError):
                    pass

    # meta/grupos: ordenado por campo `ordem`
    snap = db.collection("meta").document("grupos").get()
    if snap.exists:
        items = sorted(
            (snap.to_dict() or {}).get("items", []),
            key=lambda x: x.get("ordem", 9999),
        )
        out["grupos_ordenados"] = [it.get("nome") for it in items if it.get("nome")]

    # meta/agrupamentos: mapa agrupamento→grupo + ordem
    snap = db.collection("meta").document("agrupamentos").get()
    if snap.exists:
        items = (snap.to_dict() or {}).get("items", [])
        for it in items:
            n = it.get("nome") or ""
            g = it.get("grupo") or ""
            if n and g:
                out["agrupamento_para_grupo"][n] = g
            if n and n not in out["agrupamentos_ordenados"]:
                out["agrupamentos_ordenados"].append(n)

    # meta/linhas: usa agrupamento dela e infere grupo via sufixo do nome +
    # fallback no map de agrupamento. Isso cobre os 5 agrupamentos que aparecem
    # em múltiplos grupos (ex: "Despesas c/ Pessoal" em Operacionais/Comercial/ADM).
    snap = db.collection("meta").document("linhas").get()
    if snap.exists:
        for item in (snap.to_dict() or {}).get("items", []):
            nome = item.get("nome") or ""
            grupo = item.get("grupo") or ""   # se cadastrado explicitamente, respeita
            agrupamento = item.get("agrupamento") or ""
            if not nome:
                continue
            if not grupo:
                grupo = _grupo_por_linha(nome, agrupamento, out["agrupamento_para_grupo"])
            out["linha_para_grupo"][nome] = (grupo, agrupamento)
            if nome not in out["linhas_ordenadas"]:
                out["linhas_ordenadas"].append(nome)
    return out


def _agregar_em_doc_compacto(fatos: list[dict], dimensoes: dict, ano: int, mes: int,
                             aluguel_pb: dict | None = None, inss_pb: dict | None = None,
                             pb_diretas: dict | None = None, aluguel_contrato: dict | None = None) -> dict:
    """Agrega fatos por (loja, grupo, agrupamento, linha) → doc compacto v=2.

    Formato consumido pelo dashboard (loadFromFirestore):
      { ano, mes, v:2, dim:{lojas,grupos,agrupamentos,linhas},
        porGrupo:[{l,g,v}], porAgrupamento:[{l,a,v}], porLinha:[{l,g,a,n,v}] }
    onde l/g/a/n são índices nos arrays de dim.

    aluguel_pb: {loja: valor} do DRE PowerBI para "Aluguel de Imoveis". Quando
    presente, completa a linha local somando o que falta por loja (só onde o PB
    tem MAIS despesa) — registrado no detalhe como ajuste identificado.
    """
    nro2loja = dimensoes["nroempresa_para_loja"]
    linha2grupo = dimensoes["linha_para_grupo"]

    porLinha: dict[tuple, float]       = defaultdict(float)
    porAgrupamento: dict[tuple, float] = defaultdict(float)
    porGrupo: dict[tuple, float]       = defaultdict(float)

    lojas_set, linhas_set, grupos_set, agrups_set = set(), set(), set(), set()
    nros_sem_loja: set = set()
    linhas_fora_plano: dict[str, float] = {}   # LINHA → total absoluto (pra ranking)

    # Provisões manuais (lançamentoManual, sem nroempresa): viram TOTAL por
    # LINHA, rateado por venda mais abaixo. {linha: total, obs}.
    provisao_por_linha: dict[str, float] = {}
    provisao_obs: dict[str, str] = {}
    provisoes_detalhe: list[dict] = []   # drill-down: 1 linha por (loja, linha) rateada

    for f in fatos:
        nro = f.get("nroempresa")
        if nro is None:
            # Lançamento manual sem loja → acumula como total a ratear por venda.
            if f.get("_fonte") == "lancamentoManual":
                ln = f.get("linha") or ""
                if ln:
                    provisao_por_linha[ln] = provisao_por_linha.get(ln, 0.0) + float(f.get("valor") or 0)
                    if f.get("_obs"):
                        provisao_obs[ln] = f.get("_obs")
            else:
                nros_sem_loja.add(None)
            continue
        try:
            nro = int(nro)
        except (ValueError, TypeError):
            nros_sem_loja.add(nro)
            continue
        loja = nro2loja.get(nro)
        if not loja:
            nros_sem_loja.add(nro)
            continue
        linha = f.get("linha") or ""
        valor = float(f.get("valor") or 0)
        if linha in LINHA_MULTIPLIER:
            valor *= LINHA_MULTIPLIER[linha]
        if not linha or valor == 0:
            continue
        if linha not in linha2grupo:
            # LINHA não cadastrada em meta/linhas — agrega mesmo assim em
            # porLinha mas com grupo/agrup vazios (aparece no dashboard
            # como linha órfã). Conta pra warning.
            linhas_fora_plano[linha] = linhas_fora_plano.get(linha, 0.0) + abs(valor)
        grupo, agrupamento = linha2grupo.get(linha, ("", ""))

        porLinha[(loja, grupo, agrupamento, linha)] += valor
        if agrupamento:
            porAgrupamento[(loja, agrupamento)] += valor
        if grupo:
            porGrupo[(loja, grupo)] += valor

        lojas_set.add(loja)
        linhas_set.add(linha)
        if grupo: grupos_set.add(grupo)
        if agrupamento: agrups_set.add(agrupamento)

        # Provisão de aluguel (jan-abr): marca no detalhamento.
        if f.get("_fonte") == "provisao_aluguel":
            provisoes_detalhe.append({"loja": loja, "linha": linha, "valor": round(valor, 2),
                                      "obs": "Provisão de Aluguel", "label": "Provisão de Aluguel"})

    # ─── RATEIO POR VENDA BRUTA ──────────────────────────────────────────
    # Cada LINHA desses grupos é redistribuída entre as lojas proporcional
    # à participação da loja na Venda Bruta total. Decisão do usuário: esses
    # valores são centralizados e devem aparecer nas lojas proporcionalmente
    # à venda gerada (loja com 3% da venda absorve 3% do valor).
    # Receitas Comerciais entra no rateio, EXCETO 3 linhas que ficam com a
    # distribuição original por loja (vêm direto do título do fornecedor).
    GRUPOS_RATEIO_POR_VENDA = {
        "Despesas Comerciais", "Despesas Administrativas", "Receitas Comerciais",
        # Resultado Financeiro rateado por venda (decisão do usuário 2026-05),
        # exceto "Sobra de Caixa PDV" (ver LINHAS_RATEIO_EXCETO).
        "Resultado Financeiro",
        # Novas Unidades e Ajustes Gerenciais (ICMS, COFINS, PIS, Parcelamentos,
        # Compras p/ Construção, Sócio 30…) rateado por venda (decisão do usuário).
        "Novas Unidades e Ajustes Gerenciais",
    }
    LINHAS_RATEIO_EXCETO = {
        "Contrato Retorno", "Devolução de Fornecedores", "Descontos Obtidos",
        "Sobra de Caixa PDV",   # fica na loja de origem, não rateia
        # Despesas Tributárias (movidas p/ Despesas Administrativas em 2026-05):
        # o usuário pediu MANTER o valor real por loja (não ratear por venda),
        # apesar de Administrativas estar em GRUPOS_RATEIO_POR_VENDA.
        # (Taxa INMETRO fica em Despesas Operacionais via grupo explícito no meta/linhas.)
        "Taxa INMETRO", "DIFAL", "PIS, COFINS e CSLL Guia Unica", "INSSRF",
        "Taxa Administrativa", "Taxa ASBRA", "DCTF", "DAS", "ISSRF",
        "Taxa SPC", "Alvaras e Licencas das Lojas",
    }
    # Linhas específicas rateadas por venda mesmo NÃO estando nos grupos acima
    # (decisão do usuário 2026-05): valores centralizados que devem aparecer em
    # TODAS as lojas pela participação na venda geral.
    # NOTA: Assistencia Medica e Hospitalar, Uniformes e EPIs Operacao e
    # Plano de Saude Operacao SAÍRAM do rateio (decisão do usuário 2026-05): são
    # de "Despesas c/ Pessoal Operação" e devem manter os valores ORIGINAIS por loja.
    LINHAS_RATEIO_POR_VENDA = {
        "Cartaz Faixa e Outdoor", "Material de Expediente da Operaçao",
        "Lavanderia", "Plano de Saude Comercial", "Plano de Saude ADM",
        "Servicos Contratos Mensais PJ", "Servicos Contratos Mensais PJ Operacao",
        "Servicos Contratos Mensais PJ Comercial",
    }
    # FGTS/INSS NÃO entram no rateio geral por venda. Estas lojas formam
    # GRUPOS; dentro de cada grupo o FGTS/INSS é repartido entre as lojas pela
    # participação de venda DENTRO do grupo (decisão do usuário). Demais lojas
    # (fora de qualquer grupo) mantêm o valor próprio (já com mult. 90/8/2).
    GRUPOS_LOJAS_FGTS = [
        {"L02", "L04", "L06", "L12"},          # nros 102/104/106/112
        {"L26", "L27", "L01", "L03", "L08"},   # nros 26/27/101/103/108
        {"L28", "L09", "L117", "L17"},         # nros 28/29/117/109
        {"L25", "L15", "L19", "L22"},          # nros 125/215/219/222
    ]
    LINHAS_FGTS_GRUPO = {
        "FGTS Operacao", "INSS e GPS Operacao",
        "FGTS Comercial", "INSS e GPS Comercial",
        "FGTS ADM", "INSS e GPS ADM",
    }
    venda_por_loja = {}
    total_venda = 0.0
    for (loja, _g, _a, ln), v in porLinha.items():
        if ln == "Venda Bruta":
            venda_por_loja[loja] = venda_por_loja.get(loja, 0.0) + v
            total_venda += v
    if total_venda > 0:
        pct_por_loja = {loja: v / total_venda for loja, v in venda_por_loja.items()}
        # Soma cada LINHA dos grupos-alvo em todas as lojas → total a ratear
        # (pula as linhas-exceção e as de FGTS/INSS, que têm regra própria).
        total_por_linha: dict[tuple, float] = {}
        for (loja, g, a, ln), v in list(porLinha.items()):
            if (g in GRUPOS_RATEIO_POR_VENDA or ln in LINHAS_RATEIO_POR_VENDA) and ln not in LINHAS_RATEIO_EXCETO and ln not in LINHAS_FGTS_GRUPO:
                total_por_linha[(g, a, ln)] = total_por_linha.get((g, a, ln), 0.0) + v
        # Remove entradas antigas dessas linhas (todas as lojas)
        for k in [k for k in porLinha
                  if (k[1] in GRUPOS_RATEIO_POR_VENDA or k[3] in LINHAS_RATEIO_POR_VENDA) and k[3] not in LINHAS_RATEIO_EXCETO
                  and k[3] not in LINHAS_FGTS_GRUPO]:
            del porLinha[k]
        # Recria distribuído pela %-venda de cada loja
        for (g, a, ln), total in total_por_linha.items():
            for loja, pct in pct_por_loja.items():
                v = total * pct
                if v == 0:
                    continue
                porLinha[(loja, g, a, ln)] = v
                lojas_set.add(loja); linhas_set.add(ln)
                if g: grupos_set.add(g)
                if a: agrups_set.add(a)

        # ─── RATEIO INTERNO DOS GRUPOS DE LOJAS (FGTS/INSS) ──────────────
        # Para cada grupo e cada uma das 6 linhas de FGTS/INSS, soma o total
        # das lojas do grupo e redistribui ENTRE elas pela venda de cada uma
        # dentro do grupo.
        for grupo_lojas in GRUPOS_LOJAS_FGTS:
            venda_grupo = sum(venda_por_loja.get(lo, 0.0) for lo in grupo_lojas)
            if venda_grupo <= 0:
                continue
            for ln in LINHAS_FGTS_GRUPO:
                g, a = linha2grupo.get(ln, ("", ""))
                total_grupo = sum(porLinha.get((lo, g, a, ln), 0.0) for lo in grupo_lojas)
                if total_grupo == 0:
                    continue
                for lo in grupo_lojas:
                    porLinha[(lo, g, a, ln)] = total_grupo * (venda_por_loja.get(lo, 0.0) / venda_grupo)
                    lojas_set.add(lo); linhas_set.add(ln)
                    if g: grupos_set.add(g)
                    if a: agrups_set.add(a)

        # ─── RATEIO DAS PROVISÕES MANUAIS (lançamentoManual) ─────────────
        # Cada provisão (total sem loja, ex: 13º salário) é distribuída por
        # %-venda. Regra do usuário: a partir de mai/2026 a loja L117 recebe,
        # ALÉM da sua parcela própria, a parcela rateada para a L09 (onde está
        # a nroempresa 29). detalhe → provisoes_detalhe (drill-down).
        L117_HERDA_DE = "L09"   # nroempresa 29 está dentro de L09
        herda_117 = (ano, mes) >= (2026, 5) and "L117" in pct_por_loja and L117_HERDA_DE in pct_por_loja
        for ln, total in provisao_por_linha.items():
            if total == 0:
                continue
            g, a = linha2grupo.get(ln, ("", ""))
            obs = provisao_obs.get(ln, "Provisão")
            for loja, pct in pct_por_loja.items():
                v = total * pct
                if v == 0:
                    continue
                porLinha[(loja, g, a, ln)] += v
                provisoes_detalhe.append({"loja": loja, "linha": ln, "valor": round(v, 2), "obs": obs})
                lojas_set.add(loja); linhas_set.add(ln)
                if g: grupos_set.add(g)
                if a: agrups_set.add(a)
            if herda_117:
                extra = total * pct_por_loja[L117_HERDA_DE]
                if extra != 0:
                    porLinha[("L117", g, a, ln)] += extra
                    provisoes_detalhe.append({
                        "loja": "L117", "linha": ln, "valor": round(extra, 2),
                        "obs": f"{obs} (parcela herdada da {L117_HERDA_DE} / nro 29)",
                    })
                    lojas_set.add("L117"); linhas_set.add(ln)
                    if g: grupos_set.add(g)
                    if a: agrups_set.add(a)

        # ─── AJUSTE ALUGUEL DE IMOVEIS vs DRE PowerBI ─────────────────────
        # Completa a linha por loja somando SÓ o que falta em relação ao
        # PowerBI (lojas onde o PB tem mais despesa). Registrado no detalhe.
        if aluguel_pb:
            ALN = "Aluguel de Imoveis"
            g, a = linha2grupo.get(ALN, ("", ""))
            for loja, pb_val in aluguel_pb.items():
                local_val = porLinha.get((loja, g, a, ALN), 0.0)
                falta = pb_val - local_val   # ambos negativos (despesa)
                if falta < -0.01:            # só onde o PB tem MAIS despesa
                    porLinha[(loja, g, a, ALN)] += falta
                    provisoes_detalhe.append({
                        "loja": loja, "linha": ALN, "valor": round(falta, 2),
                        "obs": "Ajuste DRE PowerBI (aluguel faltante)",
                        "label": "AJUSTE DRE PowerBI",
                    })
                    lojas_set.add(loja); linhas_set.add(ALN)
                    if g: grupos_set.add(g)
                    if a: agrups_set.add(a)

        # ─── INSS e GPS vs DRE PowerBI ────────────────────────────────────
        # A query de despesas (codoperacao=6) só captura parte do INSS; o total
        # real (títulos incluídos) vem do PowerBI. Quando há PB, SUBSTITUI o INSS
        # do op-6 pelo valor cheio do PB por loja, aplicando 90% Operação /
        # 8% ADM / 2% Comercial. Sem PB (ex: mês corrente), mantém o op-6.
        if inss_pb:
            INSS_LINES = {"INSS e GPS Operacao", "INSS e GPS ADM", "INSS e GPS Comercial"}
            for k in [k for k in porLinha if k[3] in INSS_LINES]:
                del porLinha[k]
            INSS_SPLIT = [("INSS e GPS Operacao", 0.90), ("INSS e GPS ADM", 0.08), ("INSS e GPS Comercial", 0.02)]
            for loja, pb_val in inss_pb.items():
                for ln, pct in INSS_SPLIT:
                    g, a = linha2grupo.get(ln, ("", ""))
                    porLinha[(loja, g, a, ln)] += pb_val * pct
                    lojas_set.add(loja); linhas_set.add(ln)
                    if g: grupos_set.add(g)
                    if a: agrups_set.add(a)

        # ─── Linhas que vêm direto do drePB (1:1) — ver LINHAS_PB_DIRETO ──────
        if pb_diretas:
            for ln, por_loja in pb_diretas.items():
                g, a = linha2grupo.get(ln, ("", ""))
                for k in [k for k in porLinha if k[3] == ln]:   # remove o op-6
                    del porLinha[k]
                for loja, val in por_loja.items():
                    porLinha[(loja, g, a, ln)] += val
                    lojas_set.add(loja); linhas_set.add(ln)
                    if g: grupos_set.add(g)
                    if a: agrups_set.add(a)

        # ─── ALUGUEL: provisão de contrato p/ lojas SEM lançamento (mai/2026+) ──
        # De maio/2026 em diante: usa o título do sistema (op-16) quando há; nas
        # lojas SEM lançamento, provisiona o valor do contrato (meta/aluguelContrato)
        # e marca no detalhamento como "Provisão de Aluguel" (decisão user 2026-05-24).
        # Jan-abr não passam aqui (aluguel já é provisão fixa via fatos provisao_aluguel).
        if aluguel_contrato and (ano, mes) >= (2026, 5):
            ALN = "Aluguel de Imoveis"; g, a = linha2grupo.get(ALN, ("", ""))
            for loja, val in aluguel_contrato.items():
                if abs(porLinha.get((loja, g, a, ALN), 0.0)) < 1:   # sem lançamento no sistema
                    porLinha[(loja, g, a, ALN)] += val
                    provisoes_detalhe.append({"loja": loja, "linha": ALN, "valor": round(val, 2),
                                              "obs": "Provisão de Aluguel", "label": "Provisão de Aluguel"})
                    lojas_set.add(loja); linhas_set.add(ALN)
                    if g: grupos_set.add(g)
                    if a: agrups_set.add(a)

        # Recomputa porAgrupamento e porGrupo de porLinha pra refletir o
        # rateio — LINHAS_CALCULADAS (EBITDA etc) usa esses totais por loja.
        porAgrupamento = defaultdict(float)
        porGrupo = defaultdict(float)
        for (loja, gr, ag, _ln), v in porLinha.items():
            if ag: porAgrupamento[(loja, ag)] += v
            if gr: porGrupo[(loja, gr)] += v

    # ─── Aplica LINHAS_CALCULADAS (fórmulas pós-agregação) ───────────────
    # Index por loja pra lookup rápido nas fórmulas
    linha_por_loja: dict[str, dict[str, float]]    = defaultdict(lambda: defaultdict(float))
    agrup_por_loja: dict[str, dict[str, float]]    = defaultdict(lambda: defaultdict(float))
    grupo_por_loja: dict[str, dict[str, float]]    = defaultdict(lambda: defaultdict(float))
    for (loja, _g, _a, ln), v in porLinha.items():
        linha_por_loja[loja][ln] += v
    for (loja, ag), v in porAgrupamento.items():
        agrup_por_loja[loja][ag] += v
    for (loja, gr), v in porGrupo.items():
        grupo_por_loja[loja][gr] += v

    for f in LINHAS_CALCULADAS:
        nome  = f["nome"]
        agrup = f.get("agrupamento", "")
        grupo = dimensoes["agrupamento_para_grupo"].get(agrup, "")
        for loja in list(lojas_set):
            valor = f["calc"](
                lambda n, _l=loja: linha_por_loja[_l].get(n, 0.0),
                lambda n, _l=loja: agrup_por_loja[_l].get(n, 0.0),
                lambda n, _l=loja: grupo_por_loja[_l].get(n, 0.0),
            )
            if valor == 0:
                continue
            porLinha[(loja, grupo, agrup, nome)] = valor
            # Atualiza o index local pra que fórmulas posteriores possam
            # referenciar essa nova LINHA imediatamente.
            linha_por_loja[loja][nome] = valor
            linhas_set.add(nome)
            if grupo: grupos_set.add(grupo)
            if agrup: agrups_set.add(agrup)

    # Recomputa porAgrupamento e porGrupo a partir de porLinha — garante que
    # agrupamentos compartilhados (ex: IRPJ/CSLL com 2 linhas calculadas) e
    # grupos derivados (EBITDA, LAIR, etc) somem corretamente as linhas.
    porAgrupamento = defaultdict(float)
    porGrupo = defaultdict(float)
    for (loja, gr, ag, _ln), v in porLinha.items():
        if ag: porAgrupamento[(loja, ag)] += v
        if gr: porGrupo[(loja, gr)] += v
    # Atualiza tb os indexes locais (caso alguma fórmula referencie agrup/grupo
    # que foi recém criado por LINHA_CALCULADA — não é o caso atual, mas evita
    # bugs futuros).
    agrup_por_loja = defaultdict(lambda: defaultdict(float))
    grupo_por_loja = defaultdict(lambda: defaultdict(float))
    for (loja, ag), v in porAgrupamento.items():
        agrup_por_loja[loja][ag] = v
    for (loja, gr), v in porGrupo.items():
        grupo_por_loja[loja][gr] = v

    # Constrói índices ordenados — preserva ordem do meta/linhas quando possível
    def _ordena(presentes, ordenadas_meta):
        out = [x for x in ordenadas_meta if x in presentes]
        for x in sorted(presentes):
            if x not in out:
                out.append(x)
        return out

    lojas  = sorted(lojas_set)
    linhas = _ordena(linhas_set, dimensoes["linhas_ordenadas"])
    grupos = _ordena(grupos_set, dimensoes["grupos_ordenados"])
    agrups = _ordena(agrups_set, dimensoes["agrupamentos_ordenados"])

    iloja  = {x: i for i, x in enumerate(lojas)}
    igrupo = {x: i for i, x in enumerate(grupos)}
    iagrup = {x: i for i, x in enumerate(agrups)}
    ilinha = {x: i for i, x in enumerate(linhas)}

    return {
        "ano": ano,
        "mes": mes,
        "v": 2,
        "dim": {
            "lojas": lojas,
            "grupos": grupos,
            "agrupamentos": agrups,
            "linhas": linhas,
        },
        "porGrupo": [
            {"l": iloja[l], "g": igrupo[g], "v": round(v, 2)}
            for (l, g), v in porGrupo.items()
        ],
        "porAgrupamento": [
            {"l": iloja[l], "a": iagrup[a], "v": round(v, 2)}
            for (l, a), v in porAgrupamento.items()
        ],
        "porLinha": [
            {"l": iloja[l],
             "g": igrupo.get(g, 0),
             "a": iagrup.get(a, 0),
             "n": ilinha[ln],
             "v": round(v, 2)}
            for (l, g, a, ln), v in porLinha.items()
        ],
        "_diag": {
            "nrosSemLoja":      sorted(str(n) for n in nros_sem_loja if n is not None),
            "linhasForaPlano":  sorted(linhas_fora_plano.keys()),
            # TOP 10 LINHAs por valor absoluto agregado (pra priorizar no fix)
            "linhasForaPlanoTop": sorted(
                linhas_fora_plano.items(), key=lambda kv: -kv[1]
            )[:10],
        },
        "_provisoesDetalhe": provisoes_detalhe,
    }


def executar_rateio(db, ano: int, mes: int, cenario: str = "realizado") -> dict:
    """Pipeline completo: lê tudo, agrega, grava em meses/{ano-mes}."""
    print(f"\n>> Executando rateio {ano}-{mes:02d} ({cenario})...")

    fatos = _carregar_fatos_classificados(db, ano, mes)
    print(f"   fatos classificados:  {len(fatos):>5}")

    manuais = _carregar_lancamentos_manuais(db, ano, mes, cenario)
    print(f"   lançamentos manuais:  {len(manuais):>5}")

    dimensoes = _carregar_dimensoes(db)
    n_lojas = len(set(dimensoes["nroempresa_para_loja"].values()))
    print(f"   lojas no meta/lojas:  {n_lojas:>5}")
    print(f"   linhas no meta/linhas:{len(dimensoes['linha_para_grupo']):>5}")

    # V1: pool = classificados + manuais (manuais sem nroempresa serão ignorados
    # na agregação até a engine de rateio V2 distribuir nas lojas).
    fatos_pool = list(fatos) + manuais

    # PowerBI override DESATIVADO (decisão do usuário 2026-05: nenhuma linha vem
    # do PowerBI). INSS/FGTS Multa etc. vêm da consulta SQL (codoperacao=16). O
    # "Aluguel de Imoveis" agora é PROVISÃO fixa (fatos _fonte='provisao_aluguel',
    # = valor do contrato); o classificador IGNORA os títulos de aluguel no valor
    # da DRE (ficam só no rawOracle p/ detalhamento). Por isso a completagem do
    # aluguel via drePB (_carregar_aluguel_pb) foi DESLIGADA.

    # Contrato de aluguel (provisão p/ lojas sem lançamento, mai/2026+).
    aluguel_contrato = _carregar_aluguel_contrato(db)
    if aluguel_contrato and (ano, mes) >= (2026, 5):
        print(f"   aluguel contrato: {len(aluguel_contrato)} lojas (provisiona quem não tem lançamento)")

    # TODO V2: aplicar regras de rateio (driver/matriz/duplicacao/haircut)
    # for rateio in carregar_rateios_aplicaveis(db, mes, cenario):
    #     fatos_pool = aplicar_rateio(fatos_pool, rateio, dimensoes)

    doc = _agregar_em_doc_compacto(fatos_pool, dimensoes, ano, mes, aluguel_contrato=aluguel_contrato)
    diag = doc.pop("_diag", {})
    provisoes_detalhe = doc.pop("_provisoesDetalhe", [])
    doc["geradoEm"] = firestore.SERVER_TIMESTAMP

    chave = f"{ano:04d}-{mes:02d}"
    db.collection("meses").document(chave).set(doc, merge=False)

    # Detalhe das provisões rateadas (drill-down identifica como provisão).
    db.collection("provisoesDetalhadas").document(chave).set({
        "ano": ano, "mes": mes,
        "geradoEm": firestore.SERVER_TIMESTAMP,
        "total": len(provisoes_detalhe),
        "detalhes": provisoes_detalhe,
    }, merge=False)

    n_pontos = len(doc["porLinha"])
    print(f"   ✓ meses/{chave}: {len(doc['dim']['lojas'])} lojas × "
          f"{len(doc['dim']['linhas'])} linhas, {n_pontos} pontos")
    if diag.get("nrosSemLoja"):
        print(f"   ⚠ NROEMPRESAs sem loja em meta/lojas: {diag['nrosSemLoja']}")
    if diag.get("linhasForaPlano"):
        print(f"   ⚠ {len(diag['linhasForaPlano'])} LINHAs fora do plano de contas (TOP 10 por valor):")
        for linha, total in diag.get("linhasForaPlanoTop", []):
            print(f"      {total:>15,.2f}  {linha}")

    return {
        "ano": ano, "mes": mes, "cenario": cenario,
        "fatosClassificados":   len(fatos),
        "lancamentosManuais":   len(manuais),
        "lojas":                len(doc["dim"]["lojas"]),
        "linhas":               len(doc["dim"]["linhas"]),
        "pontos":               n_pontos,
        "nrosSemLoja":          diag.get("nrosSemLoja", []),
        "linhasForaPlano":      diag.get("linhasForaPlano", []),
        "linhasForaPlanoTop":   [{"linha": l, "valorAbs": v} for l, v in diag.get("linhasForaPlanoTop", [])],
    }
