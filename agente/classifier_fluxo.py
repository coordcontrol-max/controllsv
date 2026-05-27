"""Classificador do Fluxo de Caixa — transforma rawOracle/{ano-mes}__fluxo_*
em fatos do fluxo no formato:
    (DATA, NROEMPRESA, BANCO, LINHA, VALOR)

V1: classifica por CODESPECIE pra fluxo_pago + por descrição do FI_OPERACAO
pra fluxo_opfin. fluxo_juros tem LINHA fixa "Juros e Multas".

LINHAs usadas devem existir em meta/linhasFluxo (cadastrado pelo user).
Quando não existir, marca como "Não classificado" e gera warning.
"""
from __future__ import annotations
import datetime as dt
from itertools import groupby


def _to_date(v):
    if v is None: return None
    if isinstance(v, (dt.date, dt.datetime)):
        return v.date() if isinstance(v, dt.datetime) else v
    if isinstance(v, str):
        try:
            return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).date()
        except Exception:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
                try: return dt.datetime.strptime(v[:19], fmt).date()
                except Exception: pass
    return None


def _val(row: dict, *names):
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
        if n.upper() in row and row[n.upper()] is not None:
            return row[n.upper()]
        if n.lower() in row and row[n.lower()] is not None:
            return row[n.lower()]
    return None


# ─── BASE_PAGO (fluxo_pago) — codoperacao 5 + 6 ───────────────────────────
# CODESPECIE → LINHA do fluxo. Mapa baseado nas espécies que aparecem em
# títulos a receber/pagar. Quando codespecie é desconhecido, vai pra
# "Não classificado" e gera warning pra o user cadastrar.
CODESPECIE_TO_LINHA_FLUXO = {
    # --- ENTRADAS (vendas/recbtos) ---
    "CARTAO":  "Recbto de Venda em Crédito",
    "CARDEB":  "Recbto de Venda em Débito",
    "TICKET":  "Recbto de Venda em Ticket",
    "CARDIG":  "Recbto de Venda em PIX",        # carteira digital
    "DRCOL":   "Recbto de Venda entre Unidades",
    "RECIC":   "Reciclagem E Osso",
    "CONVEN":  "Recbto de Convênios (Terceiros)",
    "PROREC":  "Recbto de Venda em Dinheiro (Protege)",
    # Acordos / contratos comerciais — cada CODESPECIE vai pra uma linha
    # específica, nome conforme DESCRICAO da FI_ESPECIE no Consinco.
    "ACRA22": "Acordo Aniversário 2022",
    "ACRA23": "Acordo Aniversário 2023",
    "ACRA24": "Acordo Aniversário 2024",
    "ACRA25": "Acordo Aniversário 2025",
    "ACRA26": "Acordo Aniversário 2026",
    "ACRCOM": "Acordo de Compras",
    "ACREX2": "Receita Adiantamento Judicial",
    "ACREXT": "Acordos Judicial Operação",
    "ACRFOR": "Acordo de Fornecimento",
    "ACRINA": "Acordo Inauguração",
    "ACRINT": "Acordo de Introdução",
    "ACRLOG": "Acordo de Logística",
    "ACRMGM": "Acordo Recomposição de Margem",
    "ACRMKT": "Acordo de Marketing",
    "ACRPEN": "Acordo Pentecostes",
    "ACRPON": "Acordo de Ponto Gôndola/Extra",
    "ACRPRE": "Acordo de Preço",
    "ACRQUE": "Acordo de Quebra",
    "ACRTRO": "Acordo de Troca",
    "ACRXTR": "Acordo Ação Extra",
    "CONTRT": "Contrato de Retorno",
    "DEVREC": "Devoluções a Receber de Fornec",
    # --- FORNECEDORES (saídas) ---
    "DUPP":   "(-) Fornecedores De Mercadorias",
    "DUPRPD": "(-) Fornecedores De Mercadorias",
    "DPCOL":  "(-) Pagto de Compra Entre Unidades",
    "ADIAFO": "Adiantamento A Fornecedores",
    # --- DESPESAS COM PESSOAL ---
    "ORDSAL": "Salarios E Ordenados Operaçao",
    "SALARO": "Salarios E Ordenados Operaçao",
    "SALADM": "Salarios E Ordenados ADM",
    "SALCOM": "Salarios E Ordenados Comercial",
    "ALIMEN": "Alimentacao Operaçao",
    "ALIADM": "Alimentação Adm",
    "TRANSV": "Transporte",
    "VALETR": "Transporte",
    "VTFOLH": "Transporte",
    "FERIAS": "Ferias",
    "FERIA2": "Ferias ADM",
    "PREMIO": "Premios e Bonus Operaçao",
    "BONUS":  "Premios e Bonus Operaçao",
    "FGTSRE": "Fgts Multa Recisoria",
    "FGTSR2": "Fgts Multa Recisoria ADM",
    "PESEXA": "Assistencia Medica E Hospitalar",
    "PLANO":  "Plano De Saude",
    "PLANO2": "Plano De Saude ADM",
    "EPI2":   "Uniformes E Epis ADM",
    "INTRAB": "Recisao Contratual",  # confirmado user (era Custas Judiciais Trabalhistas)
    "CONT":   "Honorarios Contabeis",  # confirmado user (era Contribuicao Sindical; TXSIND é a sindical)
    "INFOL2": "Adiantamento De Salario",
    # --- SERVIÇOS PÚBLICOS ---
    "ENERGI": "Energia Eletrica",
    "AGUA":   "Agua e Esgoto",
    "TELEF":  "Telefone",
    # --- ALUGUÉIS ---
    "ALUG":   "Aluguel De Imoveis",
    # --- MANUTENÇÃO ---
    "MANUTE": "Manutencao da Loja",
    "EQUIP":  "Material E Equipamentos Da Operação",
    "MAEQLJ": "Manutenção Construçao E Reformas",
    "INFEQ":  "Computadores e Perifericos",
    "INFEQ2": "Computadores e Perifericos ADM",
    # --- PUBLICIDADE ---
    # PROPAG removido — não deve movimentar nada no DFC (ver CODESPECIE_IGNORAR_FLUXO)
    "MIDIA":  "Anuncios em Midia Social",
    "PANFLE": "Panfletagem",
    "IMPRES": "Material Impresso Em Tabloide",
    # --- LOGÍSTICA ---
    "LOGALU": "Aluguel de Veiculos",
    "LOGCOM": "Despesas Diversas Com Logistica",
    "CONSOR": "Logistica Consorcio",
    # --- SERVIÇOS TERCEIRIZADOS ---
    "SERVT":  "Serviços De Consultoria Externa",
    "SERVTS": "Servicos Terceirizados De Seguranca",  # confirmado user (era Consultoria)
    "SERVTC": "Servicos Contratos Mensais Comercial",
    # --- IMPOSTOS ---
    "ICMSST": "ICMS-ST",
    "ICMSAN": "ICMS Antecipação",
    "TAXADM": "Taxa Administrativa",
    # --- DESPESAS COM VENDAS ---
    "RECARG": "Desagio Recargas",
    # --- EMBALAGENS / EXPEDIENTE ---
    "MATADM": "Material De Expediente Do Adm",
    "DESPU":  "Material De Expediente Da Operaçao",
    # --- JURÍDICAS ---
    "CUSCAR": "Custas Cartoriais",
    "CUSTJU": "Custas Judiciais Civis E Criminal",  # confirmado user (era Trabalhistas)
    "CUSJF":  "Custas Juridicas",
    "ADIAJU": "Adiantamento Judicial",
    # --- INVESTIMENTOS ---
    "INLJ29": "Investimento Loja 29",
    "INLJ30": "Investimento Loja 29",     # placeholder — conferir
    "AQUISE": "Aquisicao Imoveis",
    "INEQUI": "Investimentos Equipamentos",
    # --- EMPRÉSTIMOS / MÚTUOS ---
    "EMPREC": "Emprestimo A Receber",
    "EMPRES": "Emprestimo",
    "EMPRE2": "Emprestimo Banc Capital Giro",  # CODOP 6 + EMPRE2 (e exceção do fluxo_juros)
    "MUTREC": "Mútuo Entre Lojas a Receber",
    "MUTPAG": "Mútuo Entre Lojas a Pagar",
    # --- RETIRADAS DE SÓCIOS ---
    "DIRET2": "Socio 30",
    "DISTLU": "Socio 60",
    "DIRET":  "Socio 60",                  # DIRETORIA W — confirmado pelo user / DRE
    "DIRET3": "Socio 60",                  # DIRETORIA F — confirmado pelo user / DRE
    "DIRET4": "Socio 60",                  # DIRETORIA N — confirmado pela DRE

    # --- EXPANSÃO: ENTRADAS / Recbto de Contratos (subAgrupamento) ---
    "DRCOL2": "Recbto de Venda entre Unidades",     # = DRCOL
    "DUPR":   "Duplicata a Receber",                # nova
    "JURFOR": "Juridico Devedores Forneced",        # nova
    "PDDFOR": "Prov Perdas Devedores Forneced",     # nova
    "CREJUD": "Credito Judicial",                   # nova
    "BONIAC": "Bonificacoes em Geral",              # nova
    # --- EXPANSÃO: ENTRADAS (sem subAgrupamento) ---
    "CHQPRE": "Cheque Pre Datado",
    "IFOOD":  "iFood",
    "BOLPDV": "Boletos PDV",
    "CUSREC": "Custas Cartorio a Receber",
    "FORDA":  "Fornec Desp Acessorias a Receber",
    "DUPCXA": "Notas Fiscais Pend no Caixa",
    "OUTREC": "Outras Receitas Financeiras",        # já existe em Empréstimos/Mútuos Recebidos

    # --- EXPANSÃO: FORNECEDORES / DESPESAS GERAIS ---
    "DPCOL2": "(-) Pagto de Compra Entre Unidades", # = DPCOL
    "CHQPG":  "Cheques Pre a Pagar",                # nova
    "DEVPAG": "Devolução de Clientes",              # nova
    "DOACAO": "Doacoes e Brindes",                  # nova
    "CONC9":  "Conciliacao Contabil",               # nova

    # --- EXPANSÃO: IMPOSTOS ---
    "INSS":   "INSS e GPS",
    "ICMS":   "ICMS",
    "ICMSPA": "Parcelamento Estadual",
    "NPRVPA": "Parcelamento Federal",
    "COFINS": "COFINS",
    "PIS":    "PIS",
    "CSLL":   "CSLL a pagar",
    "IRPJ":   "IRPJ",
    "IRRF":   "IRRF",
    "IRRFNF": "IRRF",
    "ISSRF":  "Issrf",
    "IMPCC":  "PIS, COFINS e CSLL Guia Unica",
    "TXECAD": "Taxa ECAD",
    "TXDIV":  "Taxa Administrativa",
    "ALVARA": "Alvará",

    # --- EXPANSÃO: PESSOAL ---
    "FGTS":   "Fgts",
    "CURSOS": "Cursos",
    "TXSIND": "Contribuicao Sindical",
    "EPIS":   "Uniformes e EPIs",
    "VTADM":  "Transporte ADM",
    "13SAL":  "13 Salario",
    "BONCOM": "Premio E Bonus Comercial",
    "FUCLAV": "Lavanderia",
    "EVENT":  "Eventos E Treinamentos",
    "DESPF":  "Vales Funcionarios",                 # nova

    # --- EXPANSÃO: JURÍDICAS ---
    "ADV":    "Honorarios Advocaticios",

    # --- EXPANSÃO: MANUTENÇÃO / LOGÍSTICA ---
    "MANUTG": "Manutencao Geradores",
    "MANUTM": "Manutencao Motos",
    "MANUVS": "Manutencao Veiculo De Som",
    "MANUEN": "Manutencao Caminhao De Entrega",
    "LOGM":   "Manutencao De Veiculos Em Geral",
    "MANPRE": "Manutenção Construçao E Reformas",
    "LOCOMB": "Combustivel",
    "DESPLG": "Despesas Diversas Com Logistica",
    "LOGLEQ": "Locacao De Equipamentos Para Obras",
    "SEGUPD": "Seguro Predial",

    # --- EXPANSÃO: INFORMÁTICA ---
    "INTERN": "Internet",
    "INFOSU": "Suporte Tecnico",
    "INFOLI": "Licenca de Software Operação",
    "LICSOF": "Licenca de Software",
    "INFMAE": "Computadores e Perifericos",
    "INFOL3": "Licenca de Software Comercial",     # nova

    # --- EXPANSÃO: PUBLICIDADE ---
    "MARKT":  "Despesas Eventuais Com Marketing",
    "INMARK": "Despesas Com Marketing",
    "TELEV":  "Anuncios em Televisao",
    "DESPJR": "Anuncios Em Jornais",
    "PUBLI":  "Influencers E Eventos Patrocinados",
    "MUSICA": "Musica Ambiente E Vinhetas",

    # --- EXPANSÃO: SERVIÇOS TERCEIRIZADOS ---
    "SERVT2": "Servicos Terceirizados De Manutencao Adm",
    "SERVT4": "Servicos Contratos Mensais ADM",
    "SERVT5": "Servicos Contratos Mensais Comercial",
    "SERVT7": "Servicos Contratos Mensais Pj Comercial",  # Despesas Com Pessoal (confirmado user)
    "SERVTA": "Servicos Terceirizados Alarmes",
    "CONS9":  "Serviços De Consultoria Externa",
    "PPOJEN": "Projetos De Engenharia E Arquitetura",

    # --- EXPANSÃO: EMBALAGENS / EXPEDIENTE ---
    "DESP":   "Despesas Emergencial Lojas",          # confirmado pelo user

    # --- EXPANSÃO: INVESTIMENTOS ---
    "INIMOV": "Investimentos Imoveis",
    "INCOMP": "Investimento Compras Materiais",
    "SUPTAV": "Supermercados Tavares",
    "DESPA":  "Despesas Sobre Ativo Imobiliz",
    "INLJ22": "Investimento Loja 22",                # nova
    "INLJ24": "Investimento Loja 24",                # nova
    "INLJ27": "Investimento Loja 27",                # nova
    "INEPTG": "Investimento Posto EPTG",             # nova
    "INVCEU": "Investimento Obra CEU",               # nova
    "INLJ31": "Investimento Loja 31",                # nova (Arapoanga)

    # --- EXPANSÃO 2 (auditoria volumes histó ricos rawOracle) ---
    "CAMBIO": "Operacao De Cambio",                  # Empréstimos/Mútuos Recebidos
    "CONSUL": "Fluxo Consultoria",                   # Despesas Gerais
    "CONSCO": "Consultoria Contabil",                # Serviços Terceirizados
    "SERVT3": "Servicos Contratos Mensais Pj",       # Pessoal
    "SERVT6": "Servicos Contratos Mensais Pj Operacao",
    "IMOV":   "Aquisicao Imoveis",                   # Investimentos
    "RECISA": "Recisao De Funcionario",              # confirmado user (era Recisao Contratual)
    "RECIS2": "Rescisao Comercial",                  # Pessoal
    "DETET":  "Servicos Terceirizados Detetizacao",  # Serv. Terceirizados
    "IPTU":   "IPTU e TLP",                          # Aluguéis
    "AGENC":  "Agencias de Propaganda",              # Publicidade
    "GDJ":    "Deposito Judicial Processos Em Andamento",  # Jurídicas
    "INFOEQ": "Locaçao De Equipamentos De Informatica",    # Informática (ADM)
    "INFOE2": "Locaçao De Equipamentos Operação",          # Informática (OPER)
    "COMBGE": "Energia Gerador",                     # Serviços Públicos
    "PENSAO": "Pensao Alimenticia",                  # Pessoal
    "PENSCO": "Pensao Alimenticia Comercial",        # Pessoal
    "PENSAD": "Pensao Alimenticia ADM",              # Pessoal
    "MANUEM": "Manutencao Empilhadeira",             # Logística
    "TXSPC":  "Taxa SPC",                            # Impostos
    "FERIA3": "Ferias Comercial",                    # Pessoal
    "TXASBR": "Taxa ASBRA",                          # Impostos
    "AUTINF": "Autos De Infracao Em Geral",          # Jurídicas
    "EXTINT": "Extintores E Mat Contra Incendio",    # Manutenção
    "PLANO3": "Plano De Saude Comercial",            # Pessoal
    "FGTSR3": "Fgts Multa Recisoria Comercial",      # Pessoal
    "MANUTT": "Manutencao Caminhao De Transferencia",# Logística
    "DIFAL":  "DIFAL",                               # Impostos
    "MANUTP": "Manutencao De Veiculos Gestores",     # Logística
    "MANUTV": "Manutencao De Veiculos Gestores",     # Logística (mesma linha)
    "TXFUN":  "Taxa Funeraria",                      # Pessoal
    "VLADIA": "Adiantamento De Salario",             # Pessoal
    "ACRJUC": "Acordo Judicial",                     # Jurídicas
    "FCPST":  "Fundo de Combate à Pobreza",          # Impostos
    "ESTCON": "Descont Abatiment Nao Recorent",      # Desp. Financeiras / Expansão
    "FRETE":  "Fretes e Carretos",                   # Logística
    "CARTAZ": "Cartaz Faixa E Outdoor",              # Publicidade
    "CUSJC":  "Custas Juridicas Comercial",          # Jurídicas
    "DEVEX":  "Devolução de Clientes",               # Despesas Gerais

    # --- DESPESAS FINANCEIRAS — descartar ---
    # "TESCPG" — ignorar (igual no DRE)
}

# CODESPECIEs a descartar do fluxo (decisão consciente). Aplicado em
# fluxo_pago E fluxo_juros — não movimenta nada no DFC.
#   TESCPG — igual ao DRE
#   PROPAG — confirmado user: não deve movimentar em nenhum relatório de DFC
CODESPECIE_IGNORAR_FLUXO = {"TESCPG", "PROPAG"}

# CARTAO + NOMERAZAO contendo um destes (uppercase, sem acentos) →
# "Recbto de Venda em Cartão Próprio" em vez de "Recbto de Venda em Crédito".
# Adquirentes do cartão próprio do grupo (DM Pagamento / FortBrasil).
CARTAO_PROPRIO_RAZOES = (
    "DM INSTITUICAO DE PAGAMENTO",
    "FORTBRASIL",
)

# MUTPAG ("Mútuo Entre Lojas a Pagar") + NOMERAZAO contendo um destes →
# reclassifica pra "Mutuo A Pagar (entre grupos)" (agrupamento "Mútuo Entre
# Grupos"). Essas empresas são holdings, não lojas do grupo, então o mútuo é
# entre grupos e não entre lojas.
MUTUO_ENTRE_GRUPOS_RAZOES = (
    "WITHI PARTICIPACOES",
    "TIGO HOLDING",
    "AUTO POSTO IRMAOS PACIFICOS",
    "PEGUI COMERCIAL",
    "TAVARES CONSTRUTORA",
)


def classify_fluxo_pago(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """BASE_PAGO — codoperacao 5 (recebto) + 6 (pagto).
    obrigdireito='D' = direito (recebimento, +) | 'O' = obrigação (pagamento, -)."""
    fatos = []
    nao_mapeados: dict[str, int] = {}
    for r in rows:
        codespecie = _val(r, "CODESPECIE")
        if codespecie in CODESPECIE_IGNORAR_FLUXO:
            continue
        nro = _val(r, "NROEMPRESA")
        valor = _val(r, "VLROPERACAO")
        data = _to_date(_val(r, "DTAOPERACAO", "DTAQUITACAO", "DTACONTABILIZA"))
        obrigdireito = _val(r, "OBRIGDIREITO")
        if data is None or valor is None:
            continue
        linha = CODESPECIE_TO_LINHA_FLUXO.get(codespecie)
        if not linha:
            nao_mapeados[codespecie or "—"] = nao_mapeados.get(codespecie or "—", 0) + 1
            continue
        # Regra especial: CARTAO + adquirente "DM Pagamento" ou "FortBrasil"
        # → cartão próprio do grupo, vai pra linha separada.
        if codespecie == "CARTAO":
            razao = (_val(r, "NOMERAZAO") or "").upper()
            if any(p in razao for p in CARTAO_PROPRIO_RAZOES):
                linha = "Recbto de Venda em Cartão Próprio"
        # Regra especial: MUTPAG / MUTREC p/ holdings (WITHI / TIGO) →
        # "Mutuo A Pagar/Receber (entre grupos)" em vez de "Mútuo Entre Lojas
        # a Pagar/Receber". Sem isso, esses títulos aparecem duplicados — uma
        # vez em "entre lojas" e outra em "entre grupos" — quando o user já
        # confirmou que esses NOMERAZAOs são holdings, não lojas do grupo.
        if codespecie in ("MUTPAG", "MUTREC"):
            razao = (_val(r, "NOMERAZAO") or "").upper()
            if any(p in razao for p in MUTUO_ENTRE_GRUPOS_RAZOES):
                linha = "Mutuo A Pagar (entre grupos)" if codespecie == "MUTPAG" else "Mutuo A Receber (entre grupos)"
        # Se for pagamento (obrigação), inverte sinal
        sign = -1 if obrigdireito == "O" else +1
        fatos.append({
            "data": data.isoformat(),
            "nroempresa": int(nro) if nro is not None else None,
            "linha": linha,
            "valor": round(float(valor) * sign, 2),
            "_fonte": "fluxo_pago",
            "_codespecie": codespecie,
        })
    return fatos, nao_mapeados


# ─── FLUXO_JUROS — codoperacao 7 ──────────────────────────────────────────
def classify_fluxo_juros(rows: list[dict]) -> list[dict]:
    fatos = []
    for r in rows:
        nro = _val(r, "NROEMPRESA")
        valor = _val(r, "VLROPERACAO")
        data = _to_date(_val(r, "DTAOPERACAO", "DTAQUITACAO", "DTACONTABILIZA"))
        obrigdireito = _val(r, "OBRIGDIREITO")
        codespecie = _val(r, "CODESPECIE")
        if codespecie in CODESPECIE_IGNORAR_FLUXO:
            continue
        if data is None or valor is None:
            continue
        # Exceção: CODESPECIE=EMPRE2 não é juros — é empréstimo bancário
        # de capital de giro, vai pra linha separada.
        linha = "Emprestimo Banc Capital Giro" if codespecie == "EMPRE2" else "Juros e Multas"
        sign = -1 if obrigdireito == "O" else +1
        fatos.append({
            "data": data.isoformat(),
            "nroempresa": int(nro) if nro is not None else None,
            "linha": linha,
            "valor": round(float(valor) * sign, 2),
            "_fonte": "fluxo_juros",
            "_codespecie": codespecie,
        })
    return fatos


# ─── FLUXO_OPFIN — codoperacao várias (FI_CTACORLANCA) ────────────────────
# Mapa CODOPERACAO → LINHA do fluxo. Reaproveitado e adaptado do BASE5 do
# DRE, com extras 920, 15, 54 que aparecem só no fluxo.
CODOPERACAO_TO_LINHA_FLUXO = {
    34:  "Tarifa Bancária",      73:  "IOF",
    108: "Tarifa Bancária",      112: "Tarifa Bancária",
    129: "Tarifa Bancária",      132: "Tarifa Bancária",
    136: "Tarifa Bancária",      142: "Tarifa Bancária",
    191: "Tarifa Bancária",      205: "Tarifa Bancária",
    69:  "Tarifa Bancária",      130: "Tarifa Bancária",
    139: "Tarifa Bancária",
    # 140 (estorno) — ignorado, igual no DRE
    # 920, 15, 54 — pendentes, vão pra "Não classificado" até user mapear
    223: None, 217: None, 225: None, 214: None, 218: None, 220: None,
    216: None, 167: None, 219: None, 157: None,
}
CODOPERACAO_IGNORAR_FLUXO = {140}

# Regra Protege Cash: somente CODOPERACAO=15 ("Transferência Entre C/C")
# em que o HISTORICO contenha PROTEGE / PROTCASH / PROT.CASH / PROT CASH.
# Demais lançamentos de op 15 não são Protege Cash.
PROTEGE_CASH_CODOPS = {15}
PROTEGE_CASH_HIST_TOKENS = ("PROTEGE", "PROTCASH", "PROT.CASH", "PROT CASH")


def classify_fluxo_opfin(rows: list[dict]) -> tuple[list[dict], dict[int, int]]:
    fatos = []
    nao_mapeados: dict[int, int] = {}
    for r in rows:
        codop = _val(r, "CODOPERACAO")
        try: codop = int(codop) if codop is not None else None
        except (ValueError, TypeError): codop = None
        if codop in CODOPERACAO_IGNORAR_FLUXO:
            continue
        nro = _val(r, "NROEMPRESA")
        valor = _val(r, "VLRLANCAMENTO", "VLROPERACAO")
        data = _to_date(_val(r, "DTALANCTO", "DTAOPERACAO"))
        tipo = _val(r, "TIPOLANCTO")  # 'D' (débito) ou 'C' (crédito)
        if data is None or valor is None:
            continue
        linha = CODOPERACAO_TO_LINHA_FLUXO.get(codop)
        # Regra Protege Cash: somente CODOP 15 + HISTORICO casando os tokens
        # da lista (PROTEGE, PROTCASH, PROT.CASH, PROT CASH) → "Recbto de
        # Protege Cash" em Entradas Operacionais.
        if codop in PROTEGE_CASH_CODOPS:
            hist = (_val(r, "HISTORICO") or "").upper()
            if any(tok in hist for tok in PROTEGE_CASH_HIST_TOKENS):
                linha = "Recbto de Protege Cash"
        if not linha:
            nao_mapeados[codop] = nao_mapeados.get(codop, 0) + 1
            continue
        # Protege Cash sempre positivo (e considera só o lado crédito da
        # transferência D/C pra não duplicar o valor).
        if linha == "Recbto de Protege Cash":
            if tipo == "D":
                continue
            sign = +1
        else:
            sign = -1 if tipo == "D" else +1
        fatos.append({
            "data": data.isoformat(),
            "nroempresa": int(nro) if nro is not None else None,
            "linha": linha,
            "valor": round(float(valor) * sign, 2),
            "_fonte": "fluxo_opfin",
            "_codoperacao": codop,
        })
    return fatos, nao_mapeados


# ─── FLUXO_TRANSITORIAS — saldo das contas transitórias (DFC Consolidado) ──
# A query fluxo_transitorias traz TODOS os lançamentos da FI_CTACORLANCA das
# contas transitórias desde 01/01/1990 até :dta_fim. Aqui acumulamos esses
# lançamentos (crédito +, débito −, mesma convenção da fluxo_opfin) e geramos,
# para cada dia COM movimento dentro do mês-alvo, o SALDO acumulado da conta:
#
#   "Saldo Conta Transitória"           → todas as contas transitórias
#   "Saldo Conta Transitória (LUMI)"    → só a conta LUMI (SEQCTACORRENTE 361)
#   "Saldo Conta Transitória (Exceto LUMI)" → total − LUMI
#
# Linhas consolidadas (nroempresa=None): não entram nos docs por loja, só no
# fluxoCaixa/{ano-mes} agregado. As 3 LINHAs devem existir em meta/linhasFluxo.
# Mês-alvo = mês do maior DTALANCTO presente (= :dta_fim do /atualizar).
LUMI_SEQCTACORRENTE = {361}


def classify_fluxo_transitorias(rows: list[dict]) -> list[dict]:
    parsed = []
    for r in rows:
        seqcc = _val(r, "SEQCTACORRENTE")
        valor = _val(r, "VLRLANCAMENTO", "VLROPERACAO")
        data  = _to_date(_val(r, "DTALANCTO", "DTAOPERACAO"))
        tipo  = _val(r, "TIPOLANCTO")  # 'D' (débito) ou 'C' (crédito)
        if data is None or valor is None or seqcc is None:
            continue
        try: seqcc = int(seqcc)
        except (ValueError, TypeError): continue
        sign = -1 if tipo == "D" else +1
        parsed.append((data, seqcc, round(float(valor) * sign, 2)))
    if not parsed:
        return []
    parsed.sort(key=lambda x: x[0])

    # Mês-alvo: mês do último lançamento (= :dta_fim). Só esses dias viram fato.
    ultimo = parsed[-1][0]
    alvo_ano, alvo_mes = ultimo.year, ultimo.month

    fatos = []
    acum_total = 0.0
    acum_lumi  = 0.0
    for data, dia_iter in groupby(parsed, key=lambda x: x[0]):
        for (_d, seqcc, v) in dia_iter:
            acum_total += v
            if seqcc in LUMI_SEQCTACORRENTE:
                acum_lumi += v
        if data.year != alvo_ano or data.month != alvo_mes:
            continue
        iso = data.isoformat()
        for linha, val in (
            ("Saldo Conta Transitória",                round(acum_total, 2)),
            ("Saldo Conta Transitória (LUMI)",         round(acum_lumi, 2)),
            ("Saldo Conta Transitória (Exceto LUMI)",  round(acum_total - acum_lumi, 2)),
        ):
            fatos.append({
                "data": iso,
                "nroempresa": None,        # linha consolidada — não tem rateio por loja
                "linha": linha,
                "valor": val,
                "_fonte": "fluxo_transitorias",
            })
    return fatos


def classificar_fluxo(slug: str, rows: list[dict]) -> tuple[list[dict], dict]:
    """Dispatcher: slug → função classifier. Retorna (fatos, warnings)."""
    if slug == "fluxo_pago":
        fatos, nao_mapeados = classify_fluxo_pago(rows)
        return fatos, {"codespecies_nao_mapeados": nao_mapeados} if nao_mapeados else {}
    if slug == "fluxo_juros":
        return classify_fluxo_juros(rows), {}
    if slug == "fluxo_opfin":
        fatos, nao_mapeados = classify_fluxo_opfin(rows)
        return fatos, {"codops_nao_mapeados": nao_mapeados} if nao_mapeados else {}
    if slug == "fluxo_transitorias":
        return classify_fluxo_transitorias(rows), {}
    return [], {}
