"""
Integral Trading — Recolha de Notícias
========================================
Vai buscar notícias relevantes para uma matéria-prima, via Finnhub.
Esta camada SÓ recolhe (em bruto). A destilação (via Claude) é separada.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests

from config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

_FINNHUB_URL = "https://finnhub.io/api/v1"


@dataclass
class NewsItem:
    """Notícia em bruto, antes de destilada."""
    titulo: str
    resumo: str
    fonte: str
    url: str
    data: str          # ISO date
    origem: str = "finnhub"


def recolher_finnhub(keywords: list[str], dias: int = 3,
                     limite: int = 30) -> list[NewsItem]:
    """
    Recolhe notícias gerais de mercado do Finnhub e filtra pelas keywords
    (ex: ['gold', 'dollar', 'fed']). O Finnhub /news dá notícias gerais por
    categoria; filtramos por relevância textual.
    """
    if not FINNHUB_API_KEY:
        logger.warning("FINNHUB_API_KEY em falta — recolha desativada.")
        return []

    try:
        resp = requests.get(
            f"{_FINNHUB_URL}/news",
            params={"category": "general", "token": FINNHUB_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        artigos = resp.json()
    except Exception as e:
        logger.error("Erro a recolher do Finnhub: %s", e)
        return []

    corte = datetime.now() - timedelta(days=dias)
    kw = [k.lower() for k in keywords]
    items: list[NewsItem] = []

    for a in artigos:
        texto = f"{a.get('headline','')} {a.get('summary','')}".lower()
        if not any(k in texto for k in kw):
            continue
        # data vem como timestamp unix
        ts = a.get("datetime", 0)
        try:
            dt = datetime.fromtimestamp(ts)
        except Exception:
            dt = datetime.now()
        if dt < corte:
            continue
        items.append(NewsItem(
            titulo=a.get("headline", "").strip(),
            resumo=a.get("summary", "").strip(),
            fonte=a.get("source", "?"),
            url=a.get("url", ""),
            data=dt.date().isoformat(),
        ))
        if len(items) >= limite:
            break

    return items


if __name__ == "__main__":
    # Teste: python -m engine.news_feed
    # Keywords típicas do ouro (puxadas, no futuro, dos drivers da ficha)
    kws = ["gold", "dollar", "fed", "rate", "inflation", "treasury"]
    noticias = recolher_finnhub(kws, dias=4)
    print(f"\nRecolhidas {len(noticias)} notícias (keywords: {kws})\n")
    for n in noticias[:15]:
        print(f"  [{n.data}] {n.fonte}")
        print(f"    {n.titulo}")
        print()