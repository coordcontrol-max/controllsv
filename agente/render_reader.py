"""Leitor do Postgres do Render (projeto-comercial) → substitui queries Oracle
lentas por leitura direta das tabelas que o cron-update.sh do João já mantém
atualizadas (ele sobe diariamente).

Slugs que migraram do Oracle pra Render:
  - venda_atual  ← agregado de venda_historico (mes_ref × cod_loja)

Os outros slugs (despesas, juros, compras, etc.) seguem no Oracle porque essas
tabelas não vivem no Render.

Shape de retorno: dicts com as MESMAS chaves/tipos que `linha_para_dict` produz
no Oracle. Assim `rodar_query` chama esse módulo de forma transparente —
classificador e engine continuam funcionando sem modificações.
"""
import os
import psycopg2
from typing import Any


# Mapeia slug → função desse módulo. agente.rodar_query consulta esse dict
# e, se o slug existir aqui, chama essa função em vez de rodar SQL no Oracle.
RENDER_SLUGS: dict[str, str] = {
    "venda_atual": "ler_venda_atual",
}


def _conn():
    """Conecta ao Render Postgres usando RENDER_DATABASE_URL do .env.
    Connect_timeout curto pra falhar rápido se o DNS/rede pifar (em vez de
    travar a thread do agente)."""
    url = os.environ.get("RENDER_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "RENDER_DATABASE_URL não definida — adicione no .env do agente "
            "(External URL do Postgres do projeto-comercial no Render)."
        )
    return psycopg2.connect(url, connect_timeout=15)


def ler_venda_atual(ano: int, mes: int) -> list[dict[str, Any]]:
    """Equivalente à query Oracle 'venda_atual' — agrega venda_historico
    (Render, mantido pelo João via cron-update.sh) por (mes_ref, cod_loja).

    Retorna 1 linha por loja com:
        ANO         str  '2026'
        MES         str  '05'  (zero-padded, como TO_CHAR(DTAVDA,'MM'))
        NROEMPRESA  int
        TICKETS     int   (∑ nro_documentos)
        VENDA       float (∑ valor_total — venda líquida = vendas − devoluções)
        MARGEM      float (∑ lucratividade_total)
        VERBA       float (∑ verba_bonificacao)

    Validado em 2026-05-26: Maio Render = R$ 46.379.461,42 = Painel KPIs.
    """
    mes_ref = f"{ano:04d}-{mes:02d}"
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                cod_loja,
                COALESCE(SUM(nro_documentos), 0)::int       AS tickets,
                COALESCE(SUM(valor_total), 0)::float        AS venda,
                COALESCE(SUM(lucratividade_total), 0)::float AS margem,
                COALESCE(SUM(verba_bonificacao), 0)::float  AS verba
            FROM venda_historico
            WHERE mes_ref = %s
              AND cod_loja IS NOT NULL
            GROUP BY cod_loja
            ORDER BY cod_loja
        """, (mes_ref,))
        rows = []
        for cod_loja, tickets, venda, margem, verba in cur.fetchall():
            rows.append({
                "ANO": f"{ano:04d}",
                "MES": f"{mes:02d}",
                "NROEMPRESA": int(cod_loja),
                "TICKETS": int(tickets or 0),
                "VENDA": float(venda or 0),
                "MARGEM": float(margem or 0),
                "VERBA": float(verba or 0),
            })
        cur.close()
        return rows
    finally:
        conn.close()


# Dispatcher usado pelo agente.rodar_query.
def rodar_slug(slug: str, ano: int, mes: int) -> list[dict[str, Any]]:
    fn_name = RENDER_SLUGS.get(slug)
    if not fn_name:
        raise KeyError(f"slug '{slug}' não está mapeado em RENDER_SLUGS")
    fn = globals()[fn_name]
    return fn(ano, mes)


if __name__ == "__main__":
    # Smoke test: python3 render_reader.py [ano] [mes]
    import sys
    ano = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    mes = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    rows = ler_venda_atual(ano, mes)
    print(f"venda_atual {ano}-{mes:02d}: {len(rows)} lojas")
    total_v = sum(r["VENDA"] for r in rows)
    total_m = sum(r["MARGEM"] for r in rows)
    print(f"  ∑VENDA = R$ {total_v:>16,.2f}")
    print(f"  ∑MARGEM = R$ {total_m:>15,.2f}")
    for r in rows[:5]:
        print(f"    loja {r['NROEMPRESA']:>3}: venda={r['VENDA']:>14,.2f}  margem={r['MARGEM']:>12,.2f}")
