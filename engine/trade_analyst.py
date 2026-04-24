"""
Integral Trading — Trade Analyst (Nível 2)
============================================
Após cada posição fechar, o especialista EP analisa o resultado
e escreve conclusões que ficam na knowledge base.

O especialista aprende:
  - O que funcionou e porquê
  - O que falhou e porquê
  - Padrões recorrentes
  - Ajustes sugeridos aos critérios
"""

import json
import logging
import requests
from datetime import datetime
from typing import Optional

from config import ANTHROPIC_API_KEY
from engine.database import get_conn, init_db

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"


class TradeAnalyst:
    """
    Analisa trades fechados e acumula conhecimento narrativo.

    Uso:
        analyst = TradeAnalyst()

        # Analisar um trade específico
        analyst.analyse_closed_trade(position_id=3)

        # Analisar todos os trades ainda não analisados
        analyst.analyse_pending()

        # Ver o que o sistema aprendeu
        lessons = analyst.get_lessons(limit=10)
    """

    def __init__(self):
        init_db()
        self._ensure_tables()

    # ── Análise de trades ─────────────────────────────────────────────────────

    def analyse_closed_trade(self, position_id: int) -> Optional[dict]:
        """Analisa um trade fechado e guarda a conclusão."""
        pos = self._get_position(position_id)
        if not pos:
            logger.warning("Posição #" + str(position_id) + " não encontrada.")
            return None

        if pos["status"] != "closed":
            logger.warning("Posição #" + str(position_id) + " ainda não fechada.")
            return None

        # Verificar se já foi analisado
        if self._already_analysed(position_id):
            logger.info("Posição #" + str(position_id) + " já analisada.")
            return None

        decision = self._get_decision_for_position(pos["ticker"])
        lesson   = self._ask_specialist(pos, decision)

        if lesson:
            self._save_lesson(position_id, pos, lesson)
            logger.info(
                "Lição guardada: " + pos["ticker"] +
                " | " + ("WIN" if pos["pnl_pct"] > 0 else "LOSS") +
                " " + str(round(pos["pnl_pct"], 1)) + "%"
            )

        return lesson

    def analyse_pending(self) -> list:
        """Analisa todos os trades fechados ainda não analisados."""
        positions = self._get_unanalysed_positions()
        logger.info(str(len(positions)) + " trades para analisar.")

        lessons = []
        for pos in positions:
            try:
                lesson = self.analyse_closed_trade(pos["id"])
                if lesson:
                    lessons.append(lesson)
            except Exception as e:
                logger.error("Erro ao analisar #" + str(pos["id"]) + ": " + str(e))

        return lessons

    def get_lessons(self, limit: int = 20, ticker: str = None) -> list:
        """Retorna lições aprendidas."""
        with get_conn() as conn:
            if ticker:
                rows = conn.execute("""
                    SELECT * FROM trade_lessons
                    WHERE ticker = ?
                    ORDER BY created_at DESC LIMIT ?
                """, (ticker, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM trade_lessons
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_pattern_summary(self) -> str:
        """
        Resumo narrativo dos padrões aprendidos.
        Usado pelo especialista EP como contexto.
        """
        lessons = self.get_lessons(limit=50)
        if not lessons:
            return "Sem lições acumuladas ainda."

        wins   = [l for l in lessons if l.get("outcome") == "WIN"]
        losses = [l for l in lessons if l.get("outcome") == "LOSS"]

        summary_parts = []

        if wins:
            summary_parts.append(
                "PADRÕES QUE FUNCIONARAM (" + str(len(wins)) + " trades):\n" +
                "\n".join([
                    "- " + l["ticker"] + " (" + l.get("catalyst_type", "") + "): " +
                    l.get("key_learning", "")[:100]
                    for l in wins[:5]
                ])
            )

        if losses:
            summary_parts.append(
                "PADRÕES QUE FALHARAM (" + str(len(losses)) + " trades):\n" +
                "\n".join([
                    "- " + l["ticker"] + " (" + l.get("catalyst_type", "") + "): " +
                    l.get("key_learning", "")[:100]
                    for l in losses[:5]
                ])
            )

        return "\n\n".join(summary_parts)

    def get_criteria_suggestions(self) -> list:
        """
        Sugestões de ajuste aos critérios baseadas nas lições.
        """
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT criteria_suggestion, COUNT(*) as count
                FROM trade_lessons
                WHERE criteria_suggestion != ''
                GROUP BY criteria_suggestion
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()
        return [dict(r) for r in rows]

    # ── Análise pelo especialista ─────────────────────────────────────────────

    def _ask_specialist(self, pos: dict, decision: Optional[dict]) -> Optional[dict]:
        """Pede ao especialista EP para analisar o trade."""
        if not ANTHROPIC_API_KEY:
            return self._simple_lesson(pos)

        outcome    = "WIN" if pos["pnl_pct"] > 0 else "LOSS"
        pnl_str    = "{:+.1f}%".format(pos["pnl_pct"])
        days       = pos.get("days_held", 0)
        exit_reason = pos.get("exit_reason", "")

        decision_context = ""
        if decision:
            decision_context = f"""
**Decisão original:**
- Confiança: {round(decision.get('confidence', 0), 0)}%
- Catalisador: {decision.get('catalyst_type', 'desconhecido')}
- Qualidade do catalisador: {decision.get('catalyst_quality', 'desconhecida')}
- Raciocínio original: {decision.get('reasoning', '')[:200]}
"""

        prompt = f"""Analisa este trade EP e extrai a lição mais importante.

## Trade: {pos['ticker']} — {outcome} {pnl_str}

**Dados:**
- Entrada: ${round(pos['entry_price'], 2)} em {pos.get('entry_date', '')}
- Saída: ${round(pos.get('exit_price', 0) or 0, 2)} em {pos.get('exit_date', '')}
- Razão de saída: {exit_reason}
- Dias em posição: {days}
- P&L: {pnl_str}
- Catalisador: {pos.get('catalyst', 'desconhecido')}
{decision_context}

Como especialista EP, analisa:
1. Porque funcionou/falhou este trade?
2. O catalisador era da qualidade certa?
3. A entrada foi no timing certo?
4. O que farias diferente?
5. Que ajuste aos critérios EP sugeres?

Responde APENAS em JSON:
{{
  "outcome": "WIN" ou "LOSS",
  "key_learning": "a lição mais importante em 1-2 frases",
  "what_worked": "o que funcionou bem (ou vazio se LOSS)",
  "what_failed": "o que falhou (ou vazio se WIN)",
  "catalyst_assessment": "avaliação do catalisador",
  "timing_assessment": "avaliação do timing de entrada",
  "criteria_suggestion": "sugestão concreta de ajuste aos critérios (ou vazio)",
  "pattern_tag": "tag curta para categorizar: ex: 'earnings_beat_prime', 'late_entry_failure'"
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
                    "max_tokens": 500,
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
            start   = content.find("{")
            end     = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = content[start:end]

            result = json.loads(content)
            result["outcome"] = outcome
            return result

        except Exception as e:
            logger.error("Erro API trade analyst: " + str(e))
            return self._simple_lesson(pos)

    def _simple_lesson(self, pos: dict) -> dict:
        """Lição simples sem API."""
        outcome = "WIN" if pos["pnl_pct"] > 0 else "LOSS"
        return {
            "outcome":             outcome,
            "key_learning":        outcome + " de " + str(round(pos["pnl_pct"], 1)) + "% em " + str(pos.get("days_held", 0)) + " dias.",
            "what_worked":         "",
            "what_failed":         "",
            "catalyst_assessment": "",
            "timing_assessment":   "",
            "criteria_suggestion": "",
            "pattern_tag":         outcome.lower() + "_basic",
        }

    # ── DB ────────────────────────────────────────────────────────────────────

    def _save_lesson(self, position_id: int, pos: dict, lesson: dict):
        with get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trade_lessons
                  (position_id, ticker, outcome, pnl_pct, days_held,
                   catalyst_type, key_learning, what_worked, what_failed,
                   catalyst_assessment, timing_assessment,
                   criteria_suggestion, pattern_tag, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                position_id,
                pos["ticker"],
                lesson.get("outcome", ""),
                round(pos["pnl_pct"], 2),
                pos.get("days_held", 0),
                pos.get("catalyst", ""),
                lesson.get("key_learning", ""),
                lesson.get("what_worked", ""),
                lesson.get("what_failed", ""),
                lesson.get("catalyst_assessment", ""),
                lesson.get("timing_assessment", ""),
                lesson.get("criteria_suggestion", ""),
                lesson.get("pattern_tag", ""),
                datetime.utcnow().isoformat(),
            ))

    def _get_position(self, position_id: int) -> Optional[dict]:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE id = ?", (position_id,)
            ).fetchone()
        return dict(row) if row else None

    def _get_unanalysed_positions(self) -> list:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT p.* FROM positions p
                LEFT JOIN trade_lessons tl ON tl.position_id = p.id
                WHERE p.status = 'closed'
                  AND tl.id IS NULL
                ORDER BY p.exit_date DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def _already_analysed(self, position_id: int) -> bool:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM trade_lessons WHERE position_id = ?",
                (position_id,)
            ).fetchone()
        return row is not None

    def _get_decision_for_position(self, ticker: str) -> Optional[dict]:
        """Busca a decisão original associada a este ticker."""
        try:
            with get_conn() as conn:
                row = conn.execute("""
                    SELECT * FROM decisions
                    WHERE ticker = ? AND confirmed = 1
                    ORDER BY created_at DESC LIMIT 1
                """, (ticker,)).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def _ensure_tables(self):
        with get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS trade_lessons (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id          INTEGER UNIQUE,
                ticker               TEXT NOT NULL,
                outcome              TEXT NOT NULL,
                pnl_pct              REAL DEFAULT 0,
                days_held            INTEGER DEFAULT 0,
                catalyst_type        TEXT DEFAULT '',
                key_learning         TEXT DEFAULT '',
                what_worked          TEXT DEFAULT '',
                what_failed          TEXT DEFAULT '',
                catalyst_assessment  TEXT DEFAULT '',
                timing_assessment    TEXT DEFAULT '',
                criteria_suggestion  TEXT DEFAULT '',
                pattern_tag          TEXT DEFAULT '',
                created_at           TEXT NOT NULL
            );
            """)
