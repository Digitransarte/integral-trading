"""Integral Trading — Backtester v2.1
Modos de entrada configuráveis:
- next_day_open: open do dia seguinte ao EP (original)
- ep_close: fecho do dia do EP (mais próximo do método Pradeep)
- next_day_filtered: open do dia seguinte, só se ≤ MAX_CHASE_PCT do open do EP
"""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import pandas as pd
import logging

from engine.strategies.base import BaseStrategy, BacktestResult
from engine.data_feed import DataFeed

logger = logging.getLogger(__name__)


def _load_knowledge() -> dict:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "knowledge", "ep_strategy.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@dataclass
class BacktestConfig:
    tickers: list
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10_000.0
    commission_pct: float = 0.001
    max_concurrent_positions: int = 5
    next_day_execution: bool = True  # mantido para compatibilidade

    # Modo de entrada:
    # "next_day_open"     — open do dia seguinte (original)
    # "ep_close"          — fecho do dia do EP
    # "next_day_filtered" — open do dia seguinte, só se não perseguiu demasiado
    entry_mode: str = "ep_close"

    # Só para entry_mode="next_day_filtered":
    # máximo de valorização aceite desde o open do EP até ao open do dia seguinte
    max_chase_pct: float = 3.0


@dataclass
class EnrichedBacktestResult(BacktestResult):
    """BacktestResult com métricas adicionais do knowledge JSON."""
    vol_ratio:       float = 0.0
    neglect_score:   float = 0.0
    gap_pct:         float = 0.0
    entry_window:    str   = "UNKNOWN"
    candle_strength: float = 0.0
    entry_mode:      str   = ""


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
    breakdown: dict = field(default_factory=dict)

    def build(self):
        closed = [t for t in self.trades if t.exit_price is not None]
        if not closed:
            return self

        self.total_trades   = len(closed)
        wins                = [t for t in closed if t.pnl_pct > 0]
        losses              = [t for t in closed if t.pnl_pct <= 0]
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
        self._build_breakdown(closed)
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

    def _build_breakdown(self, trades):
        def stats(group):
            if not group:
                return {"trades": 0, "win_rate": 0, "avg_pnl": 0, "profit_factor": 0}
            wins   = [t for t in group if t.pnl_pct > 0]
            losses = [t for t in group if t.pnl_pct <= 0]
            gp = sum(t.pnl_pct for t in wins)
            gl = abs(sum(t.pnl_pct for t in losses))
            return {
                "trades":        len(group),
                "win_rate":      round(len(wins) / len(group) * 100, 1),
                "avg_pnl":       round(sum(t.pnl_pct for t in group) / len(group), 2),
                "profit_factor": round(gp / gl, 2) if gl else 0,
            }

        enriched = [t for t in trades if isinstance(t, EnrichedBacktestResult)]
        if not enriched:
            return

        self.breakdown["entry_window"] = {
            w: stats([t for t in enriched if t.entry_window == w])
            for w in ["PRIME", "OPEN", "LATE"]
        }
        self.breakdown["volume_ratio"] = {
            "< 5x":  stats([t for t in enriched if t.vol_ratio < 5]),
            "5-10x": stats([t for t in enriched if 5 <= t.vol_ratio < 10]),
            "> 10x": stats([t for t in enriched if t.vol_ratio >= 10]),
        }
        self.breakdown["neglect"] = {
            "com neglect (>= 20)": stats([t for t in enriched if t.neglect_score >= 20]),
            "sem neglect (< 20)":  stats([t for t in enriched if t.neglect_score < 20]),
        }
        self.breakdown["gap"] = {
            "8-10%":  stats([t for t in enriched if 8 <= t.gap_pct < 10]),
            "10-15%": stats([t for t in enriched if 10 <= t.gap_pct < 15]),
            "> 15%":  stats([t for t in enriched if t.gap_pct >= 15]),
        }
        self.breakdown["candle_strength"] = {
            "forte (>= 0.7)": stats([t for t in enriched if t.candle_strength >= 0.7]),
            "fraco (< 0.7)":  stats([t for t in enriched if t.candle_strength < 0.7]),
        }

    def to_dict(self):
        return {
            "strategy":         self.strategy_name,
            "entry_mode":       self.config.entry_mode,
            "total_trades":     self.total_trades,
            "win_rate":         round(self.win_rate * 100, 1),
            "avg_win_pct":      round(self.avg_win_pct, 2),
            "avg_loss_pct":     round(self.avg_loss_pct, 2),
            "profit_factor":    round(self.profit_factor, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "avg_hold_days":    round(self.avg_hold_days, 1),
            "breakdown":        self.breakdown,
            "errors":           self.errors,
        }


class Backtester:
    def __init__(self, feed: DataFeed, strategy: BaseStrategy):
        self.feed       = feed
        self.strategy   = strategy
        self._knowledge = _load_knowledge()

    def run(self, config: BacktestConfig) -> BacktestSummary:
        logger.info(f"Backtest: {self.strategy.name} | {len(config.tickers)} tickers | mode: {config.entry_mode}")
        all_trades, errors = [], []

        for ticker in config.tickers:
            try:
                trades = self._run_ticker(ticker, config)
                all_trades.extend(trades)
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
            f"Win: {summary.win_rate:.1%} | PF: {summary.profit_factor:.2f}"
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

                    meta          = position.metadata if hasattr(position, "metadata") else {}
                    vol_ratio     = meta.get("vol_ratio", 0)
                    neglect_score = meta.get("neglect_score", 0)
                    gap_pct       = meta.get("gap_pct", 0)
                    entry_window  = self._classify_window(meta.get("days_since_gap", 0))

                    signal_bar = dfsf.iloc[-1]
                    rng = float(signal_bar["high"]) - float(signal_bar["low"])
                    candle_strength = (
                        (float(signal_bar["close"]) - float(signal_bar["low"])) / rng
                        if rng > 0 else 0.5
                    )

                    trades.append(EnrichedBacktestResult(
                        ticker=ticker,
                        strategy_name=self.strategy.name,
                        entry_date=position.signal_date,
                        entry_price=position.entry_price,
                        exit_date=date.to_pydatetime(),
                        exit_price=current_price,
                        exit_reason=action,
                        pnl_pct=pnl,
                        days_held=days_held,
                        vol_ratio=vol_ratio,
                        neglect_score=neglect_score,
                        gap_pct=gap_pct,
                        entry_window=entry_window,
                        candle_strength=candle_strength,
                        entry_mode=config.entry_mode,
                    ))
                    position = None
                continue

            if not self.strategy.scan(ticker, dfsf):
                continue

            signal = self.strategy.generate_signal(ticker, dfsf)
            if signal is None or signal.score < self.strategy.min_score:
                continue

            ep_bar = df.iloc[i]

            # ── Determinar preço e data de entrada ──────────────────────────
            if config.entry_mode == "ep_close":
                # Entrar no fecho do dia do EP
                signal.entry_price = float(ep_bar["close"])
                signal.signal_date = date.to_pydatetime()

            elif config.entry_mode == "next_day_filtered":
                # Entrar no open do dia seguinte, só se não perseguiu demasiado
                if i + 1 >= len(df):
                    continue
                next_open = float(df.iloc[i+1]["open"])
                ep_open   = float(ep_bar["open"])
                if ep_open > 0:
                    chase_pct = (next_open - ep_open) / ep_open * 100
                    if chase_pct > config.max_chase_pct:
                        continue  # já correu demasiado — não entrar
                signal.entry_price = next_open
                signal.signal_date = df.index[i+1].to_pydatetime()

            else:
                # next_day_open — comportamento original
                if i + 1 < len(df):
                    signal.entry_price = float(df.iloc[i+1]["open"])
                    signal.signal_date = df.index[i+1].to_pydatetime()
                else:
                    signal.signal_date = date.to_pydatetime()

            position = signal

        # Fechar posição aberta no fim do período
        if position is not None:
            lp  = float(df.iloc[-1]["close"])
            pnl = (lp - position.entry_price) / position.entry_price * 100
            meta = position.metadata if hasattr(position, "metadata") else {}
            trades.append(EnrichedBacktestResult(
                ticker=ticker,
                strategy_name=self.strategy.name,
                entry_date=position.signal_date,
                entry_price=position.entry_price,
                exit_date=df.index[-1].to_pydatetime(),
                exit_price=lp,
                exit_reason="end_of_period",
                pnl_pct=pnl,
                days_held=(df.index[-1] - pd.Timestamp(position.signal_date)).days,
                vol_ratio=meta.get("vol_ratio", 0),
                neglect_score=meta.get("neglect_score", 0),
                gap_pct=meta.get("gap_pct", 0),
                entry_window="UNKNOWN",
                candle_strength=0.5,
                entry_mode=config.entry_mode,
            ))

        return trades

    def _classify_window(self, days: int) -> str:
        if days <= 1:   return "PRIME"
        elif days <= 5: return "OPEN"
        else:           return "LATE"
