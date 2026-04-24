"""Integral Trading — Base de Dados SQLite"""
import sqlite3, json
from datetime import datetime
from contextlib import contextmanager
from config import DB_PATH


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name   TEXT,
            tickers         TEXT,
            start_date      TEXT,
            end_date        TEXT,
            initial_capital REAL,
            total_trades    INTEGER DEFAULT 0,
            win_rate        REAL DEFAULT 0,
            profit_factor   REAL DEFAULT 0,
            total_return    REAL DEFAULT 0,
            max_drawdown    REAL DEFAULT 0,
            equity_curve    TEXT,
            errors          TEXT DEFAULT "[]",
            run_date        TEXT
        );
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        INTEGER REFERENCES backtest_runs(id),
            ticker        TEXT,
            strategy_name TEXT,
            entry_date    TEXT,
            entry_price   REAL,
            exit_date     TEXT,
            exit_price    REAL,
            exit_reason   TEXT DEFAULT "",
            pnl_pct       REAL DEFAULT 0,
            days_held     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            specialist    TEXT NOT NULL,
            role          TEXT NOT NULL,
            content       TEXT NOT NULL,
            created_at    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS positions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker        TEXT,
            strategy_name TEXT,
            entry_date    TEXT,
            entry_price   REAL,
            stop_price    REAL,
            target_1      REAL,
            target_2      REAL,
            current_price REAL,
            days_held     INTEGER DEFAULT 0,
            status        TEXT DEFAULT "open",
            exit_date     TEXT,
            exit_price    REAL,
            exit_reason   TEXT DEFAULT "",
            pnl_pct       REAL DEFAULT 0,
            score         REAL DEFAULT 0,
            catalyst      TEXT DEFAULT "",
            metadata      TEXT DEFAULT "{}"
        );
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_backtest(summary) -> int:
    init_db()
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO backtest_runs
              (strategy_name, tickers, start_date, end_date, initial_capital,
               total_trades, win_rate, profit_factor, total_return, max_drawdown,
               equity_curve, errors, run_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            summary.strategy_name,
            json.dumps(summary.config.tickers),
            summary.config.start_date.isoformat(),
            summary.config.end_date.isoformat(),
            summary.config.initial_capital,
            summary.total_trades,
            summary.win_rate,
            summary.profit_factor,
            summary.total_return_pct,
            summary.max_drawdown_pct,
            json.dumps(summary.equity_curve),
            json.dumps(getattr(summary, "errors", [])),
            datetime.utcnow().isoformat(),
        ))
        run_id = cur.lastrowid
        for t in summary.trades:
            conn.execute("""
                INSERT INTO backtest_trades
                  (run_id, ticker, strategy_name, entry_date, entry_price,
                   exit_date, exit_price, exit_reason, pnl_pct, days_held)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                run_id, t.ticker, t.strategy_name,
                t.entry_date.isoformat() if t.entry_date else None,
                t.entry_price,
                t.exit_date.isoformat() if t.exit_date else None,
                t.exit_price, t.exit_reason, t.pnl_pct, t.days_held,
            ))
    return run_id


def get_backtest_history(limit: int = 20) -> list:
    init_db()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, strategy_name, start_date, end_date, total_trades,
                   win_rate, profit_factor, total_return, max_drawdown, run_date
            FROM backtest_runs ORDER BY run_date DESC LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_open_positions() -> list:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE status='open' ORDER BY entry_date DESC"
        ).fetchall()
    return [dict(r) for r in rows]
