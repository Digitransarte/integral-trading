"""
Integral Trading — Scanner em Tempo Real
==========================================
Detecta sinais EP nos últimos N dias (janela de entrada).
Não só o dia de hoje — procura EPs recentes ainda em janela PRIME/OPEN.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import logging

from engine.data_feed import DataFeed
from engine.strategies.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    ticker: str
    strategy_name: str
    scan_date: datetime
    signal: Signal
    current_price: float
    gap_price: float        # preco no dia do gap
    prev_close: float
    gap_pct: float
    vol_ratio: float
    avg_volume: float
    gap_date: datetime
    days_since_gap: int
    entry_window: str = "UNKNOWN"

    @property
    def score(self) -> float:
        return self.signal.score

    @property
    def stop_loss(self) -> float:
        return self.signal.stop_loss

    @property
    def target_1(self) -> float:
        return self.signal.target_1

    @property
    def target_2(self) -> float:
        return self.signal.target_2

    @property
    def risk_pct(self) -> float:
        return abs(self.current_price - self.stop_loss) / self.current_price * 100

    @property
    def reward_pct(self) -> float:
        return abs(self.target_1 - self.current_price) / self.current_price * 100

    @property
    def move_since_gap(self) -> float:
        """Movimento desde o dia do gap até hoje."""
        if self.gap_price <= 0:
            return 0.0
        return (self.current_price - self.gap_price) / self.gap_price * 100

    def to_dict(self) -> dict:
        return {
            "ticker":          self.ticker,
            "strategy":        self.strategy_name,
            "scan_date":       self.scan_date.strftime("%Y-%m-%d %H:%M"),
            "gap_date":        self.gap_date.strftime("%Y-%m-%d"),
            "days_since_gap":  self.days_since_gap,
            "entry_window":    self.entry_window,
            "current_price":   round(self.current_price, 2),
            "gap_price":       round(self.gap_price, 2),
            "gap_pct":         round(self.gap_pct, 2),
            "move_since_gap":  round(self.move_since_gap, 2),
            "vol_ratio":       round(self.vol_ratio, 1),
            "score":           round(self.score, 1),
            "stop_loss":       round(self.stop_loss, 2),
            "target_1":        round(self.target_1, 2),
            "target_2":        round(self.target_2, 2),
            "risk_pct":        round(self.risk_pct, 2),
            "reward_pct":      round(self.reward_pct, 2),
            "catalyst":        self.signal.catalyst,
            "notes":           self.signal.notes,
        }


@dataclass
class ScanResult:
    strategy_name: str
    scan_date: datetime
    tickers_scanned: int
    candidates: list
    errors: list = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def total_candidates(self) -> int:
        return len(self.candidates)

    def top(self, n: int = 10) -> list:
        return sorted(self.candidates, key=lambda x: x.score, reverse=True)[:n]


class Scanner:
    """
    Scanner em tempo real.

    Procura EPs nos últimos max_lookback_days dias —
    não só hoje, mas qualquer EP ainda dentro da janela de entrada.
    """

    # Janela máxima de entrada (dias desde o gap)
    MAX_ENTRY_DAYS = 10

    def __init__(self, feed: DataFeed, strategy: BaseStrategy):
        self.feed     = feed
        self.strategy = strategy

    def run(self, tickers: list, lookback_days: int = 60) -> ScanResult:
        start = datetime.utcnow()
        logger.info("Scanner a iniciar: " + str(len(tickers)) + " tickers")

        candidates, errors = [], []

        for ticker in tickers:
            try:
                candidate = self._scan_ticker(ticker, lookback_days)
                if candidate is not None:
                    candidates.append(candidate)
            except Exception as e:
                errors.append(ticker + ": " + str(e))
                logger.warning("Erro " + ticker + ": " + str(e))

        duration = (datetime.utcnow() - start).total_seconds()

        return ScanResult(
            strategy_name=self.strategy.name,
            scan_date=datetime.utcnow(),
            tickers_scanned=len(tickers),
            candidates=candidates,
            errors=errors,
            duration_seconds=duration,
        )

    def _scan_ticker(self, ticker: str, lookback_days: int) -> Optional[Candidate]:
        df = self.feed.get_bars(ticker, days=lookback_days)

        if df is None or df.empty or len(df) < 22:
            return None

        # Preço actual (último bar disponível)
        current_price = float(df.iloc[-1]["close"])

        # Procurar EP nos últimos MAX_ENTRY_DAYS bars
        # Começa pelo mais recente e vai para trás
        best_candidate = None

        for days_back in range(0, self.MAX_ENTRY_DAYS + 1):
            # Index do bar a verificar (0 = hoje, 1 = ontem, etc.)
            bar_idx = -(days_back + 1)
            prev_idx = -(days_back + 2)

            if abs(bar_idx) > len(df) or abs(prev_idx) > len(df):
                break

            bar  = df.iloc[bar_idx]
            prev = df.iloc[prev_idx]

            # Calcular gap e volume neste bar
            gap_pct = (float(bar["open"]) - float(prev["close"])) / float(prev["close"]) * 100
            avg_vol = float(df["volume"].iloc[prev_idx - 20 : prev_idx].mean()) if abs(prev_idx) + 20 <= len(df) else float(df["volume"].mean())
            vol_ratio = float(bar["volume"]) / avg_vol if avg_vol > 0 else 0

            # Verificar critérios EP neste bar
            if gap_pct < self.strategy.MIN_GAP_PCT:
                continue
            if vol_ratio < self.strategy.MIN_VOLUME_RATIO:
                continue
            if float(bar["close"]) < self.strategy.MIN_PRICE:
                continue

            # Gerar signal usando os dados até ao bar do EP
            df_at_event = df.iloc[:bar_idx] if bar_idx != -1 else df
            if len(df_at_event) < 22:
                continue

            score = self.strategy._calculate_score(df_at_event, gap_pct, vol_ratio)

            if score < self.strategy.min_score:
                continue

            # EP encontrado — calcular janela de entrada
            days_since = days_back
            entry_window = self._classify_window(days_since)

            # Stop e targets baseados no preço actual
            stop  = current_price * (1 - self.strategy.default_stop_loss_pct)
            t1    = current_price * 1.15
            t2    = current_price * 1.30

            from engine.strategies.base import Signal
            signal = Signal(
                ticker=ticker,
                strategy_name=self.strategy.name,
                signal_date=df.index[bar_idx].to_pydatetime(),
                entry_price=current_price,
                stop_loss=stop,
                target_1=t1,
                target_2=t2,
                score=score,
                catalyst="Gap + Volume",
                notes="Gap: " + str(round(gap_pct, 1)) + "% | Vol: " + str(round(vol_ratio, 1)) + "x",
                metadata={"gap_pct": gap_pct, "vol_ratio": vol_ratio},
            )

            candidate = Candidate(
                ticker=ticker,
                strategy_name=self.strategy.name,
                scan_date=datetime.utcnow(),
                signal=signal,
                current_price=current_price,
                gap_price=float(bar["close"]),
                prev_close=float(prev["close"]),
                gap_pct=gap_pct,
                vol_ratio=vol_ratio,
                avg_volume=avg_vol,
                gap_date=df.index[bar_idx].to_pydatetime(),
                days_since_gap=days_since,
                entry_window=entry_window,
            )

            # Guardar o mais recente com melhor score
            if best_candidate is None or score > best_candidate.score:
                best_candidate = candidate

        return best_candidate

    def _classify_window(self, days: int) -> str:
        if days <= 5:
            return "PRIME"
        elif days <= 10:
            return "OPEN"
        else:
            return "LATE"
