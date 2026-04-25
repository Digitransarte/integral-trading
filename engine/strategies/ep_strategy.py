"""Integral Trading — Episodic Pivot Strategy v2.0
Critérios baseados no knowledge JSON (knowledge/ep_strategy.json).
Filtros de Neglect, catalisador Tier 1/2/3, e scoring melhorado.
"""
import json
import os
from datetime import datetime
from typing import Optional
import pandas as pd

from engine.strategies.base import BaseStrategy, Signal


def _load_ep_knowledge() -> dict:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "knowledge", "ep_strategy.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class EpisodicPivotStrategy(BaseStrategy):
    name        = "Episodic Pivot"
    description = "Gap + volume explosivo num catalisador transformador (Pradeep Bonde)"
    version     = "2.1"

    # Critérios mínimos (alinhados com Pradeep)
    MIN_GAP_PCT      = 8.0    # Pradeep usa 8% — subimos de 5%
    MIN_VOLUME_RATIO = 3.0    # Pradeep usa 3x média 100 dias — subimos de 2.5x
    MAX_VOLUME_RATIO = 15.0   # Cap — acima de 15x tende a reverter (validado em backtest)
    MIN_PRICE        = 1.0    # Pradeep usa $1 — baixamos de $5
    MIN_VOLUME_ABS   = 300000 # Volume absoluto mínimo (Pradeep)

    default_stop_loss_pct = 0.08
    default_hold_days     = 20
    min_score             = 60.0

    def __init__(self):
        self._knowledge = _load_ep_knowledge()

    def scan(self, ticker: str, df: pd.DataFrame) -> bool:
        if len(df) < 22:
            return False

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Preço mínimo
        if float(last["close"]) < self.MIN_PRICE:
            return False

        # Gap mínimo (Pradeep: >= 8%)
        gap_pct  = (float(last["open"]) - float(prev["close"])) / float(prev["close"]) * 100
        day_move = (float(last["close"]) - float(prev["close"])) / float(prev["close"]) * 100
        if gap_pct < self.MIN_GAP_PCT and day_move < self.MIN_GAP_PCT:
            return False

        # Volume ratio vs média 100 dias (Pradeep usa 100 dias, não 20)
        lookback = min(100, len(df) - 2)
        avg_vol  = float(df["volume"].iloc[-(lookback + 1):-1].mean())
        vol_day  = float(last["volume"])
        if avg_vol > 0 and vol_day / avg_vol < self.MIN_VOLUME_RATIO:
            return False

        # Volume absoluto mínimo
        if vol_day < self.MIN_VOLUME_ABS:
            return False

        # Cap de volume ratio — acima de 15x tende a reverter (validado em backtest)
        if avg_vol > 0 and vol_day / avg_vol > self.MAX_VOLUME_RATIO:
            return False

        return True

    def generate_signal(self, ticker: str, df: pd.DataFrame) -> Optional[Signal]:
        if not self.scan(ticker, df):
            return None

        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        price = float(last["close"])

        gap_pct   = (float(last["open"]) - float(prev["close"])) / float(prev["close"]) * 100
        lookback  = min(100, len(df) - 2)
        avg_vol   = float(df["volume"].iloc[-(lookback + 1):-1].mean())
        vol_ratio = float(last["volume"]) / avg_vol if avg_vol > 0 else 0

        # Neglect check
        neglect_score = self._check_neglect(df)

        score = self._calculate_score(df, gap_pct, vol_ratio, neglect_score)
        if score < self.min_score:
            return None

        # Stop: mínima dos 2 dias anteriores (Pradeep) ou 8% — o maior dos dois
        two_day_low   = min(float(prev["low"]), float(df.iloc[-3]["low"]) if len(df) >= 3 else float(prev["low"]))
        stop_pradeep  = two_day_low
        stop_pct      = price * (1 - self.default_stop_loss_pct)
        stop          = max(stop_pradeep, stop_pct)  # o mais conservador

        neglect_label = "Neglect ✓" if neglect_score >= 20 else "Sem neglect"

        return Signal(
            ticker=ticker,
            strategy_name=self.name,
            signal_date=datetime.utcnow(),
            entry_price=price,
            stop_loss=stop,
            target_1=price * 1.15,
            target_2=price * 1.30,
            score=score,
            catalyst="Gap + Volume",
            notes=(
                "Gap: " + str(round(gap_pct, 1)) + "% | "
                "Vol: " + str(round(vol_ratio, 1)) + "x | "
                + neglect_label
            ),
            metadata={
                "gap_pct":      gap_pct,
                "vol_ratio":    vol_ratio,
                "neglect_score": neglect_score,
            },
        )

    def _check_neglect(self, df: pd.DataFrame) -> float:
        """
        Verifica sinais de Neglect baseados nos critérios do Pradeep.
        Retorna score de 0 a 40 pontos.
        """
        score = 0.0

        if len(df) < 65:
            return score

        # 1. Sem rally mas também sem colapso nos últimos 65 dias
        lookback_prices = df["close"].iloc[-66:-1]
        first_price = float(lookback_prices.iloc[0])
        max_price   = float(lookback_prices.max())
        min_price   = float(lookback_prices.min())

        if first_price > 0:
            max_gain = (max_price - first_price) / first_price * 100
            max_loss = (min_price - first_price) / first_price * 100

            if -10 <= max_gain <= 10:
                score += 15   # flat — neglect genuíno
            elif 10 < max_gain <= 20:
                score += 8    # subiu um pouco — aceitável
            elif max_loss < -30:
                score -= 10   # colapso estrutural — penalizar

        # 2. Volume baixo nos últimos 20 dias (antes do EP)
        avg_vol_recent = float(df["volume"].iloc[-21:-1].mean())
        avg_vol_100d   = float(df["volume"].iloc[-101:-1].mean()) if len(df) >= 102 else avg_vol_recent
        if avg_vol_100d > 0:
            vol_decay = avg_vol_recent / avg_vol_100d
            if vol_decay < 0.7:
                score += 15  # volume estava a cair — acção negligenciada
            elif vol_decay < 0.9:
                score += 8

        # 3. Movimento lateral — range estreito nos últimos 20 dias
        if len(df) >= 22:
            high_20 = float(df["high"].iloc[-21:-1].max())
            low_20  = float(df["low"].iloc[-21:-1].min())
            if low_20 > 0:
                range_pct = (high_20 - low_20) / low_20 * 100
                if range_pct < 15:
                    score += 10  # range muito estreito = consolidação / negligência

        return min(score, 40.0)

    def _calculate_score(self, df: pd.DataFrame, gap_pct: float,
                         vol_ratio: float, neglect_score: float = 0) -> float:
        score = 0.0

        # Gap (0-25 pontos) — sweet spot 10-15% (validado em backtest)
        if 10 <= gap_pct < 15:   score += 25   # sweet spot
        elif gap_pct >= 15:       score += 15   # grande mas menos fiável
        elif gap_pct >= 8:        score += 10   # mínimo aceitável

        # Volume (0-25 pontos) — escala Pradeep (10x = explosivo)
        if vol_ratio >= 10:  score += 25
        elif vol_ratio >= 5: score += 20
        elif vol_ratio >= 4: score += 15
        elif vol_ratio >= 3: score += 10

        # Neglect (0-40 pontos) — critério central Pradeep
        score += neglect_score

        # Força do candle (0-10 pontos) — fecha perto do high?
        last = df.iloc[-1]
        rng  = float(last["high"]) - float(last["low"])
        if rng > 0:
            cp = (float(last["close"]) - float(last["low"])) / rng
            if cp >= 0.8:   score += 10
            elif cp >= 0.6: score += 5

        return min(score, 100.0)
