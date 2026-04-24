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
        raise HTTPException(404, detail=f"Estratégia '{req.strategy_name}' não encontrada")

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
