"""
Integral Trading — NCI Backtester
====================================
Walk-forward backtesting da estratégia NCI.

Dois modos:
  DAILY  — histórico completo (2015+), só barras diárias para detecção
  MTF    — últimos 730 dias, usa Daily + H4 + H1 (mais preciso)

Pipeline:
  1. Fetch histórico completo upfront
  2. Walk forward bar a bar no Daily
  3. Em cada bar: simular o que o NCI veria com dados até esse momento
  4. Se setup activo → registar trade (entrada no close do bar seguinte)
  5. Simular saída: stop hit, target hit, ou timeout (max_bars)
  6. Calcular métricas e equity curve
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "knowledge" / "nci_strategy.json"


# ─────────────────────────────────────────────────────────────────────────────
# Estruturas de dados
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BacktestTrade:
    trade_id:      int
    ticker:        str
    direction:     str       # LONG / SHORT
    entry_date:    datetime
    entry_price:   float
    stop_loss:     float
    target_1:      float
    exit_date:     datetime
    exit_price:    float
    exit_reason:   str       # "TARGET" / "STOP" / "TIMEOUT"
    pnl_pct:       float
    pnl_r:         float     # múltiplo de R
    bars_held:     int
    setup_score:   int
    setup_quality: str
    daily_trend:   str
    bos_confirmed: bool
    manipulation:  bool

    @property
    def is_win(self) -> bool:
        return self.pnl_pct > 0


@dataclass
class BacktestResult:
    ticker:        str
    mode:          str       # "daily" / "mtf"
    start_date:    datetime
    end_date:      datetime
    trades:        list      # list[BacktestTrade]
    params:        dict

    # Métricas calculadas no __post_init__
    total_trades:  int = 0
    wins:          int = 0
    losses:        int = 0
    win_rate:      float = 0.0
    avg_win_pct:   float = 0.0
    avg_loss_pct:  float = 0.0
    profit_factor: float = 0.0
    expectancy_r:  float = 0.0
    total_return:  float = 0.0
    max_drawdown:  float = 0.0
    avg_bars_held: float = 0.0
    equity_curve:  list  = field(default_factory=list)

    def __post_init__(self):
        self._calculate()

    def _calculate(self):
        if not self.trades:
            return

        self.total_trades = len(self.trades)
        wins   = [t for t in self.trades if t.is_win]
        losses = [t for t in self.trades if not t.is_win]

        self.wins   = len(wins)
        self.losses = len(losses)
        self.win_rate = round(self.wins / self.total_trades * 100, 1)

        self.avg_win_pct  = round(float(np.mean([t.pnl_pct for t in wins])),   2) if wins   else 0.0
        self.avg_loss_pct = round(float(np.mean([t.pnl_pct for t in losses])), 2) if losses else 0.0

        gross_wins   = sum(t.pnl_pct for t in wins)
        gross_losses = abs(sum(t.pnl_pct for t in losses))
        self.profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else float("inf")

        self.expectancy_r = round(float(np.mean([t.pnl_r for t in self.trades])), 2)
        self.avg_bars_held = round(float(np.mean([t.bars_held for t in self.trades])), 1)

        # Equity curve (capital normalizado a 100)
        capital = 100.0
        curve   = [capital]
        peak    = capital
        dd_vals = []

        for trade in self.trades:
            capital *= (1 + trade.pnl_pct / 100)
            curve.append(round(capital, 2))
            peak = max(peak, capital)
            dd_vals.append((capital - peak) / peak * 100)

        self.total_return = round(capital - 100.0, 2)
        self.max_drawdown = round(min(dd_vals), 2) if dd_vals else 0.0
        self.equity_curve = curve

    def to_dict(self) -> dict:
        return {
            "ticker":        self.ticker,
            "mode":          self.mode,
            "start_date":    self.start_date.strftime("%Y-%m-%d"),
            "end_date":      self.end_date.strftime("%Y-%m-%d"),
            "total_trades":  self.total_trades,
            "wins":          self.wins,
            "losses":        self.losses,
            "win_rate":      self.win_rate,
            "avg_win_pct":   self.avg_win_pct,
            "avg_loss_pct":  self.avg_loss_pct,
            "profit_factor": self.profit_factor,
            "expectancy_r":  self.expectancy_r,
            "total_return":  self.total_return,
            "max_drawdown":  self.max_drawdown,
            "avg_bars_held": self.avg_bars_held,
            "params":        self.params,
        }

    def trades_to_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        rows = []
        for t in self.trades:
            rows.append({
                "ID":         t.trade_id,
                "Data":       t.entry_date.strftime("%Y-%m-%d"),
                "Dir":        t.direction,
                "Entry":      round(t.entry_price, 2),
                "Stop":       round(t.stop_loss, 2),
                "Target":     round(t.target_1, 2),
                "Exit":       round(t.exit_price, 2),
                "Saída":      t.exit_reason,
                "PnL%":       round(t.pnl_pct, 2),
                "R":          round(t.pnl_r, 2),
                "Bars":       t.bars_held,
                "Score":      t.setup_score,
                "Q":          t.setup_quality,
                "BOS":        "✅" if t.bos_confirmed else "—",
                "Manip":      "✅" if t.manipulation else "—",
            })
        return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Backtester
# ─────────────────────────────────────────────────────────────────────────────

class NCIBacktester:
    """
    Walk-forward backtester para a estratégia NCI.
    Usa os métodos internos do NCIAnalyzer para evitar lookahead.
    """

    MIN_BARS_WARMUP   = 60   # barras mínimas para warmup (SMA50 + margem)

    def __init__(self, feed, config_path: Path = _CONFIG_PATH):
        self.feed = feed
        from engine.nci_analyzer import NCIAnalyzer
        self.analyzer = NCIAnalyzer(feed, config_path)
        # Ler max_bars_timeout do JSON (default 20)
        bt_cfg = self.analyzer.cfg.get("backtesting", {})
        self.MAX_BARS_IN_TRADE = bt_cfg.get("max_bars_timeout", 20)
        self.TRAILING_STOP_PCT  = bt_cfg.get("trailing_stop_pct", 0.0)
        self.DIRECTION_FILTER   = bt_cfg.get("direction_filter", "ALL")  # ALL / LONG / SHORT
        logger.info("MAX_BARS: " + str(self.MAX_BARS_IN_TRADE) +
                    " | TRAILING: " + str(self.TRAILING_STOP_PCT) +
                    " | DIR: " + str(self.DIRECTION_FILTER))

    def run(self, ticker: str, mode: str = "mtf",
            years: int = 2, min_score: int = 60) -> BacktestResult:
        """
        Corre o backtest para um ticker.

        Args:
            ticker:    ticker yfinance (ex: "GC=F" para ouro)
            mode:      "daily" ou "mtf"
            years:     anos de histórico a usar (modo daily: até 10)
            min_score: score mínimo para abrir trade (default: 60)
        """
        logger.info("NCI Backtest: " + ticker + " | modo=" + mode +
                    " | " + str(years) + " anos | min_score=" + str(min_score))

        # ── Fetch de dados ────────────────────────────────────────────────────

        days_daily = min(years * 365, 3650)  # máx 10 anos
        df_daily   = self.feed.get_bars(ticker, days=days_daily)

        if df_daily is None or df_daily.empty or len(df_daily) < self.MIN_BARS_WARMUP + 10:
            logger.error("Dados diários insuficientes para " + ticker)
            return self._empty_result(ticker, mode)

        df_h4, df_h1 = None, None

        if mode == "mtf":
            # yfinance limita H1 a 730 dias — limitar histórico MTF a 2 anos
            if days_daily > 730:
                logger.info("MTF: histórico limitado a 730 dias (limite yfinance H1)")
                days_daily = 730
                df_daily = self.feed.get_bars(ticker, days=730)

            df_h4 = self.feed.get_bars_intraday(ticker, interval="4h", days=730)
            df_h1 = self.feed.get_bars_intraday(ticker, interval="1h", days=730)
            if df_h4 is None or df_h1 is None:
                logger.warning("Dados intraday indisponíveis — a usar modo daily")
                mode = "daily"

        # ── Walk-forward ──────────────────────────────────────────────────────

        params = {
            "mode":       mode,
            "min_score":  min_score,
            "years":      years,
            "pivot_str":  self.analyzer.pivot_strength,
            "pullback%":  self.analyzer.pullback_zone_pct,
            "min_rr":     self.analyzer.min_rr,
            "bos_req":    self.analyzer.bos_required,
        }

        trades = self._walk_forward(ticker, df_daily, df_h4, df_h1, min_score)

        start_dt = df_daily.index[self.MIN_BARS_WARMUP].to_pydatetime()
        end_dt   = df_daily.index[-1].to_pydatetime()

        diag = getattr(self, "_diag", {})
        params["_diag"] = diag
        logger.info("Diagnóstico: " + str(diag))

        return BacktestResult(
            ticker=ticker,
            mode=mode,
            start_date=start_dt,
            end_date=end_dt,
            trades=trades,
            params=params,
        )

    # ── Walk-forward ──────────────────────────────────────────────────────────

    def _walk_forward(self, ticker: str, df_daily: pd.DataFrame,
                       df_h4: Optional[pd.DataFrame],
                       df_h1: Optional[pd.DataFrame],
                       min_score: int) -> list:
        trades    = []
        trade_id  = 1
        in_trade  = False
        trade_end = None

        # Contadores de diagnóstico
        self._diag = {
            "bars_total":   0,
            "in_trade":     0,
            "signal_none":  0,
            "score_low":    0,
            "stop_zero":    0,
            "entered":      0,
        }

        n = len(df_daily)

        for i in range(self.MIN_BARS_WARMUP, n - 1):

            self._diag["bars_total"] += 1

            # Ignorar barras dentro de um trade activo
            if in_trade and df_daily.index[i] <= trade_end:
                self._diag["in_trade"] += 1
                continue

            in_trade = False
            bar_date = df_daily.index[i]

            daily_slice = df_daily.iloc[:i + 1]
            h4_slice = self._slice_intraday(df_h4, bar_date) if df_h4 is not None else None
            h1_slice = self._slice_intraday(df_h1, bar_date) if df_h1 is not None else None

            signal = self._analyze_at_bar(ticker, daily_slice, h4_slice, h1_slice)

            if signal is None:
                self._diag["signal_none"] += 1
                continue
            if signal["score"] < min_score:
                self._diag["score_low"] += 1
                continue
            if signal["stop"] <= 0 or signal["target"] <= 0:
                self._diag["stop_zero"] += 1
                continue
            if self.DIRECTION_FILTER != "ALL" and signal["direction"] != self.DIRECTION_FILTER:
                self._diag["direction_filtered"] = self._diag.get("direction_filtered", 0) + 1
                continue

            self._diag["entered"] += 1

            # Setup detectado — entrada no close do bar seguinte
            if i + 1 >= n:
                break

            entry_date  = df_daily.index[i + 1].to_pydatetime()
            entry_price = float(df_daily["close"].iloc[i + 1])
            stop        = signal["stop"]
            target      = signal["target"]
            direction   = signal["direction"]

            # Simular trade nos bars seguintes
            trade = self._simulate_trade(
                trade_id   = trade_id,
                ticker     = ticker,
                direction  = direction,
                entry_date = entry_date,
                entry_price = entry_price,
                stop_loss  = stop,
                target_1   = target,
                df_future  = df_daily.iloc[i + 2:i + 2 + self.MAX_BARS_IN_TRADE],
                setup_score  = signal["score"],
                setup_quality = signal["quality"],
                daily_trend   = signal["daily_trend"],
                bos_confirmed = signal["bos"],
                manipulation  = signal["manipulation"],
            )

            if trade:
                trades.append(trade)
                trade_id += 1
                in_trade  = True
                trade_end = trade.exit_date

        return trades

    def _analyze_at_bar(self, ticker: str,
                         daily: pd.DataFrame,
                         h4: Optional[pd.DataFrame],
                         h1: Optional[pd.DataFrame]) -> Optional[dict]:
        """
        Corre análise NCI num ponto histórico específico.
        Usa os métodos internos do analyzer — sem lookahead.
        """
        try:
            az = self.analyzer

            daily_view = az._analyze_timeframe(daily, "daily", ticker)
            if daily_view is None or daily_view.trend == "RANGING":
                return None

            h4_view = az._analyze_timeframe(
                h4, "h4", ticker,
                reference_key_level=daily_view.key_level if daily_view else None
            ) if h4 is not None and len(h4) >= az.sma_slow else None

            h1_view = az._analyze_timeframe(
                h1, "h1", ticker,
                reference_key_level=h4_view.key_level if h4_view else None
            ) if h1 is not None and len(h1) >= az.sma_slow else None

            sig = az._build_signal(ticker, daily_view, h4_view, h1_view)

            # No backtesting filtramos só por score — setup_active é demasiado restritivo
            # O breakdown BOS vs não-BOS é precisamente o que queremos medir
            if sig.direction == "NONE":
                return None
            if sig.stop_loss <= 0 or sig.target_1 <= 0:
                return None

            return {
                "direction":    sig.direction,
                "score":        sig.confluence_score,
                "quality":      sig.setup_quality,
                "stop":         sig.stop_loss,
                "target":       sig.target_1,
                "rr":           sig.risk_reward,
                "daily_trend":  daily_view.trend,
                "bos":          (h1_view.bos_confirmed if h1_view else False) or
                                (h4_view.bos_confirmed if h4_view else False),
                "manipulation": (h4_view.manipulation_detected if h4_view else False) or
                                (h1_view.manipulation_detected if h1_view else False),
                "setup_active": sig.setup_active,
            }

        except Exception as e:
            logger.debug("Erro _analyze_at_bar: " + str(e))
            return None

    def _simulate_trade(self, trade_id, ticker, direction, entry_date,
                         entry_price, stop_loss, target_1, df_future,
                         setup_score, setup_quality, daily_trend,
                         bos_confirmed, manipulation) -> Optional[BacktestTrade]:
        """
        Simula um trade nos bars futuros.
        Verifica bar a bar se stop ou target foram atingidos.
        """
        if df_future is None or df_future.empty:
            return None

        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            return None

        best_price = entry_price

        for bars_held, (bar_date, bar) in enumerate(df_future.iterrows(), 1):
            high  = float(bar["high"])
            low   = float(bar["low"])
            close = float(bar["close"])

            # Actualizar máximo/mínimo favorável
            if direction == "LONG":
                best_price = max(best_price, high)
            else:
                best_price = min(best_price, low)

            # Trailing stop dinâmico
            trailing_exit = None
            if self.TRAILING_STOP_PCT > 0:
                if direction == "LONG" and best_price > entry_price:
                    trailing_exit = best_price * (1 - self.TRAILING_STOP_PCT / 100)
                elif direction == "SHORT" and best_price < entry_price:
                    trailing_exit = best_price * (1 + self.TRAILING_STOP_PCT / 100)

            if direction == "LONG":
                if low <= stop_loss:
                    exit_price, exit_reason = stop_loss, "STOP"
                    pnl_pct = (stop_loss - entry_price) / entry_price * 100
                    pnl_r   = -1.0
                elif high >= target_1:
                    exit_price, exit_reason = target_1, "TARGET"
                    pnl_pct = (target_1 - entry_price) / entry_price * 100
                    pnl_r   = pnl_pct / (risk / entry_price * 100)
                elif trailing_exit and low <= trailing_exit:
                    exit_price, exit_reason = trailing_exit, "TRAILING"
                    pnl_pct = (trailing_exit - entry_price) / entry_price * 100
                    pnl_r   = pnl_pct / (risk / entry_price * 100)
                else:
                    continue
            else:  # SHORT
                if high >= stop_loss:
                    exit_price, exit_reason = stop_loss, "STOP"
                    pnl_pct = (entry_price - stop_loss) / entry_price * 100
                    pnl_r   = -1.0
                elif low <= target_1:
                    exit_price, exit_reason = target_1, "TARGET"
                    pnl_pct = (entry_price - target_1) / entry_price * 100
                    pnl_r   = pnl_pct / (risk / entry_price * 100)
                elif trailing_exit and high >= trailing_exit:
                    exit_price, exit_reason = trailing_exit, "TRAILING"
                    pnl_pct = (entry_price - trailing_exit) / entry_price * 100
                    pnl_r   = pnl_pct / (risk / entry_price * 100)
                else:
                    continue

            return BacktestTrade(
                trade_id=trade_id, ticker=ticker,
                direction=direction,
                entry_date=entry_date, entry_price=entry_price,
                stop_loss=stop_loss, target_1=target_1,
                exit_date=bar_date.to_pydatetime(),
                exit_price=exit_price, exit_reason=exit_reason,
                pnl_pct=round(pnl_pct, 3), pnl_r=round(pnl_r, 2),
                bars_held=bars_held,
                setup_score=setup_score, setup_quality=setup_quality,
                daily_trend=daily_trend, bos_confirmed=bos_confirmed,
                manipulation=manipulation,
            )

        # Timeout — sair ao close do último bar
        last_bar   = df_future.iloc[-1]
        exit_price = float(last_bar["close"])
        bars_held  = len(df_future)

        if direction == "LONG":
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100

        pnl_r = pnl_pct / (risk / entry_price * 100)

        return BacktestTrade(
            trade_id=trade_id, ticker=ticker,
            direction=direction,
            entry_date=entry_date, entry_price=entry_price,
            stop_loss=stop_loss, target_1=target_1,
            exit_date=df_future.index[-1].to_pydatetime(),
            exit_price=exit_price, exit_reason="TIMEOUT",
            pnl_pct=round(pnl_pct, 3), pnl_r=round(pnl_r, 2),
            bars_held=bars_held,
            setup_score=setup_score, setup_quality=setup_quality,
            daily_trend=daily_trend, bos_confirmed=bos_confirmed,
            manipulation=manipulation,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _slice_intraday(self, df: pd.DataFrame, until: pd.Timestamp) -> Optional[pd.DataFrame]:
        """Corta DataFrame intraday até uma data inclusiva."""
        if df is None or df.empty:
            return None
        mask = df.index <= until
        sliced = df[mask]
        return sliced if len(sliced) >= self.analyzer.sma_slow else None

    def _empty_result(self, ticker: str, mode: str) -> BacktestResult:
        return BacktestResult(
            ticker=ticker, mode=mode,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow(),
            trades=[], params={},
        )
