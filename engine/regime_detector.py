"""
Integral Trading — Regime Detector (Camada 01)
===============================================
Determina o modo de mercado antes de qualquer scanner correr.

Modos:
  OFFENSIVE  — mercado em uptrend, sistema activo
  DEFENSIVE  — mercado fraco, reduzir exposição
  CASH       — mercado em colapso, zero novas posições

Lógica baseada em:
  1. SPY/QQQ vs SMA 200 (tendência macro)
  2. % stocks acima da SMA 50 (breadth)
  3. VIX threshold (volatilidade/medo)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Thresholds configuráveis
SPY_SMA_DAYS       = 200   # SMA 200 para tendência macro
QQQ_SMA_DAYS       = 200
BREADTH_SMA_DAYS   = 50    # SMA 50 para breadth
VIX_CASH_THRESHOLD = 35    # VIX acima disto → CASH
VIX_DEFENSIVE_THR  = 25    # VIX acima disto → pesar DEFENSIVE
BREADTH_OFFENSIVE  = 0.60  # >60% stocks acima SMA50 → sinal positivo
BREADTH_DEFENSIVE  = 0.40  # <40% stocks acima SMA50 → sinal negativo

# Proxy de breadth — usamos estes ETFs de sector como proxy
# (em vez de calcular % de cada stock individualmente)
BREADTH_PROXIES = [
    "XLK",  # Tech
    "XLV",  # Healthcare
    "XLF",  # Financials
    "XLI",  # Industrials
    "XLE",  # Energy
    "XLY",  # Consumer Discretionary
    "XLP",  # Consumer Staples
    "XLB",  # Materials
]


@dataclass
class RegimeSignal:
    """Sinal de regime de mercado."""
    mode: str                    # OFFENSIVE / DEFENSIVE / CASH
    score: int                   # 0-100 (100 = totalmente ofensivo)
    date: datetime               = field(default_factory=datetime.utcnow)

    # Componentes individuais
    spy_above_sma200: bool       = False
    qqq_above_sma200: bool       = False
    vix_level: float             = 0.0
    breadth_pct: float           = 0.0  # % de proxies em uptrend

    # Detalhes
    spy_price: float             = 0.0
    spy_sma200: float            = 0.0
    qqq_price: float             = 0.0
    qqq_sma200: float            = 0.0
    signals: list                = field(default_factory=list)
    warnings: list               = field(default_factory=list)

    @property
    def is_offensive(self) -> bool:
        return self.mode == "OFFENSIVE"

    @property
    def is_defensive(self) -> bool:
        return self.mode == "DEFENSIVE"

    @property
    def is_cash(self) -> bool:
        return self.mode == "CASH"

    @property
    def scanner_active(self) -> bool:
        """O scanner deve correr?"""
        return self.mode == "OFFENSIVE"

    def to_dict(self) -> dict:
        return {
            "mode":             self.mode,
            "score":            self.score,
            "date":             self.date.strftime("%Y-%m-%d %H:%M"),
            "spy_above_sma200": self.spy_above_sma200,
            "qqq_above_sma200": self.qqq_above_sma200,
            "vix_level":        round(self.vix_level, 2),
            "breadth_pct":      round(self.breadth_pct * 100, 1),
            "spy_price":        round(self.spy_price, 2),
            "spy_sma200":       round(self.spy_sma200, 2),
            "qqq_price":        round(self.qqq_price, 2),
            "qqq_sma200":       round(self.qqq_sma200, 2),
            "signals":          self.signals,
            "warnings":         self.warnings,
            "scanner_active":   self.scanner_active,
        }


class RegimeDetector:
    """
    Determina o regime de mercado actual.
    Camada 01 do sistema de 5 camadas.
    """

    def __init__(self, feed):
        self.feed = feed

    def detect(self) -> RegimeSignal:
        """
        Analisa o mercado e devolve o regime actual.
        Chamado uma vez por dia antes do scanner.
        """
        signals  = []
        warnings = []
        points   = 0  # score acumulado (max 100)

        # ── 1. SPY vs SMA 200 ────────────────────────────────────────────────
        spy_price, spy_sma200, spy_above = self._check_index_vs_sma("SPY", SPY_SMA_DAYS)

        if spy_above:
            points += 35
            signals.append("SPY acima da SMA200 ✓")
        else:
            warnings.append(f"SPY abaixo da SMA200 — ${spy_price:.2f} vs ${spy_sma200:.2f}")

        # ── 2. QQQ vs SMA 200 ────────────────────────────────────────────────
        qqq_price, qqq_sma200, qqq_above = self._check_index_vs_sma("QQQ", QQQ_SMA_DAYS)

        if qqq_above:
            points += 25
            signals.append("QQQ acima da SMA200 ✓")
        else:
            warnings.append(f"QQQ abaixo da SMA200 — ${qqq_price:.2f} vs ${qqq_sma200:.2f}")

        # ── 3. VIX ───────────────────────────────────────────────────────────
        vix_level = self._get_vix()

        if vix_level > 0:
            if vix_level >= VIX_CASH_THRESHOLD:
                warnings.append(f"VIX extremo: {vix_level:.1f} (≥{VIX_CASH_THRESHOLD}) — modo CASH")
            elif vix_level >= VIX_DEFENSIVE_THR:
                points -= 15
                warnings.append(f"VIX elevado: {vix_level:.1f} (≥{VIX_DEFENSIVE_THR})")
            else:
                points += 20
                signals.append(f"VIX controlado: {vix_level:.1f} ✓")

        # ── 4. Breadth (proxy via sector ETFs) ───────────────────────────────
        breadth_pct = self._calc_breadth()

        if breadth_pct >= BREADTH_OFFENSIVE:
            points += 20
            signals.append(f"Breadth forte: {breadth_pct*100:.0f}% sectores em uptrend ✓")
        elif breadth_pct <= BREADTH_DEFENSIVE:
            points -= 10
            warnings.append(f"Breadth fraca: {breadth_pct*100:.0f}% sectores em uptrend")
        else:
            points += 10
            signals.append(f"Breadth neutra: {breadth_pct*100:.0f}% sectores em uptrend")

        # ── Determinar modo ──────────────────────────────────────────────────
        score = max(0, min(100, points))

        if vix_level >= VIX_CASH_THRESHOLD:
            mode = "CASH"
        elif not spy_above and not qqq_above:
            mode = "CASH"
        elif score >= 60:
            mode = "OFFENSIVE"
        elif score >= 35:
            mode = "DEFENSIVE"
        else:
            mode = "CASH"

        return RegimeSignal(
            mode             = mode,
            score            = score,
            spy_above_sma200 = spy_above,
            qqq_above_sma200 = qqq_above,
            vix_level        = vix_level,
            breadth_pct      = breadth_pct,
            spy_price        = spy_price,
            spy_sma200       = spy_sma200,
            qqq_price        = qqq_price,
            qqq_sma200       = qqq_sma200,
            signals          = signals,
            warnings         = warnings,
        )

    def _check_index_vs_sma(self, ticker: str, sma_days: int):
        """Verifica se um índice está acima da sua SMA."""
        try:
            df = self.feed.get_bars(ticker, days=sma_days + 10)
            if df.empty or len(df) < sma_days:
                return 0.0, 0.0, False

            price = float(df["close"].iloc[-1])
            sma   = float(df["close"].tail(sma_days).mean())
            above = price > sma
            return price, sma, above
        except Exception as e:
            logger.error(f"Erro _check_index_vs_sma {ticker}: {e}")
            return 0.0, 0.0, False

    def _get_vix(self) -> float:
        """Obtém o nível actual do VIX."""
        try:
            df = self.feed.get_bars("^VIX", days=5)
            if df.empty:
                return 0.0
            return float(df["close"].iloc[-1])
        except Exception as e:
            logger.error(f"Erro _get_vix: {e}")
            return 0.0

    def _calc_breadth(self) -> float:
        """
        Calcula breadth usando sector ETFs como proxy.
        Retorna % de ETFs acima da sua SMA 50.
        """
        try:
            above_count = 0
            total       = 0

            for etf in BREADTH_PROXIES:
                df = self.feed.get_bars(etf, days=60)
                if df.empty or len(df) < BREADTH_SMA_DAYS:
                    continue

                price = float(df["close"].iloc[-1])
                sma50 = float(df["close"].tail(BREADTH_SMA_DAYS).mean())
                total += 1
                if price > sma50:
                    above_count += 1

            return above_count / total if total > 0 else 0.5

        except Exception as e:
            logger.error(f"Erro _calc_breadth: {e}")
            return 0.5
