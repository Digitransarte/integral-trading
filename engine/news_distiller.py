"""
Integral Trading — Destilação de Notícias
============================================
Pega numa notícia em bruto e usa o Claude para extrair:
driver tocado (da ficha) · sentido · relevância · resumo PT · impacto no preço.
Notícias consideradas ruído (relevância baixa) são descartadas.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL_FAST
from engine.knowledge import load_commodity, Commodity
from engine.news_feed import NewsItem

logger = logging.getLogger(__name__)

# Abaixo deste valor (0-10), considera-se ruído e descarta-se
_LIMIAR_RELEVANCIA = 4


@dataclass
class DistilledNews:
    titulo: str
    fonte: str
    url: str
    data: str
    origem: str
    driver_id: str        # id do driver da ficha, ou "candidato"
    driver_nome: str
    sentido: str          # "alta" / "baixa" / "neutro"
    relevancia: int       # 0-10
    resumo: str           # 1 frase em PT
    impacto: str          # impacto esperado no preço


def _prompt(noticia: NewsItem, ficha: Commodity) -> str:
    drivers_txt = "\n".join(
        f"- {d['id']}: {d['nome']} — {d.get('mecanismo','')}"
        for d in ficha.drivers
    )
    return f"""És um analista de mercado de {ficha.nome}. Analisa esta notícia.

DRIVERS CONHECIDOS DE {ficha.nome.upper()}:
{drivers_txt}

NOTÍCIA:
Título: {noticia.titulo}
Resumo: {noticia.resumo}
Fonte: {noticia.fonte} ({noticia.data})

Devolve APENAS um objeto JSON (sem texto à volta, sem ```), com esta estrutura:
{{
  "driver_id": "<id do driver tocado, ou 'candidato' se for relevante mas não couber em nenhum, ou 'nenhum' se irrelevante>",
  "sentido": "<alta|baixa|neutro> (efeito esperado no preço de {ficha.nome})",
  "relevancia": <inteiro 0-10, quão relevante é para quem negoceia {ficha.nome}>,
  "resumo": "<uma frase em português europeu>",
  "impacto": "<impacto esperado no preço, 1 frase em português europeu>"
}}

Se a notícia não tiver nada a ver com {ficha.nome} nem com os seus drivers, devolve relevancia 0 e driver_id 'nenhum'."""


def destilar(noticia: NewsItem, ficha: Commodity,
             client: Anthropic | None = None) -> DistilledNews | None:
    """Destila uma notícia. Devolve None se for ruído (relevância < limiar)."""
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY em falta — destilação desativada.")
        return None

    client = client or Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL_FAST,
            max_tokens=400,
            messages=[{"role": "user", "content": _prompt(noticia, ficha)}],
        )
        texto = resp.content[0].text.strip()
        # limpar cercas de código se vierem
        texto = texto.replace("```json", "").replace("```", "").strip()
        d = json.loads(texto)
    except Exception as e:
        logger.error("Erro a destilar '%s': %s", noticia.titulo[:40], e)
        return None

    relevancia = int(d.get("relevancia", 0))
    if relevancia < _LIMIAR_RELEVANCIA:
        return None  # ruído, descarta

    driver_id = d.get("driver_id", "candidato")
    drv = ficha.driver(driver_id)
    driver_nome = drv["nome"] if drv else ("(driver candidato)" if driver_id == "candidato" else driver_id)

    return DistilledNews(
        titulo=noticia.titulo,
        fonte=noticia.fonte,
        url=noticia.url,
        data=noticia.data,
        origem=noticia.origem,
        driver_id=driver_id,
        driver_nome=driver_nome,
        sentido=d.get("sentido", "neutro"),
        relevancia=relevancia,
        resumo=d.get("resumo", ""),
        impacto=d.get("impacto", ""),
    )


def destilar_lote(noticias: list[NewsItem], commodity_id: str) -> list[DistilledNews]:
    """Destila uma lista, descartando ruído. Devolve só as materiais."""
    ficha = load_commodity(commodity_id)
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resultado = []
    for n in noticias:
        d = destilar(n, ficha, client)
        if d:
            resultado.append(d)
    # ordenar por relevância (maior primeiro)
    resultado.sort(key=lambda x: x.relevancia, reverse=True)
    return resultado


if __name__ == "__main__":
    # Teste: python -m engine.news_distiller
    from engine.news_feed import recolher_finnhub

    kws = ["gold", "dollar", "fed", "rate", "inflation", "treasury"]
    brutas = recolher_finnhub(kws, dias=4)
    print(f"\n{len(brutas)} notícias em bruto → a destilar...\n")

    destiladas = destilar_lote(brutas, "ouro")
    print(f"{len(destiladas)} notícias materiais (resto descartado como ruído)\n")

    for d in destiladas:
        print(f"  [{d.relevancia}/10] {d.driver_nome} · {d.sentido}")
        print(f"    {d.resumo}")
        print(f"    → {d.impacto}")
        print(f"    ({d.fonte}, {d.data})")
        print()