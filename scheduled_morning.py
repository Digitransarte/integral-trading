"""
Integral Trading — Geração Matinal Automática
===============================================
Script para o cron correr de madrugada. Para cada matéria-prima:
  1. Recolhe e destila notícias frescas (Finnhub → Claude)
  2. Gera o relatório matinal (regime + notícias + NCI)
  3. Guarda o relatório na base de dados

Uso:
    python scheduled_morning.py            # todas as fichas
    python scheduled_morning.py ouro       # só uma
"""
import sys
import logging
from datetime import datetime

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("matinal")


def processar(commodity_id: str) -> None:
    from engine.knowledge import load_commodity
    from engine.news_feed import recolher_finnhub
    from engine.news_distiller import destilar_lote
    from engine.news_store import guardar as guardar_noticias
    from engine.morning_report import gerar_relatorio, guardar_relatorio

    ficha = load_commodity(commodity_id)
    logger.info("=== %s ===", ficha.nome)

    # 1. Notícias frescas
    try:
        kws = [ficha.nome.lower(), "gold", "dollar", "fed", "rate",
               "inflation", "treasury", "yields"]
        brutas = recolher_finnhub(kws, dias=4)
        destiladas = destilar_lote(brutas, commodity_id)
        novas = guardar_noticias(commodity_id, destiladas)
        logger.info("Notícias: %d novas (%d materiais)", novas, len(destiladas))
    except Exception as e:
        logger.error("Falha nas notícias de %s: %s", commodity_id, e)

    # 2 + 3. Gerar e guardar o relatório
    try:
        r = gerar_relatorio(commodity_id)
        guardar_relatorio(r)
        logger.info("Relatório: %s · convicção %s · %s",
                    r.direcao_sintese.upper(), r.conviccao.upper(), r.leitura)
    except Exception as e:
        logger.error("Falha no relatório de %s: %s", commodity_id, e)


def main():
    from engine.knowledge import list_commodities

    if len(sys.argv) > 1:
        alvos = [sys.argv[1]]
    else:
        alvos = list_commodities()

    logger.info("Geração matinal — %s — alvos: %s",
                datetime.now().strftime("%Y-%m-%d %H:%M"), alvos)
    for cid in alvos:
        processar(cid)
    logger.info("Geração matinal concluída.")


if __name__ == "__main__":
    main()