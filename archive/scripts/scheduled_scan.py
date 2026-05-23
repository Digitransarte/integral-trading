"""
Integral Trading — Scanner Agendado com Decision Engine
=========================================================
Corre o scanner EP e avalia automaticamente cada candidato.
Agendado para as 15:00 (9:00 ET) todos os dias úteis.

Corre: python scheduled_scan.py
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
        logging.FileHandler(LOG_DIR / "scan.log", encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

from engine.data_feed import DataFeed
from engine.scanner import Scanner
from engine.strategies.ep_strategy import EpisodicPivotStrategy
from engine.decision_engine import DecisionEngine
from engine.database import get_conn, init_db
from universes import MAIN_UNIVERSE
from config import POLYGON_API_KEY


def is_market_day() -> bool:
    return date.today().weekday() < 5


def save_scan_results(candidates: list, scan_date: str):
    init_db()
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date     TEXT NOT NULL,
                ticker        TEXT NOT NULL,
                score         REAL,
                gap_pct       REAL,
                vol_ratio     REAL,
                current_price REAL,
                stop_loss     REAL,
                target_1      REAL,
                entry_window  TEXT,
                days_since_gap INTEGER,
                notes         TEXT,
                created_at    TEXT NOT NULL
            )
        """)
        conn.execute("DELETE FROM scan_results WHERE scan_date = ?", (scan_date,))
        for c in candidates:
            conn.execute("""
                INSERT INTO scan_results
                  (scan_date, ticker, score, gap_pct, vol_ratio, current_price,
                   stop_loss, target_1, entry_window, days_since_gap, notes, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                scan_date, c.ticker, round(c.score, 1), round(c.gap_pct, 2),
                round(c.vol_ratio, 1), round(c.current_price, 2),
                round(c.stop_loss, 2), round(c.target_1, 2),
                c.entry_window, c.days_since_gap, c.signal.notes,
                datetime.utcnow().isoformat(),
            ))


def save_scan_log(scan_date, tickers_scanned, candidates_found, duration, errors):
    init_db()
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date        TEXT NOT NULL,
                tickers_scanned  INTEGER,
                candidates_found INTEGER,
                duration_seconds REAL,
                errors           TEXT,
                created_at       TEXT NOT NULL
            )
        """)
        conn.execute("DELETE FROM scan_log WHERE scan_date = ?", (scan_date,))
        conn.execute("""
            INSERT INTO scan_log
              (scan_date, tickers_scanned, candidates_found,
               duration_seconds, errors, created_at)
            VALUES (?,?,?,?,?,?)
        """, (
            scan_date, tickers_scanned, candidates_found,
            round(duration, 1), json.dumps(errors),
            datetime.utcnow().isoformat(),
        ))


def main():
    logger.info("=" * 55)
    logger.info("Scanner EP + Decision Engine a iniciar")
    logger.info("=" * 55)

    if not is_market_day():
        logger.info("Fim de semana — a saltar.")
        return

    scan_date = date.today().isoformat()
    logger.info("Data: " + scan_date)

    try:
        # ── 1. Scanner ────────────────────────────────────────────────────────
        logger.info("Fase 1: Scanner EP...")
        feed     = DataFeed(polygon_key=POLYGON_API_KEY)
        strategy = EpisodicPivotStrategy()
        scanner  = Scanner(feed, strategy)
        result   = scanner.run(MAIN_UNIVERSE, lookback_days=60)

        candidates = result.top(20)
        logger.info("Candidatos: " + str(len(candidates)) +
                    " de " + str(result.tickers_scanned) + " tickers")

        save_scan_results(candidates, scan_date)
        save_scan_log(
            scan_date, result.tickers_scanned,
            result.total_candidates, result.duration_seconds,
            result.errors[:10],
        )

        if not candidates:
            logger.info("Nenhum candidato — a saltar Decision Engine.")
            return

        # ── 2. Decision Engine ────────────────────────────────────────────────
        logger.info("Fase 2: Decision Engine — a avaliar " +
                    str(len(candidates)) + " candidatos...")
        engine    = DecisionEngine()
        decisions = engine.evaluate_candidates(candidates)

        # Log das decisões
        enter_list = [d for d in decisions if d.action == "ENTER"]
        watch_list = [d for d in decisions if d.action == "WATCH"]
        skip_list  = [d for d in decisions if d.action == "SKIP"]

        logger.info("")
        logger.info("── DECISÕES ──────────────────────────────────")
        for d in decisions:
            logger.info(
                d.action_icon + " " + d.ticker +
                " → " + d.action +
                " | Confiança: " + str(round(d.confidence, 0)) + "%" +
                " | R/R: " + str(round(d.risk_reward, 2))
            )

        logger.info("")
        logger.info("ENTRAR (" + str(len(enter_list)) + "): " +
                    ", ".join(d.ticker for d in enter_list))
        logger.info("AGUARDAR (" + str(len(watch_list)) + "): " +
                    ", ".join(d.ticker for d in watch_list))
        logger.info("SALTAR (" + str(len(skip_list)) + "): " +
                    ", ".join(d.ticker for d in skip_list))

        if enter_list:
            logger.info("")
            logger.info("── TOP RECOMENDAÇÕES ─────────────────────────")
            for d in enter_list[:3]:
                logger.info("")
                logger.info(d.ticker + " @ $" + str(round(d.entry_price, 2)))
                logger.info("  Stop: $" + str(round(d.stop_loss, 2)) +
                            " | T1: $" + str(round(d.target_1, 2)))
                logger.info("  " + d.reasoning[:200])

    except Exception as e:
        logger.error("Erro: " + str(e))
        raise

    logger.info("")
    logger.info("Scan + Decision Engine concluidos.")


if __name__ == "__main__":
    main()
