"""
Integral Trading — Actualização Diária com Análise de Trades
=============================================================
Actualiza posições, detecta stops/targets, analisa trades fechados.
"""
import sys, json, logging
from datetime import datetime, date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "tracker.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

from engine.data_feed import DataFeed
from engine.forward_tracker import ForwardTracker
from engine.learning import LearningEngine
from engine.trade_analyst import TradeAnalyst
from engine.database import get_conn, init_db
from config import POLYGON_API_KEY


def is_market_day() -> bool:
    return date.today().weekday() < 5


def save_daily_report(report: dict):
    init_db()
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date     TEXT NOT NULL,
                open_positions  INTEGER,
                closed_today    INTEGER,
                total_pnl_open  REAL,
                stops_hit       INTEGER,
                targets_hit     INTEGER,
                errors          INTEGER,
                summary_json    TEXT,
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute("DELETE FROM daily_reports WHERE report_date = ?",
                     (report["date"],))
        conn.execute("""
            INSERT INTO daily_reports
              (report_date, open_positions, closed_today, total_pnl_open,
               stops_hit, targets_hit, errors, summary_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            report["date"],
            report["open_positions"],
            report["closed_today"],
            report["total_pnl_open"],
            report["stops_hit"],
            report["targets_hit"],
            report["errors"],
            json.dumps(report),
            datetime.utcnow().isoformat(),
        ))


def main():
    logger.info("=" * 55)
    logger.info("Actualização diária a iniciar")
    logger.info("=" * 55)

    if not is_market_day():
        logger.info("Fim de semana — a saltar.")
        return

    today = date.today().isoformat()
    logger.info("Data: " + today)

    try:
        feed    = DataFeed(polygon_key=POLYGON_API_KEY)
        tracker = ForwardTracker(feed)

        open_before = tracker.get_open_positions()
        logger.info("Posições abertas: " + str(len(open_before)))

        if not open_before:
            logger.info("Nenhuma posição aberta.")
            save_daily_report({
                "date": today, "open_positions": 0, "closed_today": 0,
                "total_pnl_open": 0, "stops_hit": 0, "targets_hit": 0,
                "errors": 0, "positions": [], "closed": [],
            })
        else:
            # ── 1. Actualizar posições ────────────────────────────────────────
            summary    = tracker.update_all()
            open_after = tracker.get_open_positions()
            total_pnl  = sum(p.pnl_pct for p in open_after)

            logger.info("Actualizadas: " + str(summary.updated))
            logger.info("Stops: " + str(summary.stopped_out))
            logger.info("Targets: " + str(summary.target_hit))

            if summary.closed_positions:
                logger.info("Fechadas hoje:")
                for c in summary.closed_positions:
                    icon = "✅" if c["pnl_pct"] > 0 else "❌"
                    logger.info("  " + icon + " " + c["ticker"] +
                                " | " + c["reason"] +
                                " | " + str(c["pnl_pct"]) + "%")

            positions_data = [
                {
                    "ticker":        p.ticker,
                    "current_price": round(p.current_price, 2),
                    "pnl_pct":       round(p.pnl_pct, 1),
                    "days_held":     p.days_held,
                    "stop_price":    round(p.stop_price, 2),
                }
                for p in open_after
            ]

            save_daily_report({
                "date":           today,
                "open_positions": len(open_after),
                "closed_today":   len(summary.closed_positions),
                "total_pnl_open": round(total_pnl, 2),
                "stops_hit":      summary.stopped_out,
                "targets_hit":    summary.target_hit,
                "errors":         summary.errors,
                "positions":      positions_data,
                "closed":         summary.closed_positions,
            })

        # ── 2. Analisar trades fechados (Nível 2) ─────────────────────────────
        logger.info("")
        logger.info("Fase 2: Análise de trades fechados...")
        analyst = TradeAnalyst()
        lessons = analyst.analyse_pending()
        if lessons:
            logger.info(str(len(lessons)) + " novas lições adicionadas à knowledge base:")
            for l in lessons:
                icon = "✅" if l.get("outcome") == "WIN" else "❌"
                logger.info("  " + icon + " " + l.get("key_learning", "")[:100])
        else:
            logger.info("Sem novos trades para analisar.")

        # ── 3. Actualizar estatísticas (Nível 1) ──────────────────────────────
        logger.info("")
        logger.info("Fase 3: Actualizar estatísticas de aprendizagem...")
        le = LearningEngine()
        le.update()
        logger.info("Estatísticas actualizadas.")

    except Exception as e:
        logger.error("Erro: " + str(e))
        raise

    logger.info("")
    logger.info("Actualização diária concluída.")


if __name__ == "__main__":
    main()
