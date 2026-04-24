"""
Integral Trading — Decision Engine v2
=======================================
Avalia candidatos EP com análise qualitativa do catalisador.

Pipeline de decisão:
1. Filtros rápidos (sem API) — score, janela, posição existente
2. Análise qualitativa do catalisador (web search)
3. Avaliação final pelo especialista EP
4. Decisão: ENTER / WATCH / SKIP com raciocínio completo
"""

import json
import logging
import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config import ANTHROPIC_API_KEY
from engine.database import get_conn, init_db

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"


@dataclass
class Decision:
    ticker:          str
    scan_date:       str
    action:          str
    confidence:      float
    reasoning:       str
    entry_price:     float
    stop_loss:       float
    target_1:        float
    target_2:        float
    risk_pct:        float
    reward_pct:      float
    risk_reward:     float
    catalyst_type:   str = ""
    catalyst_summary: str = ""
    catalyst_quality: str = ""
    alerts:          list = field(default_factory=list)
    created_at:      str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    @property
    def action_icon(self) -> str:
        return {"ENTER": "🟢", "WATCH": "🟡", "SKIP": "🔴"}.get(self.action, "⚪")

    def to_dict(self) -> dict:
        return {
            "ticker":           self.ticker,
            "scan_date":        self.scan_date,
            "action":           self.action,
            "action_icon":      self.action_icon,
            "confidence":       round(self.confidence, 1),
            "reasoning":        self.reasoning,
            "entry_price":      round(self.entry_price, 2),
            "stop_loss":        round(self.stop_loss, 2),
            "target_1":         round(self.target_1, 2),
            "target_2":         round(self.target_2, 2),
            "risk_pct":         round(self.risk_pct, 2),
            "reward_pct":       round(self.reward_pct, 2),
            "risk_reward":      round(self.risk_reward, 2),
            "catalyst_type":    self.catalyst_type,
            "catalyst_summary": self.catalyst_summary,
            "catalyst_quality": self.catalyst_quality,
            "alerts":           self.alerts,
            "created_at":       self.created_at,
        }


class DecisionEngine:

    MIN_SCORE_ENTER  = 65
    MIN_SCORE_WATCH  = 55
    MIN_CONFIDENCE   = 60
    MIN_CATALYST_SCORE = 50   # score mínimo do catalisador para ENTER

    def __init__(self):
        init_db()
        self._ensure_tables()
        self._sugar_babies = self._load_sugar_babies()

    def evaluate_candidates(self, candidates: list) -> list:
        """Avalia lista de candidatos com análise qualitativa."""
        from engine.catalyst_analyzer import CatalystAnalyzer

        # Analisar catalisadores de candidatos com score suficiente
        eligible = [c for c in candidates if c.score >= self.MIN_SCORE_WATCH]
        skipped  = [c for c in candidates if c.score < self.MIN_SCORE_WATCH]

        # Batch analysis dos catalisadores
        catalyst_analyses = {}
        if eligible and ANTHROPIC_API_KEY:
            logger.info("A analisar catalisadores de " +
                        str(len(eligible)) + " candidatos...")
            analyzer = CatalystAnalyzer()
            catalyst_analyses = analyzer.analyze_batch(eligible)

        decisions = []

        # Avaliar candidatos elegíveis
        for candidate in eligible:
            try:
                catalyst = catalyst_analyses.get(candidate.ticker)
                decision = self._evaluate_one(candidate, catalyst)
                decisions.append(decision)
                self._save_decision(decision)
            except Exception as e:
                logger.error("Erro ao avaliar " + candidate.ticker + ": " + str(e))

        # SKIP automático para candidatos com score baixo
        for candidate in skipped:
            decision = self._quick_skip(
                candidate,
                "Score " + str(round(candidate.score, 0)) +
                " abaixo do mínimo de " + str(self.MIN_SCORE_WATCH)
            )
            decisions.append(decision)
            self._save_decision(decision)

        return sorted(decisions, key=lambda x: x.confidence, reverse=True)

    def evaluate_single(self, candidate) -> Decision:
        from engine.catalyst_analyzer import CatalystAnalyzer
        analyzer = CatalystAnalyzer()
        catalyst = analyzer.analyze(
            ticker=candidate.ticker,
            gap_pct=candidate.gap_pct,
            current_price=candidate.current_price,
        )
        decision = self._evaluate_one(candidate, catalyst)
        self._save_decision(decision)
        return decision

    def get_pending_decisions(self, scan_date: str = None) -> list:
        if not scan_date:
            from datetime import date
            scan_date = date.today().isoformat()
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM decisions
                WHERE scan_date = ?
                  AND action IN ('ENTER', 'WATCH')
                  AND confirmed = 0
                ORDER BY confidence DESC
            """, (scan_date,)).fetchall()
        return [dict(r) for r in rows]

    def confirm_entry(self, decision_id: int) -> bool:
        with get_conn() as conn:
            conn.execute(
                "UPDATE decisions SET confirmed = 1 WHERE id = ?",
                (decision_id,)
            )
        return True

    def reject_decision(self, decision_id: int, reason: str = "") -> bool:
        with get_conn() as conn:
            conn.execute(
                "UPDATE decisions SET confirmed = -1, rejection_reason = ? WHERE id = ?",
                (reason, decision_id)
            )
        return True

    def get_decision_history(self, days: int = 30) -> list:
        from datetime import date, timedelta
        since = (date.today() - timedelta(days=days)).isoformat()
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM decisions
                WHERE scan_date >= ?
                ORDER BY created_at DESC
            """, (since,)).fetchall()
        return [dict(r) for r in rows]

    # ── Avaliação ─────────────────────────────────────────────────────────────

    def _evaluate_one(self, candidate, catalyst=None) -> Decision:
        from datetime import date
        scan_date   = date.today().isoformat()
        entry_price = candidate.current_price
        stop_loss   = candidate.stop_loss
        target_1    = candidate.target_1
        target_2    = candidate.target_2
        risk_pct    = abs(entry_price - stop_loss) / entry_price * 100
        reward_pct  = abs(target_1 - entry_price) / entry_price * 100
        risk_reward = reward_pct / risk_pct if risk_pct > 0 else 0

        alerts = []

        # ── Filtros rápidos ───────────────────────────────────────────────────

        if candidate.entry_window == "LATE":
            return self._quick_skip(
                candidate,
                "Janela LATE — " + str(candidate.days_since_gap) +
                " dias desde o gap. Oportunidade passou.",
                catalyst=catalyst,
            )

        if self._has_open_position(candidate.ticker):
            return self._quick_skip(
                candidate,
                "Já existe posição aberta em " + candidate.ticker,
                catalyst=catalyst,
            )

        if risk_reward < 1.5:
            alerts.append("R/R fraco (" + str(round(risk_reward, 2)) + ")")

        is_sugar_baby = candidate.ticker in self._sugar_babies
        if is_sugar_baby:
            alerts.append("⭐ Sugar Baby")

        # ── Análise do catalisador ────────────────────────────────────────────

        catalyst_type    = ""
        catalyst_summary = ""
        catalyst_quality = ""

        if catalyst:
            catalyst_type    = catalyst.catalyst_type
            catalyst_summary = catalyst.catalyst_summary
            catalyst_quality = catalyst.catalyst_quality

            # Catalisador de baixa qualidade → SKIP directo
            if catalyst.catalyst_quality == "LOW" and catalyst.quality_score < 30:
                return Decision(
                    ticker=candidate.ticker,
                    scan_date=scan_date,
                    action="SKIP",
                    confidence=80.0,
                    reasoning=(
                        "Catalisador de baixa qualidade: " +
                        catalyst.catalyst_summary + "\n\n" +
                        catalyst.reasoning
                    ),
                    entry_price=entry_price, stop_loss=stop_loss,
                    target_1=target_1, target_2=target_2,
                    risk_pct=risk_pct, reward_pct=reward_pct,
                    risk_reward=risk_reward,
                    catalyst_type=catalyst_type,
                    catalyst_summary=catalyst_summary,
                    catalyst_quality=catalyst_quality,
                    alerts=["Catalisador fraco"] + catalyst.red_flags,
                )

            # Adicionar flags do catalisador
            alerts.extend(catalyst.red_flags)
            if catalyst.green_flags:
                alerts.extend(["✅ " + f for f in catalyst.green_flags[:2]])

            # Catalisador já priced in → WATCH
            if catalyst.already_priced_in:
                alerts.append("⚠️ Catalisador pode estar priced in")

        # ── Decisão via especialista ──────────────────────────────────────────
        if not ANTHROPIC_API_KEY:
            action     = "ENTER" if candidate.score >= self.MIN_SCORE_ENTER else "WATCH"
            confidence = min(candidate.score * 0.85, 80.0)
            reasoning  = (
                "Avaliação quantitativa (API indisponível).\n"
                "Score: " + str(round(candidate.score, 0)) + "/100\n"
                "Gap: " + str(round(candidate.gap_pct, 1)) + "%\n"
                "Volume: " + str(round(candidate.vol_ratio, 1)) + "x\n"
                "Catalisador: " + (catalyst_summary or "desconhecido")
            )
        else:
            action, confidence, reasoning = self._ask_specialist(
                candidate, catalyst, is_sugar_baby, alerts
            )

        return Decision(
            ticker=candidate.ticker,
            scan_date=scan_date,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_pct=risk_pct,
            reward_pct=reward_pct,
            risk_reward=risk_reward,
            catalyst_type=catalyst_type,
            catalyst_summary=catalyst_summary,
            catalyst_quality=catalyst_quality,
            alerts=alerts,
        )

    def _ask_specialist(self, candidate, catalyst, is_sugar_baby, alerts) -> tuple:
        """Avaliação final pelo especialista com contexto completo."""

        catalyst_context = ""
        if catalyst:
            catalyst_context = f"""
**Catalisador identificado:**
- Tipo: {catalyst.catalyst_type}
- Resumo: {catalyst.catalyst_summary}
- Qualidade: {catalyst.catalyst_quality} ({round(catalyst.quality_score, 0)}/100)
- Neglect: {'Sim' if catalyst.is_neglected else 'Não'}
- Primeiro surprise: {'Sim' if catalyst.is_first_surprise else 'Não'}
- Sustentável: {'Sim' if catalyst.is_sustainable else 'Não'}
- Priced in: {'Sim' if catalyst.already_priced_in else 'Não'}
- Green flags: {', '.join(catalyst.green_flags) if catalyst.green_flags else 'nenhum'}
- Red flags: {', '.join(catalyst.red_flags) if catalyst.red_flags else 'nenhum'}
- Análise: {catalyst.reasoning}
"""

        ticker_history = self._get_ticker_history(candidate.ticker)

        prompt = f"""Avalia este candidato EP com base em TODOS os dados disponíveis.

## {candidate.ticker}

**Dados técnicos:**
- Score EP: {round(candidate.score, 1)}/100
- Gap: {round(candidate.gap_pct, 1)}%
- Volume: {round(candidate.vol_ratio, 1)}x média
- Preço: ${round(candidate.current_price, 2)}
- Janela: {candidate.entry_window} ({candidate.days_since_gap} dias desde o gap)
- R/R: {round(abs(candidate.target_1 - candidate.current_price) / abs(candidate.current_price - candidate.stop_loss), 2) if abs(candidate.current_price - candidate.stop_loss) > 0 else 0}
- Sugar Baby: {'SIM ⭐' if is_sugar_baby else 'Não'}
- Alertas técnicos: {', '.join(alerts) if alerts else 'nenhum'}
{catalyst_context}
**Histórico:**
{ticker_history}

Decide: ENTER, WATCH ou SKIP?

Responde APENAS em JSON:
{{
  "action": "ENTER" ou "WATCH" ou "SKIP",
  "confidence": 0-100,
  "reasoning": "3-4 frases em português explicando a decisão",
  "key_factor": "o factor mais decisivo"
}}"""

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type":      "application/json",
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model":      CLAUDE_MODEL,
                    "max_tokens": 400,
                    "system":     "És o especialista EP. Respondes APENAS em JSON válido.",
                    "messages":   [{"role": "user", "content": prompt}],
                },
                timeout=20,
            )
            response.raise_for_status()
            data    = response.json()
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")

            content = content.strip()
            if "```" in content:
                for part in content.split("```"):
                    if "{" in part:
                        content = part.replace("json", "").strip()
                        break

            start = content.find("{")
            end   = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = content[start:end]

            result     = json.loads(content)
            action     = result.get("action", "WATCH")
            confidence = float(result.get("confidence", 60))
            reasoning  = result.get("reasoning", "")
            key_factor = result.get("key_factor", "")
            if key_factor:
                reasoning += "\n\n**Factor decisivo:** " + key_factor

            if action not in ("ENTER", "WATCH", "SKIP"):
                action = "WATCH"

            return action, confidence, reasoning

        except Exception as e:
            logger.error("Erro API specialist: " + str(e))
            action     = "ENTER" if candidate.score >= self.MIN_SCORE_ENTER else "WATCH"
            confidence = min(candidate.score * 0.75, 70.0)
            reasoning  = "Avaliação parcial (API indisponível). Score: " + str(round(candidate.score, 0))
            return action, confidence, reasoning

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _quick_skip(self, candidate, reason: str, catalyst=None) -> Decision:
        from datetime import date
        entry_price = candidate.current_price
        stop_loss   = candidate.stop_loss
        target_1    = candidate.target_1
        target_2    = candidate.target_2
        risk_pct    = abs(entry_price - stop_loss) / entry_price * 100
        reward_pct  = abs(target_1 - entry_price) / entry_price * 100
        risk_reward = reward_pct / risk_pct if risk_pct > 0 else 0

        return Decision(
            ticker=candidate.ticker,
            scan_date=date.today().isoformat(),
            action="SKIP",
            confidence=90.0,
            reasoning=reason,
            entry_price=entry_price, stop_loss=stop_loss,
            target_1=target_1, target_2=target_2,
            risk_pct=risk_pct, reward_pct=reward_pct,
            risk_reward=risk_reward,
            catalyst_type=catalyst.catalyst_type if catalyst else "",
            catalyst_summary=catalyst.catalyst_summary if catalyst else "",
            catalyst_quality=catalyst.catalyst_quality if catalyst else "",
            alerts=[],
        )

    def _load_sugar_babies(self) -> set:
        try:
            from collections import defaultdict
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT bt.ticker, bt.pnl_pct
                    FROM backtest_trades bt
                    JOIN backtest_runs br ON bt.run_id = br.id
                    WHERE br.strategy_name = 'Episodic Pivot'
                """).fetchall()
            by_ticker = defaultdict(list)
            for r in rows:
                by_ticker[r["ticker"]].append(r["pnl_pct"])
            sugar = set()
            for ticker, pnls in by_ticker.items():
                if len(pnls) >= 2:
                    wins = sum(1 for p in pnls if p > 0)
                    if wins / len(pnls) >= 0.5:
                        sugar.add(ticker)
            return sugar
        except Exception:
            return set()

    def _get_ticker_history(self, ticker: str) -> str:
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT bt.pnl_pct, bt.entry_date, bt.exit_reason, bt.days_held
                    FROM backtest_trades bt
                    JOIN backtest_runs br ON bt.run_id = br.id
                    WHERE bt.ticker = ? AND br.strategy_name = 'Episodic Pivot'
                    ORDER BY bt.entry_date DESC LIMIT 5
                """, (ticker,)).fetchall()
            if not rows:
                return "Sem histórico."
            lines = [
                r["entry_date"][:10] + " | " +
                "{:+.1f}%".format(r["pnl_pct"]) + " | " +
                r["exit_reason"] + " | " + str(r["days_held"]) + "d"
                for r in rows
            ]
            wins = sum(1 for r in rows if r["pnl_pct"] > 0)
            return (str(len(rows)) + " trades (" + str(wins) +
                    " wins):\n" + "\n".join(lines))
        except Exception:
            return "Histórico indisponível."

    def _has_open_position(self, ticker: str) -> bool:
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT id FROM positions WHERE ticker = ? AND status = 'open'",
                    (ticker,)
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _save_decision(self, decision: Decision):
        with get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO decisions
                  (ticker, scan_date, action, confidence, reasoning,
                   entry_price, stop_loss, target_1, target_2,
                   risk_pct, reward_pct, risk_reward,
                   catalyst_type, catalyst_summary, catalyst_quality,
                   alerts, confirmed, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                decision.ticker, decision.scan_date, decision.action,
                decision.confidence, decision.reasoning,
                decision.entry_price, decision.stop_loss,
                decision.target_1, decision.target_2,
                decision.risk_pct, decision.reward_pct, decision.risk_reward,
                decision.catalyst_type, decision.catalyst_summary,
                decision.catalyst_quality,
                json.dumps(decision.alerts), 0,
                decision.created_at,
            ))

    def _ensure_tables(self):
        with get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker           TEXT NOT NULL,
                scan_date        TEXT NOT NULL,
                action           TEXT NOT NULL,
                confidence       REAL DEFAULT 0,
                reasoning        TEXT DEFAULT '',
                entry_price      REAL DEFAULT 0,
                stop_loss        REAL DEFAULT 0,
                target_1         REAL DEFAULT 0,
                target_2         REAL DEFAULT 0,
                risk_pct         REAL DEFAULT 0,
                reward_pct       REAL DEFAULT 0,
                risk_reward      REAL DEFAULT 0,
                catalyst_type    TEXT DEFAULT '',
                catalyst_summary TEXT DEFAULT '',
                catalyst_quality TEXT DEFAULT '',
                alerts           TEXT DEFAULT '[]',
                confirmed        INTEGER DEFAULT 0,
                rejection_reason TEXT DEFAULT '',
                created_at       TEXT NOT NULL,
                UNIQUE(ticker, scan_date)
            );
            """)
