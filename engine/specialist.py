"""
Integral Trading — Especialista Base
=======================================
Especialista com acesso a dados reais da DB:
  - Histórico de backtests
  - Trades individuais
  - Posições abertas e fechadas
  - Candidatos do scanner
"""

import json
from datetime import datetime
from typing import Optional
import requests
import logging

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS   = 2000
MAX_HISTORY  = 20


class BaseSpecialist:

    name:          str = "Especialista"
    strategy_name: str = "base"
    system_prompt: str = ""
    knowledge:     dict = {}

    # ── Chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        if not ANTHROPIC_API_KEY:
            return "Chave ANTHROPIC_API_KEY não configurada no ficheiro .env"

        self._save_message("user", user_message)
        history     = self._get_history(MAX_HISTORY)
        full_system = self._build_system_prompt()

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
                    "max_tokens": MAX_TOKENS,
                    "system":     full_system,
                    "messages":   history,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            assistant_message = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    assistant_message += block["text"]

        except Exception as e:
            logger.error("Erro na API: " + str(e))
            assistant_message = "Erro ao contactar a API: " + str(e)

        self._save_message("assistant", assistant_message)
        return assistant_message

    def get_chat_history(self, limit: int = 50) -> list:
        return self._get_history_display(limit)

    def clear_history(self):
        from engine.database import get_conn, init_db
        init_db()
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM chat_messages WHERE specialist = ?",
                (self.strategy_name,)
            )

    def analyse_backtest(self, summary: dict) -> str:
        prompt = (
            "Acabei de correr um backtest da estratégia " + self.strategy_name + ".\n\n"
            "Resultados:\n" + json.dumps(summary, indent=2, ensure_ascii=False) +
            "\n\nComo especialista, analisa estes resultados. "
            "O que está a funcionar bem? O que precisa de melhoria? "
            "Que ajustes sugeres nos critérios?"
        )
        return self.chat(prompt)

    def analyse_trade(self, trade: dict) -> str:
        prompt = (
            "Analisa este trade:\n" +
            json.dumps(trade, indent=2, ensure_ascii=False) +
            "\n\nO que podemos aprender? O setup foi correcto? "
            "O que faria diferente?"
        )
        return self.chat(prompt)

    # ── Dados reais da DB ─────────────────────────────────────────────────────

    def get_all_trades(self) -> list:
        """Todos os trades de backtests desta estratégia."""
        try:
            from engine.database import get_conn, init_db
            init_db()
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT bt.ticker, bt.entry_date, bt.entry_price,
                           bt.exit_date, bt.exit_price, bt.exit_reason,
                           bt.pnl_pct, bt.days_held,
                           br.strategy_name
                    FROM backtest_trades bt
                    JOIN backtest_runs br ON bt.run_id = br.id
                    WHERE br.strategy_name = ?
                    ORDER BY bt.entry_date DESC
                """, (self.name,)).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error("Erro get_all_trades: " + str(e))
            return []

    def get_sugar_babies_candidates(self) -> list:
        """
        Identifica Sugar Babies — stocks com múltiplos EPs bem-sucedidos.
        Critério: >= 2 trades com pnl > 0 nos dados históricos.
        """
        trades = self.get_all_trades()
        if not trades:
            return []

        from collections import defaultdict
        by_ticker = defaultdict(list)
        for t in trades:
            by_ticker[t["ticker"]].append(t)

        candidates = []
        for ticker, ticker_trades in by_ticker.items():
            wins   = [t for t in ticker_trades if t["pnl_pct"] > 0]
            losses = [t for t in ticker_trades if t["pnl_pct"] <= 0]
            total  = len(ticker_trades)

            if total < 2:
                continue

            win_rate = len(wins) / total
            avg_win  = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
            gp = sum(t["pnl_pct"] for t in wins)
            gl = abs(sum(t["pnl_pct"] for t in losses))
            pf = gp / gl if gl > 0 else float("inf")

            if win_rate >= 0.5 and pf >= 1.5:
                candidates.append({
                    "ticker":    ticker,
                    "eps":       total,
                    "wins":      len(wins),
                    "win_rate":  round(win_rate * 100, 1),
                    "avg_win":   round(avg_win, 1),
                    "avg_loss":  round(avg_loss, 1),
                    "pf":        round(pf, 2),
                })

        return sorted(candidates, key=lambda x: x["pf"], reverse=True)

    def get_backtest_summary(self) -> Optional[dict]:
        """Resumo do último backtest."""
        try:
            from engine.database import get_conn, init_db
            init_db()
            with get_conn() as conn:
                row = conn.execute("""
                    SELECT strategy_name, total_trades, win_rate,
                           profit_factor, total_return, max_drawdown,
                           avg_hold_days, run_date, tickers
                    FROM backtest_runs
                    WHERE strategy_name = ?
                    ORDER BY run_date DESC LIMIT 1
                """, (self.name,)).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def get_open_positions(self) -> list:
        """Posições abertas actuais."""
        try:
            from engine.database import get_conn, init_db
            init_db()
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT ticker, strategy_name, entry_date, entry_price,
                           current_price, stop_price, target_1, pnl_pct,
                           days_held, catalyst
                    FROM positions
                    WHERE status = 'open'
                    ORDER BY entry_date DESC
                """).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── System prompt com dados reais ─────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        base = self.system_prompt

        # Knowledge base estruturada
        if self.knowledge:
            base += "\n\n## Base de Conhecimento\n"
            base += json.dumps(self.knowledge, indent=2, ensure_ascii=False)

        # Dados reais da DB
        data_context = self._build_data_context()
        if data_context:
            base += "\n\n## Dados Reais do Sistema\n"
            base += data_context

        return base

    def _build_data_context(self) -> str:
        """Constrói contexto com dados reais da DB."""
        parts = []

        # Último backtest
        bt = self.get_backtest_summary()
        if bt:
            parts.append(
                "### Último Backtest\n" +
                "- Trades: " + str(bt["total_trades"]) + "\n" +
                "- Win Rate: " + str(round(bt["win_rate"] * 100, 1)) + "%\n" +
                "- Profit Factor: " + str(round(bt["profit_factor"], 2)) + "\n" +
                "- Retorno: " + str(round(bt["total_return"], 1)) + "%\n" +
                "- Max Drawdown: " + str(round(bt["max_drawdown"], 1)) + "%\n" +
                "- Data: " + str(bt["run_date"])[:10]
            )

        # Todos os trades
        all_trades = self.get_all_trades()
        if all_trades:
            wins   = [t for t in all_trades if t["pnl_pct"] > 0]
            losses = [t for t in all_trades if t["pnl_pct"] <= 0]
            parts.append(
                "### Histórico de Trades (" + str(len(all_trades)) + " total)\n" +
                "- Wins: " + str(len(wins)) + " | Losses: " + str(len(losses)) + "\n" +
                "- Win rate global: " + str(round(len(wins) / len(all_trades) * 100, 1)) + "%\n" +
                "- Top 5 trades:\n" +
                "\n".join([
                    "  " + t["ticker"] + " " + str(round(t["pnl_pct"], 1)) + "% (" + str(t["days_held"]) + "d)"
                    for t in sorted(all_trades, key=lambda x: x["pnl_pct"], reverse=True)[:5]
                ]) +
                "\n- Piores 5 trades:\n" +
                "\n".join([
                    "  " + t["ticker"] + " " + str(round(t["pnl_pct"], 1)) + "% (" + str(t["days_held"]) + "d)"
                    for t in sorted(all_trades, key=lambda x: x["pnl_pct"])[:5]
                ])
            )

            # Tickers únicos
            tickers = list(set(t["ticker"] for t in all_trades))
            parts.append("### Tickers no histórico\n" + ", ".join(sorted(tickers)))

        # Sugar Babies candidatos
        sugar = self.get_sugar_babies_candidates()
        if sugar:
            parts.append(
                "### Sugar Babies Identificados (" + str(len(sugar)) + ")\n" +
                "\n".join([
                    "  " + s["ticker"] +
                    " | EPs: " + str(s["eps"]) +
                    " | Win: " + str(s["win_rate"]) + "%" +
                    " | PF: " + str(s["pf"])
                    for s in sugar[:10]
                ])
            )

        # Posições abertas
        positions = self.get_open_positions()
        if positions:
            parts.append(
                "### Posições Abertas (" + str(len(positions)) + ")\n" +
                "\n".join([
                    "  " + p["ticker"] +
                    " @ $" + str(round(p["entry_price"], 2)) +
                    " | P&L: " + str(round(p["pnl_pct"], 1)) + "%" +
                    " | Dia " + str(p["days_held"])
                    for p in positions
                ])
            )

        return "\n\n".join(parts)

    # ── Internos ──────────────────────────────────────────────────────────────

    def _save_message(self, role: str, content: str):
        from engine.database import get_conn, init_db
        init_db()
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO chat_messages (specialist, role, content, created_at)
                VALUES (?, ?, ?, ?)
            """, (self.strategy_name, role, content,
                  datetime.utcnow().isoformat()))

    def _get_history(self, limit: int) -> list:
        from engine.database import get_conn, init_db
        init_db()
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT role, content FROM chat_messages
                WHERE specialist = ?
                ORDER BY created_at DESC LIMIT ?
            """, (self.strategy_name, limit)).fetchall()

        messages = [{"role": r["role"], "content": r["content"]}
                    for r in reversed(rows)]
        while messages and messages[0]["role"] == "assistant":
            messages.pop(0)
        return messages

    def _get_history_display(self, limit: int) -> list:
        from engine.database import get_conn, init_db
        init_db()
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT role, content, created_at FROM chat_messages
                WHERE specialist = ?
                ORDER BY created_at ASC LIMIT ?
            """, (self.strategy_name, limit)).fetchall()
        return [dict(r) for r in rows]
