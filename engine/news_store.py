"""
Integral Trading — Persistência de Notícias
=============================================
Guarda notícias destiladas (sem duplicar) e lê-as com desvalorização
temporal por relevância.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

from engine.database import get_conn, init_db
from engine.news_distiller import DistilledNews

logger = logging.getLogger(__name__)

_MEIA_VIDA_DIAS = 7


def _hash(commodity: str, titulo: str) -> str:
    return hashlib.sha256(f"{commodity}|{titulo}".encode("utf-8")).hexdigest()[:16]


def guardar(commodity: str, destiladas: list[DistilledNews]) -> int:
    """Guarda notícias destiladas, ignorando duplicados. Devolve nº de novas."""
    init_db()
    novas = 0
    with get_conn() as conn:
        for d in destiladas:
            h = _hash(commodity, d.titulo)
            cur = conn.execute("""
                INSERT OR IGNORE INTO noticias
                (commodity, titulo, fonte, url, data, origem, driver_id,
                 driver_nome, sentido, relevancia, resumo, impacto, hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (commodity, d.titulo, d.fonte, d.url, d.data, d.origem,
                  d.driver_id, d.driver_nome, d.sentido, d.relevancia,
                  d.resumo, d.impacto, h))
            if cur.rowcount > 0:
                novas += 1
    return novas


def _peso_temporal(data_str: str) -> float:
    """Desvaloriza por idade: 1.0 hoje, ~0.5 a 7 dias, decaimento exponencial."""
    try:
        d = datetime.fromisoformat(data_str)
    except Exception:
        return 0.5
    dias = (datetime.now() - d).days
    return 0.5 ** (dias / _MEIA_VIDA_DIAS)


def ler(commodity: str, dias: int = 14, min_relevancia: int = 0) -> list[dict]:
    """
    Lê notícias do período, com 'relevancia_ajustada' (relevância × peso temporal).
    Ordenadas pela relevância ajustada (maior primeiro).
    """
    init_db()
    corte = (datetime.now() - timedelta(days=dias)).date().isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT titulo, fonte, url, data, origem, driver_id, driver_nome,
                   sentido, relevancia, resumo, impacto
            FROM noticias
            WHERE commodity = ? AND data >= ? AND relevancia >= ?
            ORDER BY data DESC
        """, (commodity, corte, min_relevancia)).fetchall()

    linhas = [dict(r) for r in rows]
    for l in linhas:
        peso = _peso_temporal(l["data"])
        l["relevancia_ajustada"] = round(l["relevancia"] * peso, 1)
    linhas.sort(key=lambda x: x["relevancia_ajustada"], reverse=True)
    return linhas


if __name__ == "__main__":
    from engine.news_feed import recolher_finnhub
    from engine.news_distiller import destilar_lote

    print("\nA recolher e destilar...")
    brutas = recolher_finnhub(["gold", "dollar", "fed", "rate", "inflation"], dias=4)
    destiladas = destilar_lote(brutas, "ouro")

    novas = guardar("ouro", destiladas)
    print(f"Guardadas {novas} noticias novas (duplicados ignorados).")

    print("\nNa base de dados (com relevancia ajustada pelo tempo):\n")
    for l in ler("ouro"):
        print(f"  [{l['relevancia']}->{l['relevancia_ajustada']}] {l['driver_nome']} - {l['sentido']}")
        print(f"    {l['resumo']}  ({l['data']})")
        print()
