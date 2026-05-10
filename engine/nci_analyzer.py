"""
Integral Trading — NCI Analyzer
=================================
Análise técnica NCI/SMC multi-timeframe.
Baseado na metodologia Jayce Pham (NCI).

Pipeline por activo:
  1. Daily  — estrutura macro (trend, Key Level dinâmico)
  2. H4     — pullback à zona + Order Block
  3. H1     — BOS confirmação + manipulação

Output: NCISignal com entrada, stop, target e score de confluência.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Caminho para o JSON de parâmetros
_CONFIG_PATH = Path(__file__).parent.parent / "knowledge" / "nci_strategy.json"


# ─────────────────────────────────────────────────────────────────────────────
# Estruturas de dados
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KeyLevel:
    price: float
    origin: str          # "swing_low" / "swing_high" / "order_block"
    timeframe: str       # "daily" / "h4"
    bar_index: int       # posição no DataFrame
    strength: int        # 1-10


@dataclass
class OrderBlock:
    high: float
    low: float
    mid: float
    timeframe: str
    bullish: bool        # True = OB bullish (suporte), False = OB bearish (resistência)
    bar_index: int


@dataclass
class TimeframeView:
    timeframe: str
    trend: str           # UPTREND / DOWNTREND / RANGING
    price: float
    sma20: float
    sma50: float
    key_level: Optional[KeyLevel]
    order_block: Optional[OrderBlock]
    bos_confirmed: bool
    manipulation_detected: bool
    recent_high: float
    recent_low: float
    bars: int            # número de barras disponíveis


@dataclass
class NCISignal:
    ticker: str
    date: datetime

    # Análise por timeframe
    daily: Optional[TimeframeView]
    h4: Optional[TimeframeView]
    h1: Optional[TimeframeView]

    # Confluência
    direction: str           # LONG / SHORT / NONE
    setup_quality: str       # A+ / A / B / C / NONE
    confluence_score: int    # 0-100

    # Níveis de trading
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float

    # Contexto
    setup_active: bool
    setup_description: str
    alerts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticker":             self.ticker,
            "date":               self.date.strftime("%Y-%m-%d %H:%M"),
            "direction":          self.direction,
            "setup_quality":      self.setup_quality,
            "confluence_score":   self.confluence_score,
            "setup_active":       self.setup_active,
            "setup_description":  self.setup_description,
            "entry_price":        round(self.entry_price, 4),
            "stop_loss":          round(self.stop_loss, 4),
            "target_1":           round(self.target_1, 4),
            "target_2":           round(self.target_2, 4),
            "risk_reward":        round(self.risk_reward, 2),
            "daily_trend":        self.daily.trend if self.daily else "N/A",
            "h4_trend":           self.h4.trend if self.h4 else "N/A",
            "h1_trend":           self.h1.trend if self.h1 else "N/A",
            "h4_bos":             self.h4.bos_confirmed if self.h4 else False,
            "h1_bos":             self.h1.bos_confirmed if self.h1 else False,
            "manipulation":       (self.h4.manipulation_detected or
                                   (self.h1.manipulation_detected if self.h1 else False)),
            "key_level":          round(self.h4.key_level.price, 4)
                                  if self.h4 and self.h4.key_level else 0,
            "alerts":             self.alerts,
            "fundamental_risk":   getattr(self, 'fundamental_risk', 'NONE'),
            "fundamental_block":  getattr(self, 'fundamental_block', False),
            "fundamental_bias":   getattr(self, 'fundamental_bias', ''),
            "fundamental_text":   getattr(self, 'fundamental_text', ''),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Analyzer
# ─────────────────────────────────────────────────────────────────────────────

class NCIAnalyzer:
    """
    Análise NCI/SMC para qualquer activo (commodities, forex, acções).
    Usa Daily + H4 + H1 em cascata.
    """

    # Pares onde USD forte invalida LONG
    _USD_NEGATIVE = {"EURUSD=X", "GBPUSD=X", "AUDUSD=X", "NZDUSD=X", "XAUUSD=X", "XAGUSD=X", "GC=F", "SI=F"}
    # Pares onde USD forte confirma LONG
    _USD_POSITIVE = {"USDJPY=X", "USDCAD=X", "USDCHF=X"}

    def __init__(self, feed, config_path: Path = _CONFIG_PATH,
                 calendar=None):
        self.feed     = feed
        self.cfg      = self._load_config(config_path)
        self.calendar = calendar  # EconomicCalendar opcional

        # Parâmetros da config
        self.pivot_strength    = self.cfg["pivot"]["strength"]
        self.pullback_zone_pct = self.cfg["entry"]["pullback_zone_pct"]
        self.min_rr            = self.cfg["entry"]["min_rr"]
        self.stop_buffer_pct   = self.cfg["entry"]["stop_buffer_pct"]
        self.max_manip_pct     = self.cfg["manipulation"]["max_penetration_pct"]
        self.bos_required      = self.cfg["bos"]["required"]
        self.bos_tf            = self.cfg["bos"]["timeframe"]   # "h4" ou "h1"
        self.sma_fast          = self.cfg["trend"]["sma_fast"]
        self.sma_slow          = self.cfg["trend"]["sma_slow"]
        self.min_confluence    = self.cfg["filters"]["min_confluence_score"]

        # Limites de distância KL→preço por timeframe (NCI estrutural)
        kl_cfg = self.cfg.get("key_level", {}).get("max_distance_pct", {})
        self.max_kl_dist = {
            "daily": float(kl_cfg.get("daily", 10.0)),
            "h4":    float(kl_cfg.get("h4",    5.0)),
            "h1":    float(kl_cfg.get("h1",    3.0)),
        }

    # ── API pública ───────────────────────────────────────────────────────────

    def analyze(self, ticker: str) -> NCISignal:
        """Análise completa NCI para um activo."""
        mtf = self.feed.get_multi_timeframe(ticker)

        daily_view = self._analyze_timeframe(
            mtf.get("daily"), "daily", ticker
        )
        h4_view = self._analyze_timeframe(
            mtf.get("h4"), "h4", ticker,
            reference_key_level=daily_view.key_level if daily_view else None
        )
        h1_view = self._analyze_timeframe(
            mtf.get("h1"), "h1", ticker,
            reference_key_level=h4_view.key_level if h4_view else None
        )

        signal = self._build_signal(ticker, daily_view, h4_view, h1_view)

        # Enriquecer com contexto fundamental (se calendar disponível)
        if self.calendar and signal.direction != "NONE":
            try:
                risk = self.calendar.get_asset_risk(ticker, hours_ahead=48)
                signal.fundamental_risk   = risk.risk_level
                signal.fundamental_block  = risk.in_block_zone
                signal.fundamental_bias   = risk.direction_bias or ""
                signal.fundamental_events = [e.to_dict() for e in risk.events]
                signal.fundamental_text   = risk.context_text

                # Ajustar alertas
                if risk.risk_level == "HIGH" and not risk.in_block_zone:
                    signal.alerts.append("⚠️ Evento HIGH IMPACT próximo — aguardar")
                elif risk.in_block_zone:
                    signal.alerts.append("🔴 BLOQUEADO — evento a decorrer agora")

                # Se evento contradiz direcção técnica
                if risk.direction_bias == "UNCERTAIN":
                    signal.alerts.append("⚡ Evento pode reverter direcção — cuidado")

            except Exception as _e:
                import logging as _log
                _log.getLogger(__name__).warning("Calendar error: " + str(_e))

        return signal

    def analyze_batch(self, tickers: list) -> dict:
        """Analisa múltiplos activos. Retorna {ticker: NCISignal}."""
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = self.analyze(ticker)
            except Exception as e:
                logger.error("NCIAnalyzer erro " + ticker + ": " + str(e))
        return results

    # ── Análise por timeframe ─────────────────────────────────────────────────

    def _analyze_timeframe(self, df: Optional[pd.DataFrame], timeframe: str,
                            ticker: str,
                            reference_key_level: Optional[KeyLevel] = None
                            ) -> Optional[TimeframeView]:
        """Analisa estrutura num timeframe específico."""
        if df is None or df.empty or len(df) < self.sma_slow + 5:
            return None

        price      = float(df["close"].iloc[-1])
        sma20      = float(df["close"].tail(self.sma_fast).mean())
        sma50      = float(df["close"].tail(self.sma_slow).mean())
        recent_high = float(df["high"].tail(20).max())
        recent_low  = float(df["low"].tail(20).min())

        # Tendência e Key Level — NCI puro (estrutura define trend, não SMAs)
        trend, key_level = self._detect_structure(df, timeframe)

        # Se temos KL de referência do timeframe superior, usar o mais próximo
        if reference_key_level and key_level:
            # Preferir KL do timeframe superior se estiver perto do preço
            ref_dist = abs(price - reference_key_level.price) / price * 100
            cur_dist = abs(price - key_level.price) / price * 100
            if ref_dist < cur_dist and ref_dist < self.pullback_zone_pct * 2:
                key_level = reference_key_level

        # Order Block
        order_block = self._detect_order_block(df, key_level, trend)

        # BOS (Break of Structure)
        bos_confirmed = self._detect_bos(df, trend)

        # Manipulação (wick abaixo KL mas close acima)
        manipulation = self._detect_manipulation(df, key_level) if key_level else False

        return TimeframeView(
            timeframe=timeframe,
            trend=trend,
            price=price,
            sma20=sma20,
            sma50=sma50,
            key_level=key_level,
            order_block=order_block,
            bos_confirmed=bos_confirmed,
            manipulation_detected=manipulation,
            recent_high=recent_high,
            recent_low=recent_low,
            bars=len(df),
        )

    # ── Detecção de Key Level ─────────────────────────────────────────────────

    # ── NCI estrutural: trend e Key Level numa só análise ───────────────────

    def _detect_structure(self, df: pd.DataFrame, timeframe: str):
        """
        Detecta trend e Key Level pela estrutura (não por SMAs).

        Lógica NCI pura:
          1. HL que precederam HH+BOS → KL bullish candidatos
          2. LH que precederam LL+BOS → KL bearish candidatos
          3. Leitura B: KL ainda não quebrado pelo preço
          4. Filtro de distância: KL não pode estar mais longe que max_kl_dist[tf]
          5. Trend = lado com BOS mais recente

        Retorna: (trend: str, key_level: Optional[KeyLevel])
        """
        n = self.pivot_strength
        if df is None or df.empty or len(df) < n * 2 + 5:
            return ("RANGING", None)

        closes = df["close"].values
        lows   = df["low"].values
        highs  = df["high"].values
        price  = float(closes[-1])

        max_dist = self.max_kl_dist.get(timeframe, 10.0)

        pivot_lows  = self._find_pivots(lows,  n, is_low=True)
        pivot_highs = self._find_pivots(highs, n, is_low=False)

        # Candidatos bullish (HL → HH → BOS)
        bullish = []
        for sl_idx in pivot_lows:
            sl_price = lows[sl_idx]
            future_highs = [(j, highs[j]) for j in pivot_highs
                            if j > sl_idx and highs[j] > sl_price]
            if not future_highs:
                continue
            sh_idx, sh_price = future_highs[0]
            if sh_idx + 1 >= len(df):
                continue
            future_closes = closes[sh_idx + 1:]
            bos_offsets = [k for k, c in enumerate(future_closes) if c > sh_price]
            if not bos_offsets:
                continue
            bos_idx = sh_idx + 1 + bos_offsets[0]
            bullish.append((sl_idx, float(sl_price), bos_idx))

        # Candidatos bearish (LH → LL → BOS)
        bearish = []
        for sh_idx in pivot_highs:
            sh_price = highs[sh_idx]
            future_lows = [(j, lows[j]) for j in pivot_lows
                           if j > sh_idx and lows[j] < sh_price]
            if not future_lows:
                continue
            sl_idx, sl_price = future_lows[0]
            if sl_idx + 1 >= len(df):
                continue
            future_closes = closes[sl_idx + 1:]
            bos_offsets = [k for k, c in enumerate(future_closes) if c < sl_price]
            if not bos_offsets:
                continue
            bos_idx = sl_idx + 1 + bos_offsets[0]
            bearish.append((sh_idx, float(sh_price), bos_idx))

        # Leitura B + filtro de distância
        bullish_alive = []
        for idx, p, bos in bullish:
            if price > p:
                dist = (price - p) / price * 100
                if dist <= max_dist:
                    bullish_alive.append((idx, p, bos))

        bearish_alive = []
        for idx, p, bos in bearish:
            if price < p:
                dist = (p - price) / price * 100
                if dist <= max_dist:
                    bearish_alive.append((idx, p, bos))

        # Decidir trend
        if not bullish_alive and not bearish_alive:
            return ("RANGING", None)

        last_bull_bos = bullish_alive[-1][2] if bullish_alive else -1
        last_bear_bos = bearish_alive[-1][2] if bearish_alive else -1

        if last_bull_bos > last_bear_bos:
            kl_idx, kl_price, _ = bullish_alive[-1]
            kl = KeyLevel(
                price=kl_price,
                origin="swing_low_validated",
                timeframe=timeframe,
                bar_index=kl_idx,
                strength=self._pivot_strength_score(df, kl_idx, n),
            )
            return ("UPTREND", kl)
        elif last_bear_bos > last_bull_bos:
            kl_idx, kl_price, _ = bearish_alive[-1]
            kl = KeyLevel(
                price=kl_price,
                origin="swing_high_validated",
                timeframe=timeframe,
                bar_index=kl_idx,
                strength=self._pivot_strength_score(df, kl_idx, n),
            )
            return ("DOWNTREND", kl)
        else:
            return ("RANGING", None)

    # ── Wrapper legacy ──────────────────────────────────────────────────────

    def _detect_key_level(self, df: pd.DataFrame, timeframe: str,
                           trend: str):
        """Wrapper para retrocompatibilidade. Lógica em _detect_structure."""
        _, kl = self._detect_structure(df, timeframe)
        return kl

    def _find_pivots(self, values, n: int, is_low: bool) -> list:
        """
        Encontra índices de pivots (highs ou lows).
        Um pivot low: valor[i] < todos os valores em [i-n, i+n]
        """
        pivots = []
        length = len(values)
        for i in range(n, length - n):
            window = list(values[i - n: i]) + list(values[i + 1: i + n + 1])
            if is_low:
                if all(values[i] <= v for v in window):
                    pivots.append(i)
            else:
                if all(values[i] >= v for v in window):
                    pivots.append(i)
        return pivots

    def _pivot_strength_score(self, df: pd.DataFrame, bar_idx: int,
                               n: int) -> int:
        """Score de força do pivot — quantas vezes o preço testou este nível."""
        kl_price = float(df["low"].iloc[bar_idx])
        tolerance = kl_price * 0.005  # 0.5% de tolerância
        tests = sum(
            1 for low in df["low"].values
            if abs(low - kl_price) <= tolerance
        )
        return min(tests, 10)

    # ── Detecção de Order Block ───────────────────────────────────────────────

    def _detect_order_block(self, df: pd.DataFrame,
                             key_level: Optional[KeyLevel],
                             trend: str) -> Optional[OrderBlock]:
        """
        Order Block = último candle bearish antes de impulso bullish forte.
        Para longs: procura o último candle vermelho antes de uma sequência
        de 2+ candles verdes com body > média.
        """
        if len(df) < 10:
            return None

        opens  = df["open"].values
        closes = df["close"].values
        highs  = df["high"].values
        lows   = df["low"].values

        avg_body = float((abs(closes - opens)).mean())

        if trend in ("UPTREND", "RANGING"):
            # Procura OB bullish (suporte) — zona de reacumulação
            # Olha para os últimos 30 candles
            lookback = min(30, len(df) - 1)
            for i in range(len(df) - 2, len(df) - lookback, -1):
                # Candle bearish (vermelho)
                if closes[i] >= opens[i]:
                    continue
                # Seguido de pelo menos 1 candle bullish forte
                if i + 1 >= len(df):
                    continue
                next_body = closes[i + 1] - opens[i + 1]
                if next_body > avg_body * 0.8 and closes[i + 1] > opens[i + 1]:
                    ob_high = float(highs[i])
                    ob_low  = float(lows[i])
                    # OB relevante se estiver perto do KL ou do preço actual
                    price = float(closes[-1])
                    dist  = abs(price - ob_low) / price * 100
                    if dist < self.pullback_zone_pct * 3:
                        return OrderBlock(
                            high=ob_high, low=ob_low,
                            mid=(ob_high + ob_low) / 2,
                            timeframe=df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], 'strftime') else "unknown",
                            bullish=True,
                            bar_index=i,
                        )

        elif trend == "DOWNTREND":
            # OB bearish (resistência) — último candle verde antes de queda
            lookback = min(30, len(df) - 1)
            for i in range(len(df) - 2, len(df) - lookback, -1):
                if closes[i] <= opens[i]:
                    continue
                if i + 1 >= len(df):
                    continue
                next_body = opens[i + 1] - closes[i + 1]
                if next_body > avg_body * 0.8 and closes[i + 1] < opens[i + 1]:
                    ob_high = float(highs[i])
                    ob_low  = float(lows[i])
                    price   = float(closes[-1])
                    dist    = abs(price - ob_high) / price * 100
                    if dist < self.pullback_zone_pct * 3:
                        return OrderBlock(
                            high=ob_high, low=ob_low,
                            mid=(ob_high + ob_low) / 2,
                            timeframe=df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], 'strftime') else "unknown",
                            bullish=False,
                            bar_index=i,
                        )

        return None

    # ── Detecção de BOS ───────────────────────────────────────────────────────

    def _detect_bos(self, df: pd.DataFrame, trend: str) -> bool:
        """
        Break of Structure — o preço fechou acima do swing high do pullback
        (para longs) ou abaixo do swing low (para shorts).

        Procura nos últimos 10 candles se houve um BOS recente.
        """
        if len(df) < 15:
            return False

        closes = df["close"].values
        highs  = df["high"].values
        lows   = df["low"].values
        price  = closes[-1]

        lookback = min(15, len(df) - 1)

        if trend in ("UPTREND", "RANGING"):
            # BOS bullish: close actual > swing high do pullback recente
            # Swing high do pullback = máximo dos últimos N candles, excluindo os últimos 2
            swing_high = float(df["high"].iloc[-lookback:-2].max()) if lookback > 2 else 0
            if swing_high > 0 and price > swing_high:
                return True

        elif trend == "DOWNTREND":
            # BOS bearish: close actual < swing low do rally recente
            swing_low = float(df["low"].iloc[-lookback:-2].min()) if lookback > 2 else float("inf")
            if swing_low < float("inf") and price < swing_low:
                return True

        return False

    # ── Detecção de Manipulação ───────────────────────────────────────────────

    def _detect_manipulation(self, df: pd.DataFrame,
                              key_level: Optional[KeyLevel]) -> bool:
        """
        Manipulação (liquidity grab):
        - Wick penetra abaixo do Key Level (para longs)
        - Mas o candle fecha ACIMA do Key Level
        - Penetração < max_manip_pct

        Procura nos últimos 5 candles.
        """
        if key_level is None or len(df) < 5:
            return False

        kl = key_level.price
        lookback = min(5, len(df))

        for i in range(-lookback, 0):
            low_i   = float(df["low"].iloc[i])
            close_i = float(df["close"].iloc[i])

            if "swing_low" in key_level.origin:
                # Wick abaixo do KL mas close acima = manipulação bullish
                if low_i < kl and close_i > kl:
                    penetration = (kl - low_i) / kl * 100
                    if penetration <= self.max_manip_pct:
                        return True
            else:
                # Wick acima do KL mas close abaixo = manipulação bearish
                high_i = float(df["high"].iloc[i])
                if high_i > kl and close_i < kl:
                    penetration = (high_i - kl) / kl * 100
                    if penetration <= self.max_manip_pct:
                        return True

        return False

    # ── Construção do sinal final ─────────────────────────────────────────────

    def _build_signal(self, ticker: str,
                       daily: Optional[TimeframeView],
                       h4: Optional[TimeframeView],
                       h1: Optional[TimeframeView]) -> NCISignal:
        """
        Combina análise dos 3 timeframes num sinal de trading.

        Lógica de confluência:
          Daily UPTREND                        → +30 pts
          H4 pullback ao KL (<= pullback_zone) → +25 pts
          H4 Order Block presente              → +10 pts
          BOS confirmado (H4 ou H1)            → +20 pts
          Manipulação detectada                → +10 pts
          H1 confirma direcção Daily           → +5 pts
        """
        alerts = []
        score  = 0
        direction = "NONE"
        entry = stop = target_1 = target_2 = 0.0

        # Sem dados diários = sem sinal
        if daily is None or daily.bars < self.sma_slow + 5:
            return self._no_signal(ticker, alerts=["Dados diários insuficientes"])

        price = daily.price

        # ── 1. Tendência Daily ────────────────────────────────────────────────
        # Pesos recalibrados com base em backtesting — escala 0-100 atingível

        if daily.trend == "UPTREND":
            direction = "LONG"
            score += 25
        elif daily.trend == "DOWNTREND":
            direction = "SHORT"
            score += 25
        else:
            # Daily RANGING — verificar se H4+H1 concordam
            if h4 and h1 and h4.trend == h1.trend and h4.trend != "RANGING":
                direction = "LONG" if h4.trend == "UPTREND" else "SHORT"
                score += 10  # score reduzido — sem confirmação daily
                alerts.append("Daily RANGING mas H4+H1 alinham: " + h4.trend)
            else:
                direction = "NONE"
                alerts.append("Daily RANGING — sem direcção clara")

        if direction == "NONE":
            return self._no_signal(ticker, alerts=alerts)

        # ── 2. H4 — pullback ao Key Level ────────────────────────────────────
        # Zona exacta (≤2%): +30 | Próximo (≤6%): +20 | Distante: +5
        # Backtesting mostrou que KL próximo é o sinal mais frequente e válido

        h4_kl = None
        if h4 and h4.key_level:
            h4_kl = h4.key_level
            dist_to_kl = abs(price - h4_kl.price) / price * 100

            if dist_to_kl <= self.pullback_zone_pct:
                score += 30
                alerts.append("✅ Pullback ao KL H4 ($" +
                               str(round(h4_kl.price, 4)) + ")")
            elif dist_to_kl <= self.pullback_zone_pct * 3:
                score += 20
                alerts.append("KL H4 próximo ($" +
                               str(round(h4_kl.price, 4)) +
                               " | " + str(round(dist_to_kl, 1)) + "% distância)")
            elif dist_to_kl <= self.pullback_zone_pct * 6:
                score += 5
                alerts.append("KL H4 distante (" +
                               str(round(dist_to_kl, 1)) + "%)")
            else:
                alerts.append("Distante do KL H4 (" +
                               str(round(dist_to_kl, 1)) + "% — extendido)")
                # Preço muito extendido — penalização severa
                score = max(0, score - 30)
                alerts.append("⛔ Setup inválido — aguardar pullback ao KL")
        else:
            alerts.append("Key Level H4 não detectado")

        # ── 3. H4 — Order Block ───────────────────────────────────────────────

        if h4 and h4.order_block:
            score += 15
            ob = h4.order_block
            alerts.append("✅ Order Block H4 [" +
                           str(round(ob.low, 4)) + "-" +
                           str(round(ob.high, 4)) + "]")

        # ── 4. BOS (H4 ou H1) ────────────────────────────────────────────────

        bos_h4 = h4.bos_confirmed if h4 else False
        bos_h1 = h1.bos_confirmed if h1 else False

        if bos_h1:
            score += 20
            alerts.append("✅ BOS confirmado H1")
        elif bos_h4:
            score += 15
            alerts.append("✅ BOS confirmado H4")
        else:
            if self.bos_required:
                alerts.append("⚠️ BOS não confirmado — aguardar")

        # ── 5. Manipulação ────────────────────────────────────────────────────

        manip_h4 = h4.manipulation_detected if h4 else False
        manip_h1 = h1.manipulation_detected if h1 else False

        if manip_h4 or manip_h1:
            score += 10
            alerts.append("✅ Manipulação detectada (liquidity grab)")

        # ── 6. H1 confirma ou diverge ────────────────────────────────────────

        if h1 and h1.trend == daily.trend:
            score += 5
            alerts.append("H1 alinha com Daily ✓")
        elif h1 and h1.trend != daily.trend and h1.trend != "RANGING":
            score -= 10
            alerts.append("⚠️ H1 diverge do Daily")

        # ── Calcular níveis de trading ────────────────────────────────────────

        kl_price = h4_kl.price if h4_kl else (
            daily.key_level.price if daily.key_level else price * 0.97
        )

        if direction == "LONG":
            # Stop abaixo do wick mínimo recente ou abaixo do KL
            if h4 and h4.key_level:
                recent_low = float(h4.recent_low)
                stop = recent_low * (1 - self.stop_buffer_pct / 100)
            else:
                stop = kl_price * (1 - self.stop_buffer_pct / 100)

            risk = abs(price - stop)

            # Target = swing high anterior (resistência estrutural)
            # Se não há swing high claro, usa min_rr como fallback
            if h4 and h4.recent_high > price:
                structural_target = float(h4.recent_high)
                # Verificar se o structural target dá R:R mínimo
                structural_rr = abs(structural_target - price) / risk if risk > 0 else 0
                if structural_rr >= self.min_rr * 0.8:
                    target_1 = structural_target
                else:
                    target_1 = price + risk * self.min_rr
            else:
                target_1 = price + risk * self.min_rr

            target_2 = price + risk * self.min_rr * 1.5
            entry    = price

        else:  # SHORT
            if h4 and h4.key_level:
                recent_high = float(h4.recent_high)
                stop = recent_high * (1 + self.stop_buffer_pct / 100)
            else:
                stop = kl_price * (1 + self.stop_buffer_pct / 100)

            risk = abs(stop - price)

            # Target = swing low anterior (suporte estrutural)
            if h4 and h4.recent_low < price:
                structural_target = float(h4.recent_low)
                structural_rr = abs(price - structural_target) / risk if risk > 0 else 0
                if structural_rr >= self.min_rr * 0.8:
                    target_1 = structural_target
                else:
                    target_1 = price - risk * self.min_rr
            else:
                target_1 = price - risk * self.min_rr

            target_2 = price - risk * self.min_rr * 1.5
            entry    = price

        risk_pct   = abs(price - stop) / price * 100
        reward_pct = abs(target_1 - price) / price * 100
        rr         = reward_pct / risk_pct if risk_pct > 0 else 0

        # R:R insuficiente
        if rr < self.min_rr - 0.01:  # margem para floating point
            alerts.append("⚠️ R:R insuficiente (" + str(round(rr, 2)) + ")")
            score = max(0, score - 15)

        # ── Setup quality ─────────────────────────────────────────────────────

        score = max(0, min(100, score))

        if score >= 80:
            quality = "A+"
        elif score >= 65:
            quality = "A"
        elif score >= self.min_confluence:
            quality = "B"
        elif score >= 25:
            quality = "C"
        else:
            quality = "NONE"

        setup_active = (
            quality in ("A+", "A", "B") and
            (bos_h4 or bos_h1 or not self.bos_required) and
            rr >= self.min_rr
        )

        # Descrição do setup
        bos_str  = "BOS ✅" if (bos_h4 or bos_h1) else "sem BOS"
        manip_str = " + Manipulação ✅" if (manip_h4 or manip_h1) else ""
        kl_str   = "$" + str(round(kl_price, 4))
        setup_desc = (
            direction + " | " + daily.trend + " Daily | KL " + kl_str +
            " | " + bos_str + manip_str +
            " | Score " + str(score) + "/100"
        )

        # ── Filtro DXY ────────────────────────────────────────────────────────
        # Obter tendência DXY e ajustar score/alerts
        try:
            from engine.macro_analyzer import MacroAnalyzer
            macro = MacroAnalyzer(self.feed).analyze()
            dxy_trend = macro.dxy.trend if macro.dxy else "NEUTRAL"

            if dxy_trend == "BULLISH":
                # USD forte
                if ticker in self._USD_NEGATIVE and direction == "LONG":
                    score = max(0, score - 25)
                    alerts.append("⚠️ DXY UPTREND — USD forte contradiz LONG")
                elif ticker in self._USD_POSITIVE and direction == "SHORT":
                    score = max(0, score - 25)
                    alerts.append("⚠️ DXY UPTREND — USD forte contradiz SHORT")
                elif ticker in self._USD_POSITIVE and direction == "LONG":
                    score = min(100, score + 10)
                    alerts.append("✅ DXY confirma direcção LONG")

            elif dxy_trend == "BEARISH":
                # USD fraco
                if ticker in self._USD_NEGATIVE and direction == "LONG":
                    score = min(100, score + 10)
                    alerts.append("✅ DXY fraco confirma LONG")
                elif ticker in self._USD_POSITIVE and direction == "LONG":
                    score = max(0, score - 20)
                    alerts.append("⚠️ DXY DOWNTREND — USD fraco contradiz LONG")

            # Recalcular qualidade após ajuste DXY
            score = max(0, min(100, score))
            if score >= 80:
                quality = "A+"
            elif score >= 65:
                quality = "A"
            elif score >= self.min_confluence:
                quality = "B"
            elif score >= 25:
                quality = "C"
            else:
                quality = "NONE"

            setup_active = (
                quality in ("A+", "A", "B") and
                (bos_h4 or bos_h1 or not self.bos_required) and
                rr >= self.min_rr - 0.01
            )

        except Exception as _dxy_err:
            import logging as _log
            _log.getLogger(__name__).warning("Filtro DXY falhou: " + str(_dxy_err))

        return NCISignal(
            ticker=ticker,
            date=datetime.utcnow(),
            daily=daily,
            h4=h4,
            h1=h1,
            direction=direction,
            setup_quality=quality,
            confluence_score=score,
            entry_price=entry,
            stop_loss=stop,
            target_1=target_1,
            target_2=target_2,
            risk_reward=rr,
            setup_active=setup_active,
            setup_description=setup_desc,
            alerts=alerts,
        )

    def _no_signal(self, ticker: str, alerts: list = None) -> NCISignal:
        return NCISignal(
            ticker=ticker,
            date=datetime.utcnow(),
            daily=None, h4=None, h1=None,
            direction="NONE",
            setup_quality="NONE",
            confluence_score=0,
            entry_price=0, stop_loss=0,
            target_1=0, target_2=0,
            risk_reward=0,
            setup_active=False,
            setup_description="Sem dados ou sem setup",
            alerts=alerts or [],
        )

    # ── Config ────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_config(path: Path) -> dict:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Config NCI não encontrada (" + str(e) +
                           ") — usando defaults")
            return {
                "pivot":        {"strength": 3},
                "entry":        {"pullback_zone_pct": 2.0, "min_rr": 2.5,
                                 "stop_buffer_pct": 0.3},
                "manipulation": {"enabled": True, "max_penetration_pct": 1.5},
                "bos":          {"required": True, "timeframe": "h1"},
                "trend":        {"sma_fast": 20, "sma_slow": 50},
                "filters":      {"macro_min_score": 40,
                                 "min_confluence_score": 60},
                "assets":       {"commodities": [], "forex": []},
            }
