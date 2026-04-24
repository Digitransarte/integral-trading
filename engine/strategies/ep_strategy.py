"""Integral Trading — Episodic Pivot Strategy"""
from datetime import datetime
from typing import Optional
import pandas as pd
from engine.strategies.base import BaseStrategy, Signal


class EpisodicPivotStrategy(BaseStrategy):
    name = "Episodic Pivot"
    description = "Gap + volume explosivo num catalisador transformador"
    version = "1.1"

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
            notes="Gap: " + str(round(gap_pct, 1)) + "% | Vol: " + str(round(vol_ratio, 1)) + "x",
            metadata={"gap_pct": gap_pct, "vol_ratio": vol_ratio},
        )

    def _calculate_score(self, df, gap_pct, vol_ratio) -> float:
        score = 0.0

        # Gap (0-30 pontos) — escala mais granular
        if gap_pct >= 20:    score += 30
        elif gap_pct >= 15:  score += 25
        elif gap_pct >= 10:  score += 20
        elif gap_pct >= 7:   score += 15
        elif gap_pct >= 5:   score += 10

        # Volume (0-30 pontos) — escala mais granular
        if vol_ratio >= 5:   score += 30
        elif vol_ratio >= 4: score += 25
        elif vol_ratio >= 3: score += 20
        elif vol_ratio >= 2.5: score += 10

        # Tendência (0-20 pontos) — stock em uptrend antes do EP?
        ma20 = float(df["close"].iloc[-21:-1].mean())
        ma50 = float(df["close"].iloc[-51:-1].mean()) if len(df) >= 52 else ma20
        last_close = float(df.iloc[-1]["close"])
        if last_close > ma20 > ma50: score += 20
        elif last_close > ma20:      score += 10

        # Força do candle (0-20 pontos) — fecha próximo do high?
        last = df.iloc[-1]
        rng  = float(last["high"]) - float(last["low"])
        if rng > 0:
            cp = (float(last["close"]) - float(last["low"])) / rng
            if cp >= 0.8:   score += 20
            elif cp >= 0.6: score += 10

        return min(score, 100.0)
