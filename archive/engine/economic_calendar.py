"""
Integral Trading — Economic Calendar
=======================================
Integra calendário económico com análise NCI.

Fontes: Finnhub API (free tier)
Lógica: cada evento é mapeado para activos afectados e direcção provável.

Três zonas de risco:
  PRÉ-EVENTO   (24-48h antes) → avisar, reduzir confiança
  JANELA       (2h antes / 4h depois) → bloquear entradas novas
  PÓS-EVENTO   (4-24h depois) → re-avaliar com novo contexto
"""

import json
import logging
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).parent.parent / "data" / "calendar_cache.json"
_CACHE_TTL_HOURS = 4   # re-busca após 4h


# ─────────────────────────────────────────────────────────────────────────────
# Mapa de relações: evento → activos afectados + direcção
# ─────────────────────────────────────────────────────────────────────────────

# Estrutura: keyword → {activos: {ticker: {bullish_if, bearish_if, strength}}}
# strength: 1-3 (1=indirecto, 2=relevante, 3=determinante)

EVENT_ASSET_MAP = {

    # ── Federal Reserve ───────────────────────────────────────────────────────
    "fed": {
        "assets": {
            "GC=F":     {"bullish_if": "dovish",  "bearish_if": "hawkish", "strength": 3},
            "SI=F":     {"bullish_if": "dovish",  "bearish_if": "hawkish", "strength": 2},
            "EURUSD=X": {"bullish_if": "dovish",  "bearish_if": "hawkish", "strength": 3},
            "GBPUSD=X": {"bullish_if": "dovish",  "bearish_if": "hawkish", "strength": 2},
            "USDJPY=X": {"bullish_if": "hawkish", "bearish_if": "dovish",  "strength": 3},
            "AUDUSD=X": {"bullish_if": "dovish",  "bearish_if": "hawkish", "strength": 2},
            "CL=F":     {"bullish_if": "dovish",  "bearish_if": "hawkish", "strength": 2},
        },
        "keywords": ["federal reserve", "fed rate", "fomc", "powell",
                     "federal funds", "interest rate decision"],
        "block_window_hours": 4,
        "pre_event_hours": 48,
    },

    # ── BCE / ECB ─────────────────────────────────────────────────────────────
    "ecb": {
        "assets": {
            "EURUSD=X": {"bullish_if": "hawkish", "bearish_if": "dovish", "strength": 3},
            "EURJPY=X": {"bullish_if": "hawkish", "bearish_if": "dovish", "strength": 3},
            "GBPUSD=X": {"bullish_if": None,       "bearish_if": None,    "strength": 1},
        },
        "keywords": ["ecb", "european central bank", "bce", "lagarde",
                     "euro rate", "eurozone rate"],
        "block_window_hours": 4,
        "pre_event_hours": 48,
    },

    # ── NFP / Emprego EUA ─────────────────────────────────────────────────────
    "nfp": {
        "assets": {
            "EURUSD=X": {"bullish_if": "weak",    "bearish_if": "strong", "strength": 3},
            "GBPUSD=X": {"bullish_if": "weak",    "bearish_if": "strong", "strength": 2},
            "USDJPY=X": {"bullish_if": "strong",  "bearish_if": "weak",   "strength": 3},
            "AUDUSD=X": {"bullish_if": "weak",    "bearish_if": "strong", "strength": 2},
            "GC=F":     {"bullish_if": "weak",    "bearish_if": "strong", "strength": 2},
        },
        "keywords": ["nonfarm", "non-farm", "nfp", "payroll", "employment",
                     "jobs report", "unemployment"],
        "block_window_hours": 4,
        "pre_event_hours": 24,
    },

    # ── CPI / Inflação ────────────────────────────────────────────────────────
    "cpi": {
        "assets": {
            "GC=F":     {"bullish_if": "high",  "bearish_if": "low",   "strength": 3},
            "SI=F":     {"bullish_if": "high",  "bearish_if": "low",   "strength": 2},
            "EURUSD=X": {"bullish_if": None,    "bearish_if": None,    "strength": 2},
            "CL=F":     {"bullish_if": "high",  "bearish_if": "low",   "strength": 2},
        },
        "keywords": ["cpi", "consumer price", "inflation", "pce", "core inflation"],
        "block_window_hours": 2,
        "pre_event_hours": 24,
    },

    # ── PMI Zona Euro ─────────────────────────────────────────────────────────
    "pmi_euro": {
        "assets": {
            "EURUSD=X": {"bullish_if": "above_50", "bearish_if": "below_50", "strength": 3},
            "EURJPY=X": {"bullish_if": "above_50", "bearish_if": "below_50", "strength": 2},
            "GBPUSD=X": {"bullish_if": None,        "bearish_if": None,      "strength": 1},
        },
        "keywords": ["euro pmi", "eurozone pmi", "manufacturing pmi europe",
                     "services pmi europe", "composite pmi euro",
                     "pmi zona euro", "s&p global pmi"],
        "block_window_hours": 2,
        "pre_event_hours": 24,
    },

    # ── PMI EUA ───────────────────────────────────────────────────────────────
    "pmi_usa": {
        "assets": {
            "EURUSD=X": {"bullish_if": "below_50", "bearish_if": "above_50", "strength": 2},
            "GC=F":     {"bullish_if": "below_50", "bearish_if": "above_50", "strength": 1},
            "CL=F":     {"bullish_if": "above_50", "bearish_if": "below_50", "strength": 2},
        },
        "keywords": ["ism manufacturing", "ism services", "us pmi",
                     "s&p global us", "chicago pmi"],
        "block_window_hours": 2,
        "pre_event_hours": 24,
    },

    # ── PMI China ─────────────────────────────────────────────────────────────
    "pmi_china": {
        "assets": {
            "HG=F":     {"bullish_if": "above_50", "bearish_if": "below_50", "strength": 3},
            "CL=F":     {"bullish_if": "above_50", "bearish_if": "below_50", "strength": 2},
            "AUDUSD=X": {"bullish_if": "above_50", "bearish_if": "below_50", "strength": 3},
        },
        "keywords": ["china pmi", "caixin", "nbs manufacturing",
                     "china manufacturing", "china services"],
        "block_window_hours": 2,
        "pre_event_hours": 24,
    },

    # ── OPEC ──────────────────────────────────────────────────────────────────
    "opec": {
        "assets": {
            "CL=F":  {"bullish_if": "cut",    "bearish_if": "increase", "strength": 3},
            "BZ=F":  {"bullish_if": "cut",    "bearish_if": "increase", "strength": 3},
            "GC=F":  {"bullish_if": "cut",    "bearish_if": "increase", "strength": 1},
        },
        "keywords": ["opec", "opec+", "oil production", "crude output"],
        "block_window_hours": 6,
        "pre_event_hours": 48,
    },

    # ── Inventários petróleo (EIA) ────────────────────────────────────────────
    "eia_oil": {
        "assets": {
            "CL=F": {"bullish_if": "draw",  "bearish_if": "build", "strength": 3},
            "BZ=F": {"bullish_if": "draw",  "bearish_if": "build", "strength": 2},
        },
        "keywords": ["eia", "crude inventories", "oil inventories",
                     "petroleum status", "crude stocks"],
        "block_window_hours": 2,
        "pre_event_hours": 12,
    },

    # ── GDP ───────────────────────────────────────────────────────────────────
    "gdp": {
        "assets": {
            "EURUSD=X": {"bullish_if": "beat",  "bearish_if": "miss", "strength": 2},
            "GBPUSD=X": {"bullish_if": "beat",  "bearish_if": "miss", "strength": 2},
            "GC=F":     {"bullish_if": "miss",  "bearish_if": "beat", "strength": 1},
        },
        "keywords": ["gdp", "gross domestic product", "economic growth",
                     "quarterly growth"],
        "block_window_hours": 2,
        "pre_event_hours": 24,
    },

    # ── Banco de Inglaterra ───────────────────────────────────────────────────
    "boe": {
        "assets": {
            "GBPUSD=X": {"bullish_if": "hawkish", "bearish_if": "dovish", "strength": 3},
            "EURJPY=X": {"bullish_if": None,       "bearish_if": None,    "strength": 1},
        },
        "keywords": ["bank of england", "boe", "bailey", "uk rate",
                     "mpc decision", "monetary policy committee"],
        "block_window_hours": 4,
        "pre_event_hours": 48,
    },
}

# Impacto por tipo de evento (para eventos não mapeados explicitamente)
IMPACT_LEVELS = {
    3: "HIGH",    # determinante
    2: "MEDIUM",  # relevante
    1: "LOW",     # indirecto
    0: "NONE",
}


# ─────────────────────────────────────────────────────────────────────────────
# Estrutura de dados
# ─────────────────────────────────────────────────────────────────────────────

class EconomicEvent:
    def __init__(self, data: dict):
        self.event_id   = str(data.get("id", ""))
        self.name       = data.get("event", "") or data.get("name", "")
        self.country    = data.get("country", "")
        self.impact     = data.get("impact", "low").upper()   # HIGH/MEDIUM/LOW
        self.time_str   = data.get("time", "") or data.get("datetime", "")
        self.actual     = data.get("actual")
        self.estimate   = data.get("estimate")
        self.previous   = data.get("prev")
        self._matched_type = None
        self._matched_assets = {}

        # Parse datetime
        try:
            if "T" in self.time_str:
                self.dt = datetime.fromisoformat(
                    self.time_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            else:
                self.dt = datetime.strptime(self.time_str[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            self.dt = datetime.utcnow()

    @property
    def hours_until(self) -> float:
        return (self.dt - datetime.utcnow()).total_seconds() / 3600

    @property
    def hours_since(self) -> float:
        return (datetime.utcnow() - self.dt).total_seconds() / 3600

    @property
    def is_future(self) -> bool:
        return self.dt > datetime.utcnow()

    @property
    def is_high_impact(self) -> bool:
        return self.impact == "HIGH" or self.impact == "3"

    def to_dict(self) -> dict:
        return {
            "event_id":  self.event_id,
            "name":      self.name,
            "country":   self.country,
            "impact":    self.impact,
            "datetime":  self.dt.isoformat(),
            "hours_until": round(self.hours_until, 1),
            "actual":    self.actual,
            "estimate":  self.estimate,
            "previous":  self.previous,
        }


class AssetEventRisk:
    """Risco fundamental de um activo baseado nos eventos próximos."""

    def __init__(self, ticker: str):
        self.ticker        = ticker
        self.risk_level    = "NONE"   # HIGH / MEDIUM / LOW / NONE
        self.in_block_zone = False    # True = bloquear entrada
        self.events        = []       # eventos relevantes
        self.context_text  = ""       # texto para prompt do Claude
        self.direction_bias = None    # BULLISH / BEARISH / UNCERTAIN / None

    def to_dict(self) -> dict:
        return {
            "ticker":        self.ticker,
            "risk_level":    self.risk_level,
            "in_block_zone": self.in_block_zone,
            "direction_bias": self.direction_bias,
            "context_text":  self.context_text,
            "events":        [e.to_dict() for e in self.events],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Economic Calendar
# ─────────────────────────────────────────────────────────────────────────────

class EconomicCalendar:
    """
    Integra calendário económico com análise NCI.
    Determina o risco fundamental de cada activo baseado em eventos próximos.
    """

    def __init__(self, finnhub_key: str = ""):
        self.key = finnhub_key
        _CACHE_PATH.parent.mkdir(exist_ok=True)

    # ── API pública ───────────────────────────────────────────────────────────

    def get_asset_risk(self, ticker: str,
                       hours_ahead: int = 48) -> AssetEventRisk:
        """
        Avalia o risco fundamental para um activo.
        Retorna AssetEventRisk com nível de risco e contexto.
        """
        risk = AssetEventRisk(ticker)
        events = self._get_events(hours_ahead=hours_ahead)

        if not events:
            return risk

        relevant = self._filter_for_asset(ticker, events, hours_ahead)

        if not relevant:
            return risk

        risk.events = [item[0] for item in relevant]

        # Determinar nível de risco e zona de bloqueio
        max_strength = 0
        in_block     = False
        biases       = []
        context_parts = []

        for event, event_cfg, asset_cfg in relevant:
            strength = asset_cfg.get("strength", 1)
            max_strength = max(max_strength, strength)

            block_hours = event_cfg.get("block_window_hours", 2)
            if -block_hours <= event.hours_until <= block_hours:
                in_block = True

            # Bias
            bullish_if = asset_cfg.get("bullish_if")
            bearish_if = asset_cfg.get("bearish_if")
            if bullish_if or bearish_if:
                biases.append((bullish_if, bearish_if, strength))

            # Contexto
            timing = ""
            if event.is_future:
                h = event.hours_until
                if h < 2:
                    timing = "em menos de 2 horas"
                elif h < 24:
                    timing = "em " + str(int(h)) + "h"
                else:
                    timing = "em " + str(int(h/24)) + " dia(s)"
            else:
                timing = "há " + str(int(abs(event.hours_since))) + "h"

            impact_str = " [CRÍTICO]" if event.is_high_impact else ""
            context_parts.append(
                "- " + event.name + " (" + event.country + ")" +
                impact_str + " — " + timing
            )

        # Nível de risco global
        risk.risk_level    = IMPACT_LEVELS.get(max_strength, "NONE")
        risk.in_block_zone = in_block

        # Bias de direcção
        if biases:
            high_strength_biases = [(b, br) for b, br, s in biases if s >= 2]
            if high_strength_biases:
                risk.direction_bias = "UNCERTAIN"

        # Texto de contexto para o prompt
        if context_parts:
            risk.context_text = (
                "Eventos económicos relevantes para " + ticker + ":\n" +
                "\n".join(context_parts) +
                ("\n⚠️ ZONA DE BLOQUEIO — evento a decorrer" if in_block else "")
            )

        return risk

    def get_upcoming_events(self, hours_ahead: int = 48,
                             impact_filter: str = "HIGH") -> list:
        """
        Retorna todos os eventos próximos com o impacto especificado.
        Útil para o Briefing diário.
        """
        events = self._get_events(hours_ahead=hours_ahead)
        if impact_filter == "HIGH":
            return [e for e in events
                    if e.impact in ("HIGH", "3") and e.is_future]
        elif impact_filter == "MEDIUM":
            return [e for e in events
                    if e.impact in ("HIGH", "MEDIUM", "2", "3") and e.is_future]
        return [e for e in events if e.is_future]

    def get_calendar_summary(self, hours_ahead: int = 48) -> str:
        """
        Resumo do calendário para o próximo período.
        Usado no Briefing e nos prompts do Claude.
        """
        events = self.get_upcoming_events(hours_ahead, impact_filter="MEDIUM")
        if not events:
            return "Sem eventos económicos HIGH/MEDIUM impact nas próximas " + str(hours_ahead) + "h."

        lines = ["Calendário económico (próximas " + str(hours_ahead) + "h):"]
        for e in events[:8]:
            h = e.hours_until
            timing = str(int(h)) + "h" if h < 48 else str(int(h/24)) + "d"
            icon = "🔴" if e.is_high_impact else "🟡"
            lines.append(
                "  " + icon + " " + timing + " — " + e.name +
                " (" + e.country + ")"
            )
        return "\n".join(lines)

    # ── Fetch e cache ─────────────────────────────────────────────────────────

    def _get_events(self, hours_ahead: int = 72) -> list:
        """Busca eventos do Finnhub com cache."""
        # Verificar cache
        cached = self._load_cache()
        if cached:
            return [EconomicEvent(e) for e in cached]

        # Fetch da API
        if not self.key:
            logger.warning("Finnhub key não configurada — calendário indisponível")
            return []

        events = self._fetch_finnhub(hours_ahead)
        if events:
            self._save_cache([e.to_dict() for e in events])
        return events

    def _fetch_finnhub(self, hours_ahead: int) -> list:
        """Fetch do calendário económico via Finnhub."""
        try:
            now   = datetime.utcnow()
            start = now.strftime("%Y-%m-%d")
            end   = (now + timedelta(hours=hours_ahead + 24)).strftime("%Y-%m-%d")

            url = "https://finnhub.io/api/v1/calendar/economic"
            resp = requests.get(url, params={
                "token": self.key,
                "from":  start,
                "to":    end,
            }, timeout=10)
            resp.raise_for_status()
            data   = resp.json()
            events_raw = data.get("economicCalendar", [])

            events = []
            for raw in events_raw:
                try:
                    # Normalizar formato Finnhub
                    normalized = {
                        "id":       str(raw.get("id", "")),
                        "event":    raw.get("event", ""),
                        "country":  raw.get("country", ""),
                        "impact":   self._normalize_impact(raw.get("impact", "")),
                        "time":     raw.get("time", ""),
                        "actual":   raw.get("actual"),
                        "estimate": raw.get("estimate"),
                        "prev":     raw.get("prev"),
                    }
                    e = EconomicEvent(normalized)
                    # Só incluir eventos HIGH e MEDIUM impact
                    if e.impact in ("HIGH", "MEDIUM"):
                        events.append(e)
                except Exception:
                    continue

            logger.info("Finnhub: " + str(len(events)) + " eventos carregados")
            return events

        except Exception as ex:
            logger.error("Erro Finnhub: " + str(ex))
            return []

    def _normalize_impact(self, impact_raw) -> str:
        """Normaliza o campo impact do Finnhub."""
        if impact_raw is None:
            return "LOW"
        s = str(impact_raw).upper().strip()
        if s in ("HIGH", "3", "MAJOR"):
            return "HIGH"
        if s in ("MEDIUM", "2", "MODERATE"):
            return "MEDIUM"
        return "LOW"

    # ── Matching evento → activo ──────────────────────────────────────────────

    def _filter_for_asset(self, ticker: str, events: list,
                           hours_ahead: int) -> list:
        """
        Filtra eventos relevantes para um activo específico.
        Retorna lista de (event, event_cfg, asset_cfg).
        """
        relevant = []

        for event in events:
            # Só eventos nas próximas hours_ahead horas ou nas últimas 24h
            if event.hours_until > hours_ahead:
                continue
            if not event.is_future and event.hours_since > 24:
                continue

            # Encontrar o tipo de evento por keywords
            event_type, event_cfg = self._match_event_type(event)
            if not event_type:
                continue

            # Verificar se o ticker é afectado
            asset_map = event_cfg.get("assets", {})
            if ticker not in asset_map:
                continue

            asset_cfg = asset_map[ticker]

            # Só incluir se strength >= 2 ou evento HIGH IMPACT
            if asset_cfg.get("strength", 0) < 2 and not event.is_high_impact:
                continue

            relevant.append((event, event_cfg, asset_cfg))

        # Ordenar por proximidade temporal
        relevant.sort(key=lambda x: abs(x[0].hours_until))
        return relevant

    def _match_event_type(self, event: EconomicEvent) -> tuple:
        """Encontra o tipo de evento por keywords."""
        name_lower = event.name.lower()
        country    = event.country.lower()

        # Países relevantes para o sistema
        relevant_countries = {"us", "eu", "gb", "au", "nz", "ca", "jp", "cn", "ch", "de", "fr", "es", "it"}
        if country and country not in relevant_countries:
            return None, {}

        for event_type, cfg in EVENT_ASSET_MAP.items():
            for kw in cfg.get("keywords", []):
                if kw in name_lower:
                    # Refinamento por país para PMI
                    if event_type == "pmi_euro" and country not in ("eu", "de", "fr", "es", "it", "pt"):
                        continue
                    if event_type == "pmi_usa" and country not in ("us", "usa"):
                        continue
                    if event_type == "pmi_china" and country not in ("cn", "china"):
                        continue
                    return event_type, cfg

        return None, {}

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _load_cache(self) -> Optional[list]:
        try:
            if not _CACHE_PATH.exists():
                return None
            data = json.loads(_CACHE_PATH.read_text())
            cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
            if (datetime.utcnow() - cached_at).total_seconds() > _CACHE_TTL_HOURS * 3600:
                return None
            return data.get("events", [])
        except Exception:
            return None

    def _save_cache(self, events: list):
        try:
            _CACHE_PATH.write_text(json.dumps({
                "cached_at": datetime.utcnow().isoformat(),
                "events":    events,
            }, indent=2))
        except Exception as e:
            logger.error("Erro cache calendário: " + str(e))
