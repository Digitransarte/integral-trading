"""
Integral Trading — Imbalance Detector (Fair Value Gap)
========================================================
Detecta Imbalances (FVGs) em qualquer série de candles.

Definição (Pham Level 2/3):
  Bullish IMB: 3 candles consecutivas onde high[t-1] < low[t+1]
               (gap entre candle anterior e posterior à candle de impulso)
  Bearish IMB: 3 candles consecutivas onde low[t-1] > high[t+1]

O imbalance é o "footprint" do smart money — preço saltou tão depressa
que não houve trades naquele intervalo de preço.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List

import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Estrutura
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Imbalance:
    """Um Fair Value Gap (Imbalance) entre 3 candles consecutivas."""

    start_idx: int               # bar index da 1ª candle (t-1)
    middle_idx: int              # bar index da candle do meio (t)
    end_idx: int                 # bar index da 3ª candle (t+1)
    direction: str               # "BULLISH" ou "BEARISH"

    gap_high: float              # topo do gap
    gap_low: float               # fundo do gap
    gap_size_pct: float          # tamanho do gap em % do preço actual

    is_filled: bool = False      # preço posterior já fechou o gap
    fill_idx: int = 0            # bar index onde foi fechado (0 se não)

    middle_is_marubozu: bool = False   # candle do meio é marubozu (corpo > 70% range)
    strength: str = "WEAK"             # "WEAK" | "MEDIUM" | "STRONG"

    def __repr__(self):
        status = "FILLED" if self.is_filled else "OPEN"
        return ("Imbalance(" + self.direction +
                ", " + self.strength +
                ", " + str(self.start_idx) + "-" + str(self.end_idx) +
                ", gap=$" + str(round(self.gap_low, 4)) + "-$" +
                str(round(self.gap_high, 4)) +
                ", " + str(round(self.gap_size_pct, 2)) + "%, " + status + ")")


# ─────────────────────────────────────────────────────────────────────────────
# Detector
# ─────────────────────────────────────────────────────────────────────────────

def detect_imbalances(df: pd.DataFrame, min_gap_pct: float = 0.0) -> List[Imbalance]:
    """
    Detecta todos os imbalances numa série de candles.

    Args:
        df: DataFrame com colunas 'open', 'high', 'low', 'close'
        min_gap_pct: tamanho mínimo do gap em % do preço (filtro de ruído)

    Returns:
        Lista de Imbalance ordenada por start_idx (mais antigo primeiro)
    """
    if df is None or len(df) < 3:
        return []

    highs  = df["high"].values
    lows   = df["low"].values
    opens  = df["open"].values
    closes = df["close"].values

    imbalances = []

    # Iterar em janelas de 3 candles consecutivas
    # i é o índice da candle do meio (t)
    for i in range(1, len(df) - 1):
        h_prev   = highs[i - 1]
        l_prev   = lows[i - 1]
        h_next   = highs[i + 1]
        l_next   = lows[i + 1]
        h_middle = highs[i]
        l_middle = lows[i]
        o_middle = opens[i]
        c_middle = closes[i]

        # Bullish IMB: high[t-1] < low[t+1]  (gap para cima)
        if h_prev < l_next:
            gap_size = l_next - h_prev
            gap_pct  = gap_size / l_next * 100

            if gap_pct < min_gap_pct:
                continue

            # Marubozu check no candle do meio
            range_total = h_middle - l_middle
            body = abs(c_middle - o_middle)
            is_maru = range_total > 0 and (body / range_total) > 0.70

            imb = Imbalance(
                start_idx=i - 1,
                middle_idx=i,
                end_idx=i + 1,
                direction="BULLISH",
                gap_high=float(l_next),
                gap_low=float(h_prev),
                gap_size_pct=float(gap_pct),
                middle_is_marubozu=is_maru,
                strength=_classify_strength(float(gap_pct), is_maru),
            )
            # Verificar se foi preenchido
            _check_filled(imb, df)
            imbalances.append(imb)

        # Bearish IMB: low[t-1] > high[t+1]  (gap para baixo)
        elif l_prev > h_next:
            gap_size = l_prev - h_next
            gap_pct  = gap_size / l_prev * 100

            if gap_pct < min_gap_pct:
                continue

            range_total = h_middle - l_middle
            body = abs(c_middle - o_middle)
            is_maru = range_total > 0 and (body / range_total) > 0.70

            imb = Imbalance(
                start_idx=i - 1,
                middle_idx=i,
                end_idx=i + 1,
                direction="BEARISH",
                gap_high=float(l_prev),
                gap_low=float(h_next),
                gap_size_pct=float(gap_pct),
                middle_is_marubozu=is_maru,
                strength=_classify_strength(float(gap_pct), is_maru),
            )
            _check_filled(imb, df)
            imbalances.append(imb)

    return imbalances


def _check_filled(imb: Imbalance, df: pd.DataFrame) -> None:
    """Verifica se o gap foi preenchido por candles posteriores."""
    highs = df["high"].values
    lows  = df["low"].values

    # Procurar candles após end_idx que entrem no gap
    for j in range(imb.end_idx + 1, len(df)):
        if imb.direction == "BULLISH":
            # Bullish IMB é preenchido se preço descer abaixo de gap_high
            if lows[j] <= imb.gap_low:
                imb.is_filled = True
                imb.fill_idx = j
                return
        else:  # BEARISH
            # Bearish IMB é preenchido se preço subir acima de gap_low
            if highs[j] >= imb.gap_high:
                imb.is_filled = True
                imb.fill_idx = j
                return


def _classify_strength(gap_pct: float, is_marubozu: bool) -> str:
    """
    Classifica a força do imbalance.

    Critérios (Pham Level 2/3):
      STRONG: gap >= 0.5% E candle do meio é marubozu
      MEDIUM: gap >= 0.1% E candle do meio é marubozu
      WEAK:   tudo o resto (gap pequeno OU não-marubozu)

    O critério marubozu reflecte que IMBs de força operacional vêm
    sempre com candle de impulso forte. Um gap sem marubozu é mais
    provável ser ruído do que footprint de smart money.
    """
    if gap_pct >= 0.5 and is_marubozu:
        return "STRONG"
    if gap_pct >= 0.1 and is_marubozu:
        return "MEDIUM"
    return "WEAK"


def imbalances_by_strength(imbalances: List[Imbalance],
                             min_strength: str = "MEDIUM") -> List[Imbalance]:
    """
    Filtra imbalances pela força mínima.
    Ordem: WEAK < MEDIUM < STRONG
    """
    rank = {"WEAK": 0, "MEDIUM": 1, "STRONG": 2}
    threshold = rank.get(min_strength, 1)
    return [imb for imb in imbalances if rank.get(imb.strength, 0) >= threshold]


def imbalances_in_range(imbalances: List[Imbalance],
                         start_idx: int, end_idx: int) -> List[Imbalance]:
    """Filtra imbalances cujo middle_idx esteja em [start_idx, end_idx]."""
    return [
        imb for imb in imbalances
        if start_idx <= imb.middle_idx <= end_idx
    ]


def open_imbalances(imbalances: List[Imbalance]) -> List[Imbalance]:
    """Filtra apenas os imbalances ainda abertos (não preenchidos)."""
    return [imb for imb in imbalances if not imb.is_filled]


def imbalances_by_direction(imbalances: List[Imbalance],
                              direction: str) -> List[Imbalance]:
    """Filtra imbalances por direcção (BULLISH ou BEARISH)."""
    return [imb for imb in imbalances if imb.direction == direction]
