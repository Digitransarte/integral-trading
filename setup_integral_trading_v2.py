"""
Integral Trading — Setup v2
============================
Corre este script dentro de C:\\integral-trading para actualizar todos os ficheiros.

Uso:
    cd C:\\integral-trading
    venv\\Scripts\\activate
    python setup_integral_trading.py
"""

import os
from pathlib import Path

BASE = Path(__file__).parent

DIRS = [
    "engine/strategies",
    "api/routes",
    "dashboard/pages",
    "data/strategies",
    "tests",
]

for d in DIRS:
    (BASE / d).mkdir(parents=True, exist_ok=True)

FILES = {}

# ── .env.example ──────────────────────────────────────────────────────────────

FILES[".env.example"] = """\
# Copia este ficheiro para .env e preenche as tuas chaves
POLYGON_API_KEY=a_tua_chave_aqui
ANTHROPIC_API_KEY=
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
"""

# ── requirements.txt ──────────────────────────────────────────────────────────

FILES["requirements.txt"] = """\
fastapi==0.115.0
uvicorn[standard]==0.30.0
streamlit==1.40.0
yfinance
pandas==2.2.0
requests==2.32.0
pydantic==2.9.0
python-dotenv==1.0.0
"""

# ── config.py ─────────────────────────────────────────────────────────────────

FILES["config.py"] = '''\
"""
Integral Trading — Configuração Global
Lê variáveis de ambiente do ficheiro .env na raiz do projecto.
"""
import os
from pathlib import Path

# Carregar .env automaticamente se existir
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
DB_PATH   = DATA_DIR / "integral_trading.db"
STRATEGIES_DIR = DATA_DIR / "strategies"

POLYGON_API_KEY   = os.getenv("POLYGON_API_KEY",   "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY",    "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")

ALPACA_PAPER    = True
ALPACA_BASE_URL = "https://paper-api.alpaca.markets" if ALPACA_PAPER else "https://api.alpaca.markets"

MAX_POSITION_SIZE_PCT = 0.05
MAX_OPEN_POSITIONS    = 10
DEFAULT_STOP_LOSS_PCT = 0.08
DEFAULT_LOOKBACK_DAYS = 365
MARKET_OPEN    = "09:30"
MARKET_CLOSE   = "16:00"
TIMEZONE       = "America/New_York"
API_HOST       = "0.0.0.0"
API_PORT       = 8000
DASHBOARD_PORT = 8501
'''

# ── __init__ files ────────────────────────────────────────────────────────────

for p in [
    "engine/__init__.py",
    "engine/strategies/__init__.py",
    "api/__init__.py",
    "api/routes/__init__.py",
    "dashboard/__init__.py",
    "dashboard/pages/__init__.py",
]:
    FILES[p] = ""

# ── engine/data_feed.py ───────────────────────────────────────────────────────

FILES["engine/data_feed.py"] = '''\
"""
Integral Trading — Data Feed
Camada única de dados. Polygon + yfinance fallback.
Compatível com yfinance >= 0.2.50 (MultiIndex columns).
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DataFeed:
    def __init__(self, polygon_key: str = ""):
        self.polygon_key  = polygon_key
        self._use_polygon = bool(polygon_key)

    def get_bars(self, ticker: str, days: int = 365, interval: str = "1d",
                 end_date: Optional[datetime] = None) -> pd.DataFrame:
        end   = end_date or datetime.utcnow()
        start = end - timedelta(days=days)
        return self._yfinance_bars(ticker, start, end, interval)

    def get_current_price(self, ticker: str) -> Optional[float]:
        try:
            df = self.get_bars(ticker, days=5)
            return float(df["close"].iloc[-1]) if not df.empty else None
        except Exception as e:
            logger.error(f"Erro preço {ticker}: {e}")
            return None

    def get_avg_volume(self, ticker: str, days: int = 20) -> Optional[float]:
        df = self.get_bars(ticker, days=days + 5)
        if df.empty or len(df) < 5:
            return None
        return float(df["volume"].tail(days).mean())

    def _yfinance_bars(self, ticker: str, start: datetime,
                       end: datetime, interval: str) -> pd.DataFrame:
        try:
            data = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=interval,
                progress=False,
                auto_adjust=True,
                group_by="ticker",
            )
        except Exception as e:
            logger.error(f"yfinance erro {ticker}: {e}")
            return pd.DataFrame()

        if data is None or data.empty:
            return pd.DataFrame()

        # Normalizar MultiIndex (yfinance >= 0.2.50)
        if isinstance(data.columns, pd.MultiIndex):
            top = data.columns.get_level_values(0)
            if ticker.upper() in top:
                data = data[ticker.upper()]
            elif ticker in top:
                data = data[ticker]
            else:
                data.columns = data.columns.get_level_values(-1)

        data.columns = [str(c).lower().strip() for c in data.columns]

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(data.columns)):
            logger.warning(f"Colunas inesperadas para {ticker}: {list(data.columns)}")
            return pd.DataFrame()

        data.index = pd.to_datetime(data.index).tz_localize(None)
        data = data[["open", "high", "low", "close", "volume"]].copy()

        for col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

        data.dropna(inplace=True)
        return data
'''

# ── engine/strategies/base.py ─────────────────────────────────────────────────

FILES["engine/strategies/base.py"] = '''\
"""Integral Trading — Estratégia Base"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    ticker: str
    strategy_name: str
    signal_date: datetime
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    score: float
    catalyst: str = ""
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def risk_pct(self):
        return abs(self.entry_price - self.stop_loss) / self.entry_price

    @property
    def reward_1_pct(self):
        return abs(self.target_1 - self.entry_price) / self.entry_price

    @property
    def risk_reward_1(self):
        return self.reward_1_pct / self.risk_pct if self.risk_pct else 0


@dataclass
class BacktestResult:
    ticker: str
    strategy_name: str
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime]
    exit_price: Optional[float]
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0


class BaseStrategy(ABC):
    name: str = "Base Strategy"
    description: str = ""
    version: str = "1.0"
    default_stop_loss_pct: float = 0.08
    default_hold_days: int = 20
    min_score: float = 60.0

    @abstractmethod
    def scan(self, ticker: str, df: pd.DataFrame) -> bool: ...

    @abstractmethod
    def generate_signal(self, ticker: str, df: pd.DataFrame) -> Optional[Signal]: ...

    def manage_position(self, signal: Signal, current_price: float,
                        days_held: int, df: pd.DataFrame) -> str:
        if current_price <= signal.stop_loss:
            return "stop"
        if current_price >= signal.target_1:
            return "exit"
        if days_held >= self.default_hold_days:
            return "exit"
        return "hold"

    def get_position_size(self, portfolio_value: float, price: float,
                          risk_pct: float = None) -> int:
        from config import MAX_POSITION_SIZE_PCT
        return max(1, int(portfolio_value * MAX_POSITION_SIZE_PCT / price))

    def __repr__(self):
        return f"<Strategy: {self.name} v{self.version}>"
'''

# ── engine/strategies/ep_strategy.py ─────────────────────────────────────────

FILES["engine/strategies/ep_strategy.py"] = '''\
"""Integral Trading — Episodic Pivot Strategy"""
from datetime import datetime
from typing import Optional
import pandas as pd
from engine.strategies.base import BaseStrategy, Signal


class EpisodicPivotStrategy(BaseStrategy):
    name = "Episodic Pivot"
    description = "Gap + volume explosivo num catalisador transformador"
    version = "1.0"

    MIN_GAP_PCT      = 5.0
    MIN_VOLUME_RATIO = 2.5
    MIN_PRICE        = 5.0
    default_stop_loss_pct = 0.08
    default_hold_days     = 20
    min_score             = 60.0

    def scan(self, ticker: str, df: pd.DataFrame) -> bool:
        if len(df) < 21:
            return False
        last, prev = df.iloc[-1], df.iloc[-2]
        if float(last["close"]) < self.MIN_PRICE:
            return False
        gap_pct  = (float(last["open"]) - float(prev["close"])) / float(prev["close"]) * 100
        day_move = (float(last["close"]) - float(prev["close"])) / float(prev["close"]) * 100
        if gap_pct < self.MIN_GAP_PCT and day_move < self.MIN_GAP_PCT:
            return False
        avg_vol = float(df["volume"].iloc[-21:-1].mean())
        vol_day = float(last["volume"])
        if avg_vol > 0 and vol_day / avg_vol < self.MIN_VOLUME_RATIO:
            return False
        return True

    def generate_signal(self, ticker: str, df: pd.DataFrame) -> Optional[Signal]:
        if not self.scan(ticker, df):
            return None
        last, prev    = df.iloc[-1], df.iloc[-2]
        current_price = float(last["close"])
        gap_pct       = (float(last["open"]) - float(prev["close"])) / float(prev["close"]) * 100
        avg_vol       = float(df["volume"].iloc[-21:-1].mean())
        vol_ratio     = float(last["volume"]) / avg_vol if avg_vol > 0 else 0
        score         = self._calculate_score(df, gap_pct, vol_ratio)
        if score < self.min_score:
            return None
        return Signal(
            ticker=ticker,
            strategy_name=self.name,
            signal_date=datetime.utcnow(),
            entry_price=current_price,
            stop_loss=current_price * (1 - self.default_stop_loss_pct),
            target_1=current_price * 1.15,
            target_2=current_price * 1.30,
            score=score,
            catalyst="Gap + Volume",
            notes=f"Gap: {gap_pct:.1f}% | Vol: {vol_ratio:.1f}x",
            metadata={"gap_pct": gap_pct, "vol_ratio": vol_ratio},
        )

    def _calculate_score(self, df, gap_pct, vol_ratio) -> float:
        score = 0.0
        if gap_pct >= 20:   score += 30
        elif gap_pct >= 10: score += 20
        elif gap_pct >= 5:  score += 10
        if vol_ratio >= 5:   score += 30
        elif vol_ratio >= 3: score += 20
        elif vol_ratio >= 2.5: score += 10
        ma20 = float(df["close"].iloc[-21:-1].mean())
        ma50 = float(df["close"].iloc[-51:-1].mean()) if len(df) >= 52 else ma20
        last_close = float(df.iloc[-1]["close"])
        if last_close > ma20 > ma50: score += 20
        elif last_close > ma20:      score += 10
        last = df.iloc[-1]
        rng  = float(last["high"]) - float(last["low"])
        if rng > 0:
            cp = (float(last["close"]) - float(last["low"])) / rng
            if cp >= 0.8:   score += 20
            elif cp >= 0.6: score += 10
        return min(score, 100.0)
'''

# ── engine/backtester.py ──────────────────────────────────────────────────────

FILES["engine/backtester.py"] = '''\
"""Integral Trading — Backtester"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd
import logging

from engine.strategies.base import BaseStrategy, BacktestResult
from engine.data_feed import DataFeed

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    tickers: list
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10_000.0
    commission_pct: float = 0.001
    max_concurrent_positions: int = 5
    next_day_execution: bool = True


@dataclass
class BacktestSummary:
    strategy_name: str
    config: "BacktestConfig"
    trades: list
    errors: list = field(default_factory=list)
    run_date: datetime = field(default_factory=datetime.utcnow)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_hold_days: float = 0.0
    equity_curve: list = field(default_factory=list)

    def build(self):
        closed = [t for t in self.trades if t.exit_price is not None]
        if not closed:
            return self
        self.total_trades = len(closed)
        wins   = [t for t in closed if t.pnl_pct > 0]
        losses = [t for t in closed if t.pnl_pct <= 0]
        self.winning_trades = len(wins)
        self.losing_trades  = len(losses)
        self.win_rate       = self.winning_trades / self.total_trades
        self.avg_win_pct    = sum(t.pnl_pct for t in wins)   / len(wins)   if wins   else 0
        self.avg_loss_pct   = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
        gp = sum(t.pnl_pct for t in wins)
        gl = abs(sum(t.pnl_pct for t in losses))
        self.profit_factor    = gp / gl if gl else float("inf")
        self.total_return_pct = sum(t.pnl_pct for t in closed)
        self.avg_hold_days    = sum(t.days_held for t in closed) / self.total_trades
        self._build_equity_curve(closed)
        return self

    def _build_equity_curve(self, trades):
        capital = self.config.initial_capital
        curve   = [capital]
        for t in sorted(trades, key=lambda x: x.exit_date or datetime.utcnow()):
            capital *= (1 + t.pnl_pct / 100)
            curve.append(capital)
        self.equity_curve = curve
        peak, max_dd = curve[0], 0.0
        for v in curve:
            if v > peak: peak = v
            dd = (peak - v) / peak
            if dd > max_dd: max_dd = dd
        self.max_drawdown_pct = max_dd * 100

    def to_dict(self):
        return {
            "strategy":         self.strategy_name,
            "total_trades":     self.total_trades,
            "win_rate":         round(self.win_rate * 100, 1),
            "avg_win_pct":      round(self.avg_win_pct, 2),
            "avg_loss_pct":     round(self.avg_loss_pct, 2),
            "profit_factor":    round(self.profit_factor, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "avg_hold_days":    round(self.avg_hold_days, 1),
            "errors":           self.errors,
        }


class Backtester:
    def __init__(self, feed: DataFeed, strategy: BaseStrategy):
        self.feed     = feed
        self.strategy = strategy

    def run(self, config: BacktestConfig) -> BacktestSummary:
        logger.info(f"Backtest: {self.strategy.name} | {len(config.tickers)} tickers")
        all_trades, errors = [], []

        for ticker in config.tickers:
            try:
                trades = self._run_ticker(ticker, config)
                all_trades.extend(trades)
                logger.debug(f"{ticker}: {len(trades)} trades")
            except Exception as e:
                msg = f"{ticker}: {str(e)}"
                errors.append(msg)
                logger.warning(f"Erro {msg}")

        summary = BacktestSummary(
            strategy_name=self.strategy.name,
            config=config,
            trades=all_trades,
            errors=errors,
        ).build()

        logger.info(
            f"Completo: {summary.total_trades} trades | "
            f"Win: {summary.win_rate:.1%} | PF: {summary.profit_factor:.2f} | "
            f"Erros: {len(errors)}"
        )
        return summary

    def _run_ticker(self, ticker: str, config: BacktestConfig) -> list:
        days = (config.end_date - config.start_date).days + 60
        df   = self.feed.get_bars(ticker, days=days, end_date=config.end_date)

        if df.empty or len(df) < 30:
            return []

        df = df[df.index >= pd.Timestamp(config.start_date)]
        if len(df) < 21:
            return []

        trades, position = [], None

        for i in range(20, len(df)):
            bar  = df.iloc[i]
            date = df.index[i]
            dfsf = df.iloc[:i+1]

            if position is not None:
                days_held     = (date - pd.Timestamp(position.signal_date)).days
                current_price = float(bar["close"])
                action = self.strategy.manage_position(position, current_price, days_held, dfsf)

                if action in ("exit", "stop"):
                    pnl = (current_price - position.entry_price) / position.entry_price * 100
                    pnl -= config.commission_pct * 100 * 2
                    trades.append(BacktestResult(
                        ticker=ticker,
                        strategy_name=self.strategy.name,
                        entry_date=position.signal_date,
                        entry_price=position.entry_price,
                        exit_date=date.to_pydatetime(),
                        exit_price=current_price,
                        exit_reason=action,
                        pnl_pct=pnl,
                        days_held=days_held,
                    ))
                    position = None
                continue

            if not self.strategy.scan(ticker, dfsf):
                continue

            signal = self.strategy.generate_signal(ticker, dfsf)
            if signal is None or signal.score < self.strategy.min_score:
                continue

            if config.next_day_execution and i + 1 < len(df):
                signal.entry_price = float(df.iloc[i+1]["open"])
                signal.signal_date = df.index[i+1].to_pydatetime()
            else:
                signal.signal_date = date.to_pydatetime()
            position = signal

        # Fechar posição aberta no fim do período
        if position is not None:
            lp  = float(df.iloc[-1]["close"])
            pnl = (lp - position.entry_price) / position.entry_price * 100
            trades.append(BacktestResult(
                ticker=ticker,
                strategy_name=self.strategy.name,
                entry_date=position.signal_date,
                entry_price=position.entry_price,
                exit_date=df.index[-1].to_pydatetime(),
                exit_price=lp,
                exit_reason="end_of_period",
                pnl_pct=pnl,
                days_held=(df.index[-1] - pd.Timestamp(position.signal_date)).days,
            ))

        return trades
'''

# ── engine/database.py ────────────────────────────────────────────────────────

FILES["engine/database.py"] = '''\
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
            "SELECT * FROM positions WHERE status=\'open\' ORDER BY entry_date DESC"
        ).fetchall()
    return [dict(r) for r in rows]
'''

# ── api/main.py ───────────────────────────────────────────────────────────────

FILES["api/main.py"] = '''\
"""Integral Trading — FastAPI"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import backtest, strategies, positions, scanner

app = FastAPI(title="Integral Trading API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])
app.include_router(backtest.router,   prefix="/backtest",   tags=["Backtest"])
app.include_router(positions.router,  prefix="/positions",  tags=["Positions"])
app.include_router(scanner.router,    prefix="/scanner",    tags=["Scanner"])

@app.get("/")
def root():   return {"status": "ok", "app": "Integral Trading", "version": "0.1.0"}

@app.get("/health")
def health(): return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=True)
'''

FILES["api/routes/strategies.py"] = '''\
from fastapi import APIRouter
router = APIRouter()

@router.get("/")
def list_strategies():
    return {"strategies": ["ep", "canslim"]}
'''

FILES["api/routes/positions.py"] = '''\
from fastapi import APIRouter
router = APIRouter()

@router.get("/")
def list_positions():
    from engine.database import get_open_positions
    return {"open": get_open_positions(), "closed": []}
'''

FILES["api/routes/scanner.py"] = '''\
from fastapi import APIRouter
router = APIRouter()

@router.get("/candidates")
def get_candidates():
    return {"candidates": []}
'''

FILES["api/routes/backtest.py"] = '''\
"""Rota de backtest."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class BacktestRequest(BaseModel):
    strategy_name: str
    tickers: list
    start_date: str
    end_date: str
    initial_capital: float = 10_000.0
    next_day_execution: bool = True

@router.post("/run")
def run_backtest(req: BacktestRequest):
    from engine.data_feed import DataFeed
    from engine.backtester import Backtester, BacktestConfig
    from engine.strategies.ep_strategy import EpisodicPivotStrategy
    from engine.database import save_backtest
    from config import POLYGON_API_KEY

    strategy_map = {
        "ep": EpisodicPivotStrategy(),
        "episodic_pivot": EpisodicPivotStrategy(),
    }
    strategy = strategy_map.get(req.strategy_name.lower())
    if not strategy:
        raise HTTPException(404, detail=f"Estratégia \'{req.strategy_name}\' não encontrada")

    feed   = DataFeed(polygon_key=POLYGON_API_KEY)
    config = BacktestConfig(
        tickers=req.tickers,
        start_date=datetime.fromisoformat(req.start_date),
        end_date=datetime.fromisoformat(req.end_date),
        initial_capital=req.initial_capital,
        next_day_execution=req.next_day_execution,
    )
    summary = Backtester(feed, strategy).run(config)
    save_backtest(summary)

    return {
        "summary": summary.to_dict(),
        "equity_curve": summary.equity_curve,
        "trades": [
            {"ticker": t.ticker,
             "entry_date":  t.entry_date.isoformat()  if t.entry_date  else None,
             "entry_price": round(t.entry_price, 2),
             "exit_date":   t.exit_date.isoformat()   if t.exit_date   else None,
             "exit_price":  round(t.exit_price, 2)    if t.exit_price  else None,
             "exit_reason": t.exit_reason,
             "pnl_pct":     round(t.pnl_pct, 2),
             "days_held":   t.days_held}
            for t in summary.trades
        ],
    }
'''

# ── dashboard/app.py ──────────────────────────────────────────────────────────

FILES["dashboard/app.py"] = '''\
"""Integral Trading — Dashboard"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.set_page_config(page_title="Integral Trading", page_icon="◈", layout="wide")

st.sidebar.markdown("## ◈ Integral Trading")
st.sidebar.markdown("---")
page = st.sidebar.radio("", ["Dashboard", "Backtest", "Histórico", "Scanner", "Posições"],
                        label_visibility="collapsed")
st.sidebar.markdown("---")
st.sidebar.caption("v0.2.0 — paper trading")

if page == "Dashboard":
    st.title("◈ Integral Trading")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Posições Abertas", "0")
    c2.metric("P&L Hoje", "—")
    c3.metric("Win Rate (30d)", "—")
    c4.metric("Profit Factor", "—")
    st.info("Sistema iniciado. Vai a **Backtest** para correr o primeiro teste.")

elif page == "Backtest":
    from pages.backtest import render
    render()

elif page == "Histórico":
    from pages.history import render
    render()

elif page in ("Scanner", "Posições"):
    st.title(page)
    st.info("Em desenvolvimento.")
'''

# ── dashboard/pages/backtest.py ───────────────────────────────────────────────

FILES["dashboard/pages/backtest.py"] = '''\
"""Dashboard — Backtest"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests

try:
    from engine.data_feed import DataFeed
    from engine.backtester import Backtester, BacktestConfig
    from engine.strategies.ep_strategy import EpisodicPivotStrategy
    from engine.database import save_backtest
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

API_BASE = "http://localhost:8000"

UNIVERSES = {
    "Personalizado":    [],
    "S&P 500 Sample":   ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AMD",
                         "ORCL","NFLX","ADBE","CRM","UBER","ABNB","SHOP","SNOW"],
    "Small Cap Growth": ["RXRX","HIMS","ACHR","JOBY","RKLB","ASTS","LUNR",
                         "SOUN","BBAI","IONQ"],
    "ETFs":             ["SPY","QQQ","IWM","XLK","XLV","XLE","XLF","XBI","SMH"],
}


def render():
    st.title("Backtest")

    api_ok = _check_api()
    if api_ok:
        st.success("API online", icon="🟢")
    elif ENGINE_AVAILABLE:
        st.info("Modo dev — engine directo", icon="🔵")
    else:
        st.error(f"Engine não disponível: {ENGINE_ERROR}", icon="🔴")
        return

    st.markdown("---")

    with st.form("bt_form"):
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Estratégia**")
            strategy_label = st.selectbox("s", ["Episodic Pivot (EP)", "CANSLIM"],
                                          label_visibility="collapsed")
            st.markdown("**Universo**")
            univ = st.selectbox("u", list(UNIVERSES.keys()),
                                label_visibility="collapsed")
            tickers_raw = ""
            if univ == "Personalizado":
                tickers_raw = st.text_area("Tickers (separados por vírgula ou linha)",
                                           placeholder="AAPL, MSFT, NVDA", height=90)
            else:
                preset = UNIVERSES[univ]
                st.caption(f"{len(preset)} tickers: {', '.join(preset[:5])}...")

        with c2:
            st.markdown("**Período**")
            d1c, d2c = st.columns(2)
            with d1c: date_start = st.date_input("Início", value=datetime.today()-timedelta(days=365))
            with d2c: date_end   = st.date_input("Fim",    value=datetime.today())
            st.markdown("**Capital inicial ($)**")
            capital     = st.number_input("cap", value=10_000, step=1_000, label_visibility="collapsed")
            next_day    = st.checkbox("Execução no dia seguinte (mais realista)", value=True)
            show_trades = st.checkbox("Mostrar lista de trades", value=True)
            save_to_db  = st.checkbox("Guardar resultado no histórico", value=True)

        submitted = st.form_submit_button("▶ Correr Backtest", use_container_width=True, type="primary")

    if not submitted:
        return

    tickers = (
        [t.strip().upper() for t in tickers_raw.replace(",", "\n").splitlines() if t.strip()]
        if univ == "Personalizado" else UNIVERSES[univ]
    )
    if not tickers:
        st.error("Adiciona pelo menos um ticker.")
        return

    if "CANSLIM" in strategy_label:
        st.warning("CANSLIM ainda não implementado — a usar EP.")

    with st.spinner(f"A correr backtest em {len(tickers)} tickers..."):
        if api_ok:
            result = _run_via_api("ep", tickers, str(date_start), str(date_end),
                                  float(capital), next_day)
        else:
            result = _run_direct(tickers, date_start, date_end,
                                 float(capital), next_day, save_to_db)

    if result:
        _show_results(result, show_trades)


def _run_direct(tickers, d1, d2, capital, next_day, save):
    try:
        feed   = DataFeed(polygon_key=POLYGON_API_KEY)
        config = BacktestConfig(
            tickers=tickers,
            start_date=datetime.combine(d1, datetime.min.time()),
            end_date=datetime.combine(d2, datetime.min.time()),
            initial_capital=capital,
            next_day_execution=next_day,
        )
        summary = Backtester(feed, EpisodicPivotStrategy()).run(config)
        if save and summary.total_trades > 0:
            run_id = save_backtest(summary)
            st.toast(f"Guardado no histórico (ID #{run_id})", icon="💾")
        if summary.errors:
            with st.expander(f"⚠️ {len(summary.errors)} erros durante o backtest"):
                for e in summary.errors:
                    st.text(e)
        return {
            "summary": summary.to_dict(),
            "equity_curve": summary.equity_curve,
            "trades": [
                {"ticker": t.ticker,
                 "entry_date":  t.entry_date.strftime("%Y-%m-%d")  if t.entry_date  else None,
                 "entry_price": round(t.entry_price, 2),
                 "exit_date":   t.exit_date.strftime("%Y-%m-%d")   if t.exit_date   else None,
                 "exit_price":  round(t.exit_price, 2)             if t.exit_price  else None,
                 "exit_reason": t.exit_reason,
                 "pnl_pct":     round(t.pnl_pct, 2),
                 "days_held":   t.days_held}
                for t in summary.trades
            ],
        }
    except Exception as e:
        st.error(f"Erro no engine: {e}")
        return None


def _run_via_api(strat, tickers, start, end, capital, next_day):
    try:
        r = requests.post(f"{API_BASE}/backtest/run",
                          json={"strategy_name": strat, "tickers": tickers,
                                "start_date": start, "end_date": end,
                                "initial_capital": capital,
                                "next_day_execution": next_day},
                          timeout=120)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Erro API: {e}")
        return None


def _check_api():
    try: return requests.get(f"{API_BASE}/health", timeout=2).status_code == 200
    except: return False


def _show_results(data: dict, show_trades: bool):
    s, trades, equity = data["summary"], data["trades"], data["equity_curve"]
    st.markdown("---")
    st.subheader("Resultados")

    if not s.get("total_trades"):
        st.warning("Nenhum trade gerado. Tenta um período mais longo ou universo diferente.")
        return

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Trades",        s["total_trades"])
    c2.metric("Win Rate",      f"{s[\'win_rate\']}%")
    c3.metric("Profit Factor", s["profit_factor"])
    c4.metric("Retorno",       f"{s[\'total_return_pct\']}%",
              delta=f"{s[\'total_return_pct\']}%")

    c5,c6,c7,c8 = st.columns(4)
    c5.metric("Avg Win",      f"{s[\'avg_win_pct\']}%")
    c6.metric("Avg Loss",     f"{s[\'avg_loss_pct\']}%")
    c7.metric("Max Drawdown", f"{s[\'max_drawdown_pct\']}%")
    c8.metric("Avg Hold",     f"{s[\'avg_hold_days\']} dias")

    if equity and len(equity) > 1:
        st.subheader("Equity Curve")
        st.line_chart(pd.DataFrame({"Capital ($)": equity}))
        a,b,c = st.columns(3)
        a.metric("Capital Inicial", f"${equity[0]:,.2f}")
        b.metric("Capital Final",   f"${equity[-1]:,.2f}")
        c.metric("Ganho/Perda",     f"${equity[-1]-equity[0]:+,.2f}")

    if trades:
        st.subheader("Distribuição P&L")
        st.bar_chart(pd.DataFrame({"P&L (%)": [t["pnl_pct"] for t in trades]}))

    if show_trades and trades:
        st.subheader(f"Trades ({len(trades)})")
        df = pd.DataFrame(trades).sort_values("pnl_pct", ascending=False).reset_index(drop=True)
        df["pnl_pct"] = df["pnl_pct"].map(lambda x: f"{x:+.1f}%")
        st.dataframe(df.rename(columns={
            "ticker": "Ticker", "entry_date": "Entrada", "entry_price": "P. Entrada",
            "exit_date": "Saída", "exit_price": "P. Saída", "pnl_pct": "P&L",
            "days_held": "Dias", "exit_reason": "Razão",
        }), use_container_width=True, hide_index=True)
        st.download_button("⬇ CSV", pd.DataFrame(trades).to_csv(index=False),
                           f"backtest_{datetime.today().strftime(\'%Y%m%d\')}.csv", "text/csv")
'''

# ── dashboard/pages/history.py ────────────────────────────────────────────────

FILES["dashboard/pages/history.py"] = '''\
"""Dashboard — Histórico de Backtests"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd


def render():
    st.title("Histórico de Backtests")

    try:
        from engine.database import get_backtest_history
        rows = get_backtest_history(limit=50)
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")
        return

    if not rows:
        st.info("Ainda não há backtests guardados. Corre o primeiro em **Backtest**.")
        return

    df = pd.DataFrame(rows)
    df["win_rate"]      = df["win_rate"].map(lambda x: f"{x*100:.1f}%")
    df["profit_factor"] = df["profit_factor"].map(lambda x: f"{x:.2f}")
    df["total_return"]  = df["total_return"].map(lambda x: f"{x:+.1f}%")
    df["max_drawdown"]  = df["max_drawdown"].map(lambda x: f"{x:.1f}%")
    df["run_date"]      = pd.to_datetime(df["run_date"]).dt.strftime("%Y-%m-%d %H:%M")

    st.dataframe(df[[
        "id","strategy_name","start_date","end_date",
        "total_trades","win_rate","profit_factor","total_return","max_drawdown","run_date"
    ]].rename(columns={
        "id": "#", "strategy_name": "Estratégia",
        "start_date": "Início", "end_date": "Fim",
        "total_trades": "Trades", "win_rate": "Win Rate",
        "profit_factor": "PF", "total_return": "Retorno",
        "max_drawdown": "Max DD", "run_date": "Data",
    }), use_container_width=True, hide_index=True)
'''

# ── run_backtest.py ───────────────────────────────────────────────────────────

FILES["run_backtest.py"] = '''\
"""
Integral Trading — Backtest CLI
Uso:
    python run_backtest.py
    python run_backtest.py --tickers AAPL MSFT NVDA --days 365 --verbose
    python run_backtest.py --universe small_cap --days 180
"""
import argparse, sys
from datetime import datetime, timedelta
sys.path.insert(0, ".")

from engine.data_feed import DataFeed
from engine.backtester import Backtester, BacktestConfig
from engine.strategies.ep_strategy import EpisodicPivotStrategy
from engine.database import save_backtest
from config import POLYGON_API_KEY

STRATEGIES = {"ep": EpisodicPivotStrategy}
UNIVERSES  = {
    "sp500_sample":  ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AMD",
                      "ORCL","NFLX","ADBE","CRM","UBER","ABNB","SHOP","SNOW"],
    "small_cap":     ["RXRX","HIMS","ACHR","JOBY","RKLB","ASTS","LUNR","SOUN","BBAI","IONQ"],
    "etf":           ["SPY","QQQ","IWM","XLK","XLV","XLE","XLF","XBI","SMH"],
}


def run(strategy_name, tickers, days, capital, verbose=False, save=True):
    print(f"\\n{'='*55}")
    print(f"  INTEGRAL TRADING — Backtest")
    print(f"{'='*55}")
    print(f"  Estratégia : {strategy_name.upper()}")
    print(f"  Tickers    : {len(tickers)} ({', '.join(tickers[:4])}{'...' if len(tickers)>4 else ''})")
    print(f"  Período    : últimos {days} dias")
    print(f"  Capital    : ${capital:,.0f}")
    print(f"{'='*55}\\n")

    feed     = DataFeed(polygon_key=POLYGON_API_KEY)
    strategy = STRATEGIES.get(strategy_name.lower(), EpisodicPivotStrategy)()
    config   = BacktestConfig(
        tickers=tickers,
        start_date=datetime.today() - timedelta(days=days),
        end_date=datetime.today(),
        initial_capital=capital,
    )
    summary = Backtester(feed, strategy).run(config)
    s = summary.to_dict()

    print(f"  Total trades   : {s[\'total_trades\']}")
    print(f"  Win rate       : {s[\'win_rate\']}%")
    print(f"  Profit factor  : {s[\'profit_factor\']}")
    print(f"  Retorno total  : {s[\'total_return_pct\']}%")
    print(f"  Max drawdown   : {s[\'max_drawdown_pct\']}%")
    print(f"  Avg win        : {s[\'avg_win_pct\']}%")
    print(f"  Avg loss       : {s[\'avg_loss_pct\']}%")
    print(f"  Avg hold (d)   : {s[\'avg_hold_days\']}")

    if summary.equity_curve:
        ini, fin = summary.equity_curve[0], summary.equity_curve[-1]
        print(f"\\n  Capital final  : ${fin:,.2f}  ({fin-ini:+,.2f})")

    if summary.errors:
        print(f"\\n  ⚠ Erros ({len(summary.errors)}):")
        for e in summary.errors:
            print(f"    - {e}")

    if save and summary.total_trades > 0:
        run_id = save_backtest(summary)
        print(f"\\n  💾 Guardado no histórico (ID #{run_id})")

    if verbose and summary.trades:
        print(f"\\n  {'Ticker':<8} {'Entrada':<12} {'Saída':<12} {'P&L':>8} {'Dias':>5} {'Razão'}")
        print(f"  {'─'*7} {'─'*11} {'─'*11} {'─'*8} {'─'*5} {'─'*10}")
        for t in sorted(summary.trades, key=lambda x: x.pnl_pct, reverse=True):
            en = t.entry_date.strftime("%Y-%m-%d") if t.entry_date else "—"
            ex = t.exit_date.strftime("%Y-%m-%d")  if t.exit_date  else "open"
            print(f"  {t.ticker:<8} {en:<12} {ex:<12} {t.pnl_pct:>+7.1f}% {t.days_held:>5} {t.exit_reason}")

    print(f"\\n{'='*55}\\n")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--strategy",  default="ep")
    p.add_argument("--tickers",   nargs="+")
    p.add_argument("--universe",  default=None)
    p.add_argument("--days",      type=int,   default=365)
    p.add_argument("--capital",   type=float, default=10_000.0)
    p.add_argument("--verbose",   "-v", action="store_true")
    p.add_argument("--no-save",   action="store_true", help="Não guardar na DB")
    args = p.parse_args()

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.universe:
        tickers = UNIVERSES.get(args.universe, [])
        if not tickers:
            print(f"Universo desconhecido. Disponíveis: {list(UNIVERSES.keys())}")
            sys.exit(1)
    else:
        tickers = UNIVERSES["sp500_sample"]
        print("A usar universo padrão: sp500_sample")

    run(args.strategy, tickers, args.days, args.capital,
        verbose=args.verbose, save=not args.no_save)
'''

# ── start.bat ─────────────────────────────────────────────────────────────────

FILES["start.bat"] = '''\
@echo off
cd /d C:\\integral-trading
call venv\\Scripts\\activate
echo.
echo  ◈ Integral Trading
echo  Dashboard a iniciar em http://localhost:8501
echo  Prima Ctrl+C para parar
echo.
streamlit run dashboard/app.py
'''

# ── data/strategies/ep_default.yaml ──────────────────────────────────────────

FILES["data/strategies/ep_default.yaml"] = """\
name: "Episodic Pivot"
version: "1.0"

entry:
  min_gap_pct: 5.0
  min_volume_ratio: 2.5
  min_price: 5.0
  max_days_since_event: 10

position:
  stop_loss_pct: 8.0
  target_1_pct: 15.0
  target_2_pct: 30.0
  max_hold_days: 20

scoring:
  min_score: 60
"""

# ── Escrever ficheiros ─────────────────────────────────────────────────────────

print("\n" + "="*55)
print("  INTEGRAL TRADING — Setup v2")
print("="*55)

updated, created = 0, 0
for path, content in FILES.items():
    full = BASE / path
    full.parent.mkdir(parents=True, exist_ok=True)
    exists = full.exists()
    full.write_text(content, encoding="utf-8")
    status = "actualizado" if exists else "criado"
    print(f"  [ok] {path} ({status})")
    if exists: updated += 1
    else: created += 1

# Criar .env se não existir
env_file = BASE / ".env"
if not env_file.exists():
    env_example = BASE / ".env.example"
    if env_example.exists():
        env_file.write_text(env_example.read_text())
        print(f"  [ok] .env criado a partir de .env.example")

print(f"\n  {created} criados, {updated} actualizados")
print("\n" + "="*55)
print("""
  Próximos passos:

  1. Instalar nova dependência:
     pip install python-dotenv

  2. (Opcional) Preencher chave Polygon no .env:
     Abre C:\\integral-trading\\.env e edita POLYGON_API_KEY

  3. Testar CLI:
     python run_backtest.py --universe small_cap --days 365 --verbose

  4. Dashboard (duplo clique em start.bat ou):
     streamlit run dashboard/app.py
""")
