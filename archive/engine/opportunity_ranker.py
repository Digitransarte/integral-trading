"""
Integral Trading — Opportunity Ranker
=======================================
Combina NCI (commodities/forex) e EP (stocks) num ranking diário.

Output: lista ordenada de oportunidades com score combinado,
entrada, stop, target e contexto macro.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Opportunity:
    rank:          int
    ticker:        str
    name:          str
    asset_class:   str        # "commodity" / "forex" / "stock"
    strategy:      str        # "NCI" / "EP"
    direction:     str        # "LONG" / "SHORT"
    score:         int        # 0-100
    quality:       str        # A+ / A / B / C / NONE
    entry_price:   float
    stop_loss:     float
    target_1:      float
    risk_reward:   float
    setup_active:  bool
    setup_desc:    str
    alerts:        list = field(default_factory=list)
    macro_bias:    str = ""
    macro_score:   int = 0
    scan_date:     str = ""

    def __post_init__(self):
        if not self.scan_date:
            self.scan_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    @property
    def action_icon(self) -> str:
        if not self.setup_active:
            return "⚪"
        if self.quality in ("A+", "A"):
            return "🟢"
        if self.quality == "B":
            return "🟡"
        return "⚪"

    def to_dict(self) -> dict:
        return {
            "rank":         self.rank,
            "ticker":       self.ticker,
            "name":         self.name,
            "asset_class":  self.asset_class,
            "strategy":     self.strategy,
            "direction":    self.direction,
            "score":        self.score,
            "quality":      self.quality,
            "entry_price":  round(self.entry_price, 4),
            "stop_loss":    round(self.stop_loss, 4),
            "target_1":     round(self.target_1, 4),
            "risk_reward":  round(self.risk_reward, 2),
            "setup_active": self.setup_active,
            "setup_desc":   self.setup_desc,
            "alerts":       self.alerts,
            "macro_bias":   self.macro_bias,
            "macro_score":  self.macro_score,
            "action_icon":  self.action_icon,
            "scan_date":    self.scan_date,
        }


class OpportunityRanker:
    """
    Varre commodities, forex e stocks.
    Devolve lista ordenada por score combinado.
    """

    # Activos NCI activos (validados por backtesting)
    NCI_ACTIVE = {
        "GC=F":     ("Ouro",          "commodity"),
        "SI=F":     ("Prata",         "commodity"),
        "CL=F":     ("Petróleo WTI",  "commodity"),
        "BZ=F":     ("Petróleo Brent","commodity"),
        "NG=F":     ("Gás Natural",   "commodity"),
        # "HG=F": ("Cobre", "commodity"),  # Removido — WR 35%, requer filtro China PMI
        "EURUSD=X": ("EUR/USD",       "forex"),
        "GBPUSD=X": ("GBP/USD",       "forex"),
        "USDJPY=X": ("USD/JPY",       "forex"),
        "AUDUSD=X": ("AUD/USD",       "forex"),
        "USDCAD=X": ("USD/CAD",       "forex"),
        "AUDJPY=X": ("AUD/JPY",       "forex"),
    }

    def __init__(self, feed):
        self.feed = feed

    def run(self, include_stocks: bool = False,
            min_score: int = 25,
            direction_filter: str = "LONG") -> list:
        """
        Corre análise NCI em todos os activos activos.
        Retorna lista de Opportunity ordenada por score.

        Args:
            include_stocks:   incluir EP scanner de stocks
            min_score:        score mínimo NCI para incluir
            direction_filter: "LONG" / "SHORT" / "ALL"
        """
        opportunities = []

        # ── NCI — commodities e forex ─────────────────────────────────────
        nci_opps = self._scan_nci(min_score, direction_filter)
        opportunities.extend(nci_opps)

        # ── EP — stocks (opcional) ────────────────────────────────────────
        if include_stocks:
            ep_opps = self._scan_ep()
            opportunities.extend(ep_opps)

        # Ordenar por: setup_active primeiro, depois score
        opportunities.sort(
            key=lambda o: (not o.setup_active, -o.score)
        )

        # Atribuir ranks
        for i, opp in enumerate(opportunities, 1):
            opp.rank = i

        return opportunities

    def _scan_nci(self, min_score: int, direction_filter: str) -> list:
        """Corre NCI analyzer em todos os activos activos."""
        try:
            from engine.nci_analyzer import NCIAnalyzer
            analyzer = NCIAnalyzer(self.feed)
        except Exception as e:
            logger.error("NCI analyzer indisponível: " + str(e))
            return []

        opportunities = []

        for ticker, (name, asset_class) in self.NCI_ACTIVE.items():
            try:
                sig = analyzer.analyze(ticker)

                if sig.direction == "NONE":
                    continue
                if sig.confluence_score < min_score:
                    continue
                if direction_filter != "ALL" and sig.direction != direction_filter:
                    continue

                opp = Opportunity(
                    rank=0,
                    ticker=ticker,
                    name=name,
                    asset_class=asset_class,
                    strategy="NCI",
                    direction=sig.direction,
                    score=sig.confluence_score,
                    quality=sig.setup_quality,
                    entry_price=sig.entry_price,
                    stop_loss=sig.stop_loss,
                    target_1=sig.target_1,
                    risk_reward=sig.risk_reward,
                    setup_active=sig.setup_active,
                    setup_desc=sig.setup_description,
                    alerts=sig.alerts[:4],
                )
                opportunities.append(opp)

            except Exception as e:
                logger.warning("Erro NCI " + ticker + ": " + str(e))

        return opportunities

    def _scan_ep(self) -> list:
        """Corre EP scanner em stocks do universo principal."""
        try:
            from engine.scanner import Scanner
            from engine.strategies.ep_strategy import EpisodicPivotStrategy
            from universes import MAIN_UNIVERSE

            strategy = EpisodicPivotStrategy()
            scanner  = Scanner(self.feed, strategy)
            result   = scanner.run(MAIN_UNIVERSE[:30], lookback_days=30)

            opportunities = []
            for candidate in result.top(5):
                opp = Opportunity(
                    rank=0,
                    ticker=candidate.ticker,
                    name=candidate.ticker,
                    asset_class="stock",
                    strategy="EP",
                    direction="LONG",
                    score=int(candidate.score),
                    quality="A" if candidate.score >= 70 else "B",
                    entry_price=candidate.current_price,
                    stop_loss=candidate.stop_loss,
                    target_1=candidate.target_1,
                    risk_reward=round(
                        abs(candidate.target_1 - candidate.current_price) /
                        max(abs(candidate.current_price - candidate.stop_loss), 0.01), 2
                    ),
                    setup_active=candidate.entry_window in ("PRIME", "OPEN"),
                    setup_desc="EP Gap " + str(round(candidate.gap_pct, 1)) +
                               "% | Vol " + str(round(candidate.vol_ratio, 1)) + "x",
                    alerts=[candidate.entry_window],
                )
                opportunities.append(opp)

            return opportunities

        except Exception as e:
            logger.warning("EP scanner indisponível: " + str(e))
            return []
