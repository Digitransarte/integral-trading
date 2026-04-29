"""
Integral Trading — Macro Analyzer (Commodities)
=================================================
Analisa o contexto macro para ouro e prata.
Baseado no knowledge SMC do Jayce Pham (NCI).

Fontes de dados (todos via yfinance):
  GLD  — ETF proxy do ouro (XAU/USD)
  SLV  — ETF proxy da prata (XAG/USD)
  UUP  — ETF proxy do DXY (dólar index)
  TLT  — ETF proxy do yield 20Y (inverso dos yields)
  ^VIX — Volatilidade / fear index
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Thresholds
SMA_SHORT     = 20   # SMA rápida
SMA_LONG      = 50   # SMA lenta
VIX_HIGH      = 25   # VIX acima = safe haven demand (favorável ao ouro)
VIX_EXTREME   = 35   # VIX extremo


@dataclass
class MacroComponent:
    name: str
    value: float
    sma_short: float
    sma_long: float
    trend: str        # BULLISH / BEARISH / NEUTRAL
    signal: str       # sinal para ouro
    detail: str


@dataclass
class MarketStructure:
    """Estrutura de mercado simplificada (Weinstein/Jayce)."""
    asset: str
    price: float
    sma20: float
    sma50: float
    trend: str          # UPTREND / DOWNTREND / RANGING
    key_level: float    # nível chave mais próximo
    recent_high: float
    recent_low: float
    distance_to_kl: float  # % de distância ao key level
    setup: str          # NEAR_KEY_LEVEL / EXTENDED / RANGING


@dataclass
class MacroSignal:
    """Sinal macro completo para ouro/prata."""
    date: datetime
    bias: str             # BULLISH / BEARISH / NEUTRAL
    score: int            # 0-100
    confidence: str       # HIGH / MEDIUM / LOW

    # Componentes
    dxy: MacroComponent   = None
    yields: MacroComponent = None
    vix_level: float      = 0.0
    vix_signal: str       = ""

    # Estrutura de mercado
    gold_structure: MarketStructure   = None
    silver_structure: MarketStructure = None

    # Resumo
    signals_bullish: list = field(default_factory=list)
    signals_bearish: list = field(default_factory=list)
    setup_alert: str      = ""    # alerta de setup activo

    def to_dict(self) -> dict:
        return {
            "date":       self.date.strftime("%Y-%m-%d %H:%M"),
            "bias":       self.bias,
            "score":      self.score,
            "confidence": self.confidence,
            "vix_level":  round(self.vix_level, 2),
            "vix_signal": self.vix_signal,
            "dxy": {
                "value":   round(self.dxy.value, 3) if self.dxy else 0,
                "trend":   self.dxy.trend if self.dxy else "",
                "signal":  self.dxy.signal if self.dxy else "",
                "detail":  self.dxy.detail if self.dxy else "",
            },
            "yields": {
                "value":   round(self.yields.value, 2) if self.yields else 0,
                "trend":   self.yields.trend if self.yields else "",
                "signal":  self.yields.signal if self.yields else "",
                "detail":  self.yields.detail if self.yields else "",
            },
            "gold": {
                "price":          round(self.gold_structure.price, 2) if self.gold_structure else 0,
                "trend":          self.gold_structure.trend if self.gold_structure else "",
                "key_level":      round(self.gold_structure.key_level, 2) if self.gold_structure else 0,
                "recent_high":    round(self.gold_structure.recent_high, 2) if self.gold_structure else 0,
                "recent_low":     round(self.gold_structure.recent_low, 2) if self.gold_structure else 0,
                "distance_to_kl": round(self.gold_structure.distance_to_kl, 2) if self.gold_structure else 0,
                "setup":          self.gold_structure.setup if self.gold_structure else "",
                "sma20":          round(self.gold_structure.sma20, 2) if self.gold_structure else 0,
                "sma50":          round(self.gold_structure.sma50, 2) if self.gold_structure else 0,
            },
            "silver": {
                "price":          round(self.silver_structure.price, 2) if self.silver_structure else 0,
                "trend":          self.silver_structure.trend if self.silver_structure else "",
                "key_level":      round(self.silver_structure.key_level, 2) if self.silver_structure else 0,
                "recent_high":    round(self.silver_structure.recent_high, 2) if self.silver_structure else 0,
                "recent_low":     round(self.silver_structure.recent_low, 2) if self.silver_structure else 0,
                "distance_to_kl": round(self.silver_structure.distance_to_kl, 2) if self.silver_structure else 0,
                "setup":          self.silver_structure.setup if self.silver_structure else "",
            },
            "signals_bullish": self.signals_bullish,
            "signals_bearish": self.signals_bearish,
            "setup_alert":     self.setup_alert,
        }


class MacroAnalyzer:
    """
    Analisa contexto macro para ouro e prata.
    Camada de suporte ao trading manual em XTB.
    """

    def __init__(self, feed):
        self.feed = feed

    def analyze(self) -> MacroSignal:
        """Análise macro completa."""
        signals_bullish = []
        signals_bearish = []
        score = 50  # começa neutro

        # ── DXY (UUP como proxy) ──────────────────────────────────────────
        dxy = self._analyze_dxy()
        if dxy:
            if dxy.trend == "BEARISH":
                score += 20
                signals_bullish.append(f"DXY em downtrend ({dxy.detail}) ✓ favorável ao ouro")
            elif dxy.trend == "BULLISH":
                score -= 20
                signals_bearish.append(f"DXY em uptrend ({dxy.detail}) ✗ pressão no ouro")
            else:
                signals_bullish.append(f"DXY neutro ({dxy.detail})")

        # ── Yields (TLT como proxy inverso) ──────────────────────────────
        yields = self._analyze_yields()
        if yields:
            if yields.trend == "BULLISH":  # TLT sobe = yields caem = favorável ao ouro
                score += 15
                signals_bullish.append(f"Yields a cair (TLT subindo: {yields.detail}) ✓")
            elif yields.trend == "BEARISH":  # TLT cai = yields sobem = desfavorável
                score -= 15
                signals_bearish.append(f"Yields a subir (TLT caindo: {yields.detail}) ✗")
            else:
                signals_bullish.append(f"Yields neutros ({yields.detail})")

        # ── VIX ──────────────────────────────────────────────────────────
        vix_level = self._get_vix()
        vix_signal = ""
        if vix_level > 0:
            if vix_level >= VIX_EXTREME:
                score += 20
                vix_signal = f"VIX extremo: {vix_level:.1f} — forte safe haven demand"
                signals_bullish.append(vix_signal + " ✓")
            elif vix_level >= VIX_HIGH:
                score += 10
                vix_signal = f"VIX elevado: {vix_level:.1f} — safe haven demand presente"
                signals_bullish.append(vix_signal + " ✓")
            else:
                vix_signal = f"VIX controlado: {vix_level:.1f}"

        # ── Estrutura de mercado — Ouro e Prata ──────────────────────────
        gold_structure   = self._analyze_structure("GLD", "Ouro")
        silver_structure = self._analyze_structure("SLV", "Prata")

        # Setup alert
        setup_alert = ""
        if gold_structure:
            if gold_structure.setup == "NEAR_KEY_LEVEL":
                setup_alert = f"⚡ OURO perto do Key Level (${gold_structure.key_level:.2f}) — potencial entrada"
            elif gold_structure.trend == "UPTREND" and gold_structure.setup == "NEAR_KEY_LEVEL":
                setup_alert = f"⚡ OURO em uptrend + perto do Key Level — setup de alta probabilidade"

        # ── Score final e bias ────────────────────────────────────────────
        score = max(0, min(100, score))

        if score >= 65:
            bias = "BULLISH"
        elif score <= 35:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        # Confiança baseada no número de sinais alinhados
        aligned = len(signals_bullish) if bias == "BULLISH" else len(signals_bearish)
        if aligned >= 3:
            confidence = "HIGH"
        elif aligned >= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return MacroSignal(
            date             = datetime.utcnow(),
            bias             = bias,
            score            = score,
            confidence       = confidence,
            dxy              = dxy,
            yields           = yields,
            vix_level        = vix_level,
            vix_signal       = vix_signal,
            gold_structure   = gold_structure,
            silver_structure = silver_structure,
            signals_bullish  = signals_bullish,
            signals_bearish  = signals_bearish,
            setup_alert      = setup_alert,
        )

    def _analyze_dxy(self) -> Optional[MacroComponent]:
        """Analisa o DXY via UUP ETF."""
        try:
            df = self.feed.get_bars("UUP", days=80)
            if df.empty or len(df) < SMA_LONG:
                return None

            price     = float(df["close"].iloc[-1])
            sma20     = float(df["close"].tail(SMA_SHORT).mean())
            sma50     = float(df["close"].tail(SMA_LONG).mean())
            prev_sma20 = float(df["close"].tail(SMA_SHORT + 5).head(SMA_SHORT).mean())

            # Tendência do DXY
            if price > sma20 > sma50 and sma20 > prev_sma20:
                trend = "BULLISH"
                signal = "desfavorável ao ouro"
            elif price < sma20 < sma50 and sma20 < prev_sma20:
                trend = "BEARISH"
                signal = "favorável ao ouro"
            else:
                trend = "NEUTRAL"
                signal = "neutro"

            pct_from_sma20 = (price - sma20) / sma20 * 100
            detail = f"UUP ${price:.3f} | SMA20 ${sma20:.3f} ({pct_from_sma20:+.1f}%)"

            return MacroComponent(
                name="DXY (UUP)", value=price,
                sma_short=sma20, sma_long=sma50,
                trend=trend, signal=signal, detail=detail
            )
        except Exception as e:
            logger.error(f"Erro _analyze_dxy: {e}")
            return None

    def _analyze_yields(self) -> Optional[MacroComponent]:
        """Analisa yields via TLT (inverso: TLT sobe = yields caem)."""
        try:
            df = self.feed.get_bars("TLT", days=80)
            if df.empty or len(df) < SMA_LONG:
                return None

            price     = float(df["close"].iloc[-1])
            sma20     = float(df["close"].tail(SMA_SHORT).mean())
            sma50     = float(df["close"].tail(SMA_LONG).mean())

            # TLT sobe = yields caem = favorável ao ouro
            if price > sma20 > sma50:
                trend = "BULLISH"  # yields a cair
                signal = "yields a cair — favorável ao ouro"
            elif price < sma20 < sma50:
                trend = "BEARISH"  # yields a subir
                signal = "yields a subir — pressão no ouro"
            else:
                trend = "NEUTRAL"
                signal = "yields neutros"

            pct = (price - sma20) / sma20 * 100
            detail = f"TLT ${price:.2f} | SMA20 ${sma20:.2f} ({pct:+.1f}%)"

            return MacroComponent(
                name="Yields (TLT)", value=price,
                sma_short=sma20, sma_long=sma50,
                trend=trend, signal=signal, detail=detail
            )
        except Exception as e:
            logger.error(f"Erro _analyze_yields: {e}")
            return None

    def _get_vix(self) -> float:
        try:
            df = self.feed.get_bars("^VIX", days=5)
            return float(df["close"].iloc[-1]) if not df.empty else 0.0
        except Exception:
            return 0.0

    def _analyze_structure(self, ticker: str, name: str) -> Optional[MarketStructure]:
        """Analisa estrutura de mercado simplificada."""
        try:
            df = self.feed.get_bars(ticker, days=120)
            if df.empty or len(df) < 50:
                return None

            price  = float(df["close"].iloc[-1])
            sma20  = float(df["close"].tail(20).mean())
            sma50  = float(df["close"].tail(50).mean())

            # Tendência
            if price > sma20 > sma50:
                trend = "UPTREND"
            elif price < sma20 < sma50:
                trend = "DOWNTREND"
            else:
                trend = "RANGING"

            # Key level — mínimo dos últimos 20 dias (proxy do Up Key Level)
            recent_low  = float(df["low"].tail(20).min())
            recent_high = float(df["high"].tail(20).max())

            # Key level para uptrend = suporte recente mais próximo
            # Simplificação: mínimo dos últimos 10 dias
            key_level = float(df["low"].tail(10).min())

            distance_to_kl = (price - key_level) / price * 100

            # Setup
            if distance_to_kl <= 2.0:
                setup = "NEAR_KEY_LEVEL"
            elif distance_to_kl >= 8.0:
                setup = "EXTENDED"
            else:
                setup = "NORMAL"

            return MarketStructure(
                asset          = name,
                price          = price,
                sma20          = sma20,
                sma50          = sma50,
                trend          = trend,
                key_level      = key_level,
                recent_high    = recent_high,
                recent_low     = recent_low,
                distance_to_kl = distance_to_kl,
                setup          = setup,
            )
        except Exception as e:
            logger.error(f"Erro _analyze_structure {ticker}: {e}")
            return None
