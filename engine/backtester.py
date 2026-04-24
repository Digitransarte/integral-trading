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
