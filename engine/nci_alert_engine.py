"""
Integral Trading — NCI Alert Engine
======================================
Monitoriza activos NCI diariamente e detecta transições de estado.

Transições que geram alertas:
  RANGING → UPTREND/DOWNTREND    → "Tendência formou-se"
  Extendido → Pullback KL        → "Zona de entrada aproxima-se"
  BOS pendente → confirmado      → "SETUP ACTIVO — considerar entrada"
  Score sobe > 20 pts            → "Setup melhorou significativamente"
  Setup activo → score cai       → "Setup deteriorou — aguardar"

Corre via scheduled_scan.py ou manualmente via dashboard.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Caminho para a BD de alertas
_ALERTS_DB = Path(__file__).parent.parent / "data" / "nci_alerts.json"


# ─────────────────────────────────────────────────────────────────────────────
# Estruturas de dados
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NCIAlert:
    alert_id:    str
    ticker:      str
    name:        str
    alert_type:  str       # SETUP_ACTIVE / PULLBACK_ZONE / TREND_FORMED /
                           # SCORE_IMPROVED / SETUP_LOST / BOS_CONFIRMED
    priority:    str       # HIGH / MEDIUM / LOW
    message:     str
    score:       int
    direction:   str
    entry_price: float
    stop_loss:   float
    target_1:    float
    risk_reward: float
    timestamp:   str
    seen:        bool = False

    @property
    def priority_icon(self) -> str:
        return {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵"}.get(self.priority, "⚪")

    @property
    def type_icon(self) -> str:
        icons = {
            "SETUP_ACTIVE":   "✅",
            "BOS_CONFIRMED":  "🎯",
            "PULLBACK_ZONE":  "📍",
            "TREND_FORMED":   "📈",
            "SCORE_IMPROVED": "⬆️",
            "SETUP_LOST":     "⚠️",
        }
        return icons.get(self.alert_type, "📢")

    def to_dict(self) -> dict:
        return {
            "alert_id":    self.alert_id,
            "ticker":      self.ticker,
            "name":        self.name,
            "alert_type":  self.alert_type,
            "priority":    self.priority,
            "message":     self.message,
            "score":       self.score,
            "direction":   self.direction,
            "entry_price": round(self.entry_price, 4),
            "stop_loss":   round(self.stop_loss, 4),
            "target_1":    round(self.target_1, 4),
            "risk_reward": round(self.risk_reward, 2),
            "timestamp":   self.timestamp,
            "seen":        self.seen,
            "priority_icon": self.priority_icon,
            "type_icon":   self.type_icon,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Alert Engine
# ─────────────────────────────────────────────────────────────────────────────

class NCIAlertEngine:
    """
    Compara estado NCI actual com estado anterior.
    Gera alertas quando detecta transições relevantes.
    """

    # Activos monitorizados com parâmetros específicos
    WATCHLIST = {
        "GC=F":     {"name": "Ouro",          "min_pullback_pct": 2.0, "direction": "LONG"},
        "SI=F":     {"name": "Prata",          "min_pullback_pct": 2.5, "direction": "ALL"},
        "CL=F":     {"name": "Petróleo WTI",   "min_pullback_pct": 2.0, "direction": "LONG"},
        "BZ=F":     {"name": "Petróleo Brent", "min_pullback_pct": 2.0, "direction": "LONG"},
        "NG=F":     {"name": "Gás Natural",    "min_pullback_pct": 3.0, "direction": "ALL"},
        "ZC=F":     {"name": "Milho",          "min_pullback_pct": 2.0, "direction": "LONG"},
        "CT=F":     {"name": "Algodão",        "min_pullback_pct": 2.5, "direction": "LONG"},
        "ZS=F":     {"name": "Soja",           "min_pullback_pct": 2.0, "direction": "LONG"},
        "EURUSD=X": {"name": "EUR/USD",        "min_pullback_pct": 0.8, "direction": "ALL"},
        "GBPUSD=X": {"name": "GBP/USD",        "min_pullback_pct": 0.8, "direction": "ALL"},
        "AUDJPY=X": {"name": "AUD/JPY",        "min_pullback_pct": 1.0, "direction": "ALL"},
    }

    def __init__(self, feed):
        self.feed = feed
        self._alerts_db = _ALERTS_DB
        self._state_db  = _ALERTS_DB.parent / "nci_state.json"
        self._alerts_db.parent.mkdir(exist_ok=True)

    def run(self) -> list:
        """
        Corre análise em todos os activos da watchlist.
        Retorna lista de novos alertas gerados.
        """
        from engine.nci_analyzer import NCIAnalyzer
        analyzer = NCIAnalyzer(self.feed)

        previous_states = self._load_states()
        new_alerts      = []
        current_states  = {}

        for ticker, cfg in self.WATCHLIST.items():
            try:
                sig = analyzer.analyze(ticker)
                current_state = self._build_state(ticker, sig)
                current_states[ticker] = current_state

                prev_state = previous_states.get(ticker, {})
                alerts     = self._detect_transitions(ticker, cfg, current_state, prev_state)
                new_alerts.extend(alerts)

                if alerts:
                    logger.info(ticker + ": " + str(len(alerts)) + " alerta(s) gerado(s)")

            except Exception as e:
                logger.error("Erro AlertEngine " + ticker + ": " + str(e))

        # Guardar estados actuais
        self._save_states(current_states)

        # Persistir novos alertas
        if new_alerts:
            self._save_alerts(new_alerts)

        return new_alerts

    def get_alerts(self, unseen_only: bool = False,
                   days: int = 7) -> list:
        """Retorna alertas recentes da BD."""
        all_alerts = self._load_alerts()
        cutoff     = datetime.utcnow().timestamp() - days * 86400

        filtered = []
        for a in all_alerts:
            try:
                ts = datetime.fromisoformat(a["timestamp"]).timestamp()
                if ts < cutoff:
                    continue
                if unseen_only and a.get("seen", False):
                    continue
                filtered.append(a)
            except Exception:
                continue

        return sorted(filtered, key=lambda x: x["timestamp"], reverse=True)

    def mark_seen(self, alert_id: str):
        """Marca um alerta como visto."""
        alerts = self._load_alerts()
        for a in alerts:
            if a["alert_id"] == alert_id:
                a["seen"] = True
        self._persist_alerts(alerts)

    def mark_all_seen(self):
        """Marca todos os alertas como vistos."""
        alerts = self._load_alerts()
        for a in alerts:
            a["seen"] = True
        self._persist_alerts(alerts)

    def get_ticker_state(self, ticker: str) -> dict:
        """Estado actual de um ticker específico."""
        states = self._load_states()
        return states.get(ticker, {})

    def get_all_states(self) -> dict:
        """Estado actual de todos os activos monitorizados."""
        return self._load_states()

    # ── Detecção de transições ────────────────────────────────────────────────

    def _detect_transitions(self, ticker: str, cfg: dict,
                             current: dict, previous: dict) -> list:
        alerts = []
        name   = cfg["name"]
        now    = datetime.utcnow().isoformat()

        # Sem estado anterior — primeiro scan, não gera alertas
        if not previous:
            return alerts

        prev_trend    = previous.get("daily_trend", "RANGING")
        curr_trend    = current.get("daily_trend", "RANGING")
        prev_score    = previous.get("score", 0)
        curr_score    = current.get("score", 0)
        prev_active   = previous.get("setup_active", False)
        curr_active   = current.get("setup_active", False)
        prev_bos      = previous.get("bos_confirmed", False)
        curr_bos      = current.get("bos_confirmed", False)
        prev_pullback = previous.get("in_pullback_zone", False)
        curr_pullback = current.get("in_pullback_zone", False)
        direction     = current.get("direction", "NONE")

        # Filtrar direcção não desejada
        desired_dir = cfg.get("direction", "ALL")
        if desired_dir != "ALL" and direction != desired_dir and direction != "NONE":
            return alerts

        # ── 1. SETUP ACTIVO — máxima prioridade ──────────────────────────────
        if curr_active and not prev_active:
            alerts.append(NCIAlert(
                alert_id    = ticker + "_ACTIVE_" + date.today().isoformat(),
                ticker      = ticker,
                name        = name,
                alert_type  = "SETUP_ACTIVE",
                priority    = "HIGH",
                message     = (name + " — SETUP ACTIVO " + direction +
                               "\nScore " + str(curr_score) + "/100" +
                               " | Entry $" + str(round(current.get("entry_price", 0), 4)) +
                               " | Stop $" + str(round(current.get("stop_loss", 0), 4)) +
                               " | R:R " + str(round(current.get("risk_reward", 0), 1))),
                score       = curr_score,
                direction   = direction,
                entry_price = current.get("entry_price", 0),
                stop_loss   = current.get("stop_loss", 0),
                target_1    = current.get("target_1", 0),
                risk_reward = current.get("risk_reward", 0),
                timestamp   = now,
            ))

        # ── 2. BOS CONFIRMADO (sem setup activo ainda) ────────────────────────
        elif curr_bos and not prev_bos and not curr_active:
            alerts.append(NCIAlert(
                alert_id    = ticker + "_BOS_" + date.today().isoformat(),
                ticker      = ticker,
                name        = name,
                alert_type  = "BOS_CONFIRMED",
                priority    = "HIGH",
                message     = (name + " — BOS confirmado " + direction +
                               "\nScore " + str(curr_score) + "/100" +
                               " | Verificar entrada"),
                score       = curr_score,
                direction   = direction,
                entry_price = current.get("entry_price", 0),
                stop_loss   = current.get("stop_loss", 0),
                target_1    = current.get("target_1", 0),
                risk_reward = current.get("risk_reward", 0),
                timestamp   = now,
            ))

        # ── 3. PULLBACK À ZONA KL ─────────────────────────────────────────────
        if curr_pullback and not prev_pullback and not curr_active:
            alerts.append(NCIAlert(
                alert_id    = ticker + "_PULLBACK_" + date.today().isoformat(),
                ticker      = ticker,
                name        = name,
                alert_type  = "PULLBACK_ZONE",
                priority    = "MEDIUM",
                message     = (name + " — Entrou na zona KL " + direction +
                               "\nPreço perto do Key Level — aguardar BOS" +
                               "\nScore " + str(curr_score) + "/100"),
                score       = curr_score,
                direction   = direction,
                entry_price = current.get("entry_price", 0),
                stop_loss   = current.get("stop_loss", 0),
                target_1    = current.get("target_1", 0),
                risk_reward = current.get("risk_reward", 0),
                timestamp   = now,
            ))

        # ── 4. TENDÊNCIA FORMOU-SE ────────────────────────────────────────────
        if prev_trend == "RANGING" and curr_trend in ("UPTREND", "DOWNTREND"):
            alerts.append(NCIAlert(
                alert_id    = ticker + "_TREND_" + date.today().isoformat(),
                ticker      = ticker,
                name        = name,
                alert_type  = "TREND_FORMED",
                priority    = "MEDIUM",
                message     = (name + " — Tendência formou-se: " + curr_trend +
                               "\nAguardar pullback ao KL para entrada"),
                score       = curr_score,
                direction   = direction,
                entry_price = current.get("entry_price", 0),
                stop_loss   = current.get("stop_loss", 0),
                target_1    = current.get("target_1", 0),
                risk_reward = current.get("risk_reward", 0),
                timestamp   = now,
            ))

        # ── 5. SCORE MELHOROU SIGNIFICATIVAMENTE ──────────────────────────────
        if curr_score - prev_score >= 20 and curr_score >= 50 and not curr_active:
            alerts.append(NCIAlert(
                alert_id    = ticker + "_SCORE_" + date.today().isoformat(),
                ticker      = ticker,
                name        = name,
                alert_type  = "SCORE_IMPROVED",
                priority    = "MEDIUM",
                message     = (name + " — Score subiu " +
                               str(prev_score) + " → " + str(curr_score) +
                               "\nSetup a melhorar — monitorizar"),
                score       = curr_score,
                direction   = direction,
                entry_price = current.get("entry_price", 0),
                stop_loss   = current.get("stop_loss", 0),
                target_1    = current.get("target_1", 0),
                risk_reward = current.get("risk_reward", 0),
                timestamp   = now,
            ))

        # ── 6. SETUP PERDEU-SE ────────────────────────────────────────────────
        if prev_active and not curr_active:
            alerts.append(NCIAlert(
                alert_id    = ticker + "_LOST_" + date.today().isoformat(),
                ticker      = ticker,
                name        = name,
                alert_type  = "SETUP_LOST",
                priority    = "LOW",
                message     = (name + " — Setup deixou de estar activo" +
                               "\nScore: " + str(curr_score) + "/100 — aguardar nova oportunidade"),
                score       = curr_score,
                direction   = direction,
                entry_price = current.get("entry_price", 0),
                stop_loss   = current.get("stop_loss", 0),
                target_1    = current.get("target_1", 0),
                risk_reward = current.get("risk_reward", 0),
                timestamp   = now,
            ))

        return alerts

    # ── Estado ────────────────────────────────────────────────────────────────

    def _build_state(self, ticker: str, sig) -> dict:
        """Constrói o estado actual de um ticker a partir do NCISignal."""
        # Verificar se está em pullback zone (≤ pullback_zone_pct do KL)
        kl_price    = sig.h4.key_level.price if sig.h4 and sig.h4.key_level else 0
        price       = sig.entry_price or 0
        in_pullback = False

        if kl_price > 0 and price > 0:
            dist_pct = abs(price - kl_price) / price * 100
            cfg      = self.WATCHLIST.get(ticker, {})
            threshold = cfg.get("min_pullback_pct", 2.0)
            in_pullback = dist_pct <= threshold

        bos = (
            (sig.h1.bos_confirmed if sig.h1 else False) or
            (sig.h4.bos_confirmed if sig.h4 else False)
        )

        return {
            "ticker":          ticker,
            "daily_trend":     sig.daily.trend if sig.daily else "RANGING",
            "h4_trend":        sig.h4.trend if sig.h4 else "RANGING",
            "h1_trend":        sig.h1.trend if sig.h1 else "RANGING",
            "direction":       sig.direction,
            "score":           sig.confluence_score,
            "quality":         sig.setup_quality,
            "setup_active":    sig.setup_active,
            "bos_confirmed":   bos,
            "in_pullback_zone": in_pullback,
            "entry_price":     sig.entry_price,
            "stop_loss":       sig.stop_loss,
            "target_1":        sig.target_1,
            "risk_reward":     sig.risk_reward,
            "kl_price":        kl_price,
            "scanned_at":      datetime.utcnow().isoformat(),
        }

    # ── Persistência ──────────────────────────────────────────────────────────

    def _load_states(self) -> dict:
        try:
            if self._state_db.exists():
                return json.loads(self._state_db.read_text())
        except Exception:
            pass
        return {}

    def _save_states(self, states: dict):
        try:
            self._state_db.write_text(json.dumps(states, indent=2))
        except Exception as e:
            logger.error("Erro ao guardar estados: " + str(e))

    def _load_alerts(self) -> list:
        try:
            if self._alerts_db.exists():
                return json.loads(self._alerts_db.read_text())
        except Exception:
            pass
        return []

    def _save_alerts(self, new_alerts: list):
        existing = self._load_alerts()
        # Evitar duplicados (mesmo alert_id)
        existing_ids = {a["alert_id"] for a in existing}
        for alert in new_alerts:
            d = alert.to_dict()
            if d["alert_id"] not in existing_ids:
                existing.append(d)
                existing_ids.add(d["alert_id"])
        self._persist_alerts(existing)

    def _persist_alerts(self, alerts: list):
        try:
            # Manter só os últimos 500 alertas
            alerts = alerts[-500:]
            self._alerts_db.write_text(json.dumps(alerts, indent=2))
        except Exception as e:
            logger.error("Erro ao persistir alertas: " + str(e))
