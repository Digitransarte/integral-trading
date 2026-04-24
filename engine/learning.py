"""
Integral Trading — Sistema de Aprendizagem Nível 1
=====================================================
Calcula estatísticas de performance por padrão a partir
do histórico de trades reais (backtest + forward tracker).

Padrões analisados:
  - Por tipo de catalisador
  - Por sector
  - Por janela de entrada (PRIME/OPEN)
  - Por score range
  - Por Sugar Baby vs não Sugar Baby

O Decision Engine consulta estas estatísticas antes de cada decisão.
"""

import json
import logging
from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import Optional

from engine.database import get_conn, init_db

logger = logging.getLogger(__name__)


class LearningEngine:
    """
    Motor de aprendizagem estatística.

    Calcula win rates e profit factors por padrão,
    e fornece contexto para o Decision Engine.

    Uso:
        le = LearningEngine()
        le.update()                          # recalcular todas as stats
        ctx = le.get_context("IONQ", "PRIME", 75, "Earnings Beat Wide Margin")
        print(ctx)  # resumo das stats relevantes para esta decisão
    """

    def update(self) -> dict:
        """
        Recalcula todas as estatísticas a partir do histórico.
        Deve ser chamado após cada posição fechar.
        """
        init_db()
        self._ensure_tables()

        trades = self._load_all_trades()
        if not trades:
            logger.info("Sem trades para calcular estatísticas.")
            return {}

        stats = {}

        # ── Por sector ────────────────────────────────────────────────────────
        sector_stats = self._calc_by_field(trades, "sector")
        stats["by_sector"] = sector_stats
        self._save_stats("sector", sector_stats)

        # ── Por tipo de catalisador ───────────────────────────────────────────
        catalyst_stats = self._calc_by_field(trades, "catalyst_type")
        stats["by_catalyst"] = catalyst_stats
        self._save_stats("catalyst_type", catalyst_stats)

        # ── Por janela de entrada ─────────────────────────────────────────────
        window_stats = self._calc_by_field(trades, "entry_window")
        stats["by_window"] = window_stats
        self._save_stats("entry_window", window_stats)

        # ── Por score range ───────────────────────────────────────────────────
        score_stats = self._calc_by_score_range(trades)
        stats["by_score"] = score_stats
        self._save_stats("score_range", score_stats)

        # ── Sugar Baby vs não Sugar Baby ──────────────────────────────────────
        sugar_stats = self._calc_sugar_baby_stats(trades)
        stats["sugar_baby"] = sugar_stats
        self._save_stats("sugar_baby", sugar_stats)

        # ── Guardar timestamp da última actualização ──────────────────────────
        with get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO learning_meta
                  (key, value, updated_at)
                VALUES ('last_update', ?, ?)
            """, (date.today().isoformat(), datetime.utcnow().isoformat()))

        total_trades = len(trades)
        wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
        logger.info(
            "Estatísticas actualizadas: " + str(total_trades) + " trades | " +
            "Win rate global: " + str(round(wins / total_trades * 100, 1)) + "%"
        )
        return stats

    def get_context(
        self,
        ticker: str,
        entry_window: str,
        score: float,
        catalyst_type: str = "",
        sector: str = "",
    ) -> dict:
        """
        Retorna contexto estatístico relevante para uma decisão.
        Usado pelo Decision Engine antes de avaliar um candidato.
        """
        init_db()
        self._ensure_tables()

        context = {
            "has_data":      False,
            "summary":       "",
            "adjustments":   [],   # sugestões de ajuste à decisão
            "warning":       "",
        }

        stats_by_window   = self._get_stats("entry_window")
        stats_by_catalyst = self._get_stats("catalyst_type")
        stats_by_score    = self._get_stats("score_range")
        stats_by_sector   = self._get_stats("sector")

        lines = []
        adjustments = []

        # ── Janela de entrada ─────────────────────────────────────────────────
        if entry_window in stats_by_window:
            ws = stats_by_window[entry_window]
            if ws["trades"] >= 3:
                context["has_data"] = True
                lines.append(
                    "Janela " + entry_window + ": " +
                    str(ws["trades"]) + " trades | " +
                    "Win rate: " + str(ws["win_rate"]) + "% | " +
                    "PF: " + str(ws["profit_factor"])
                )
                if ws["win_rate"] < 40:
                    adjustments.append(
                        "⚠️ Janela " + entry_window + " tem win rate baixo (" +
                        str(ws["win_rate"]) + "%) no histórico"
                    )

        # ── Score range ───────────────────────────────────────────────────────
        score_range = self._get_score_range(score)
        if score_range in stats_by_score:
            ss = stats_by_score[score_range]
            if ss["trades"] >= 3:
                context["has_data"] = True
                lines.append(
                    "Score " + score_range + ": " +
                    str(ss["trades"]) + " trades | " +
                    "Win rate: " + str(ss["win_rate"]) + "% | " +
                    "PF: " + str(ss["profit_factor"])
                )

        # ── Catalisador ───────────────────────────────────────────────────────
        if catalyst_type and catalyst_type in stats_by_catalyst:
            cs = stats_by_catalyst[catalyst_type]
            if cs["trades"] >= 2:
                context["has_data"] = True
                lines.append(
                    "Catalisador '" + catalyst_type + "': " +
                    str(cs["trades"]) + " trades | " +
                    "Win rate: " + str(cs["win_rate"]) + "% | " +
                    "PF: " + str(cs["profit_factor"])
                )
                if cs["win_rate"] < 35:
                    adjustments.append(
                        "🔴 Este tipo de catalisador tem win rate histórico baixo (" +
                        str(cs["win_rate"]) + "%)"
                    )
                elif cs["win_rate"] > 65:
                    adjustments.append(
                        "🟢 Este tipo de catalisador tem win rate histórico alto (" +
                        str(cs["win_rate"]) + "%)"
                    )

        # ── Sector ───────────────────────────────────────────────────────────
        if sector and sector in stats_by_sector:
            sec = stats_by_sector[sector]
            if sec["trades"] >= 3:
                context["has_data"] = True
                lines.append(
                    "Sector " + sector + ": " +
                    str(sec["trades"]) + " trades | " +
                    "Win rate: " + str(sec["win_rate"]) + "% | " +
                    "PF: " + str(sec["profit_factor"])
                )

        # ── Ticker específico ─────────────────────────────────────────────────
        ticker_stats = self._get_ticker_stats(ticker)
        if ticker_stats and ticker_stats["trades"] >= 2:
            context["has_data"] = True
            lines.append(
                ticker + ": " + str(ticker_stats["trades"]) + " trades anteriores | " +
                "Win rate: " + str(ticker_stats["win_rate"]) + "% | " +
                "Avg P&L: " + str(ticker_stats["avg_pnl"]) + "%"
            )
            if ticker_stats["win_rate"] >= 60:
                adjustments.append(
                    "⭐ " + ticker + " tem bom histórico EP (" +
                    str(ticker_stats["win_rate"]) + "% win rate)"
                )

        context["summary"]     = "\n".join(lines) if lines else "Dados insuficientes."
        context["adjustments"] = adjustments

        return context

    def get_full_report(self) -> dict:
        """Relatório completo para o dashboard."""
        init_db()
        self._ensure_tables()

        return {
            "by_sector":    self._get_stats("sector"),
            "by_catalyst":  self._get_stats("catalyst_type"),
            "by_window":    self._get_stats("entry_window"),
            "by_score":     self._get_stats("score_range"),
            "sugar_baby":   self._get_stats("sugar_baby"),
            "last_update":  self._get_last_update(),
            "total_trades": self._count_trades(),
        }

    # ── Cálculos ──────────────────────────────────────────────────────────────

    def _calc_by_field(self, trades: list, field: str) -> dict:
        """Calcula estatísticas agrupadas por um campo."""
        groups = defaultdict(list)
        for t in trades:
            key = t.get(field, "")
            if key:
                groups[key].append(t["pnl_pct"])

        result = {}
        for key, pnls in groups.items():
            result[key] = self._calc_stats(pnls)
        return result

    def _calc_by_score_range(self, trades: list) -> dict:
        """Calcula estatísticas por range de score."""
        groups = defaultdict(list)
        for t in trades:
            score = t.get("score", 0)
            range_key = self._get_score_range(score)
            groups[range_key].append(t["pnl_pct"])

        return {k: self._calc_stats(v) for k, v in groups.items()}

    def _calc_sugar_baby_stats(self, trades: list) -> dict:
        """Compara Sugar Babies vs não Sugar Babies."""
        sugar_babies = self._load_sugar_babies_set()
        sugar_pnls = [t["pnl_pct"] for t in trades if t.get("ticker") in sugar_babies]
        other_pnls = [t["pnl_pct"] for t in trades if t.get("ticker") not in sugar_babies]

        return {
            "sugar_baby":     self._calc_stats(sugar_pnls) if sugar_pnls else {},
            "non_sugar_baby": self._calc_stats(other_pnls) if other_pnls else {},
        }

    def _calc_stats(self, pnls: list) -> dict:
        """Calcula métricas a partir de lista de P&Ls."""
        if not pnls:
            return {"trades": 0, "win_rate": 0, "avg_pnl": 0,
                    "profit_factor": 0, "avg_win": 0, "avg_loss": 0}

        wins   = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        gp = sum(wins)
        gl = abs(sum(losses))

        return {
            "trades":        len(pnls),
            "wins":          len(wins),
            "losses":        len(losses),
            "win_rate":      round(len(wins) / len(pnls) * 100, 1),
            "avg_pnl":       round(sum(pnls) / len(pnls), 2),
            "avg_win":       round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss":      round(sum(losses) / len(losses), 2) if losses else 0,
            "profit_factor": round(gp / gl, 2) if gl > 0 else round(gp, 2),
            "total_pnl":     round(sum(pnls), 2),
        }

    # ── DB ────────────────────────────────────────────────────────────────────

    def _load_all_trades(self) -> list:
        """Carrega todos os trades do histórico com metadados."""
        trades = []

        # Trades de backtest
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT
                        bt.ticker,
                        bt.pnl_pct,
                        bt.days_held,
                        bt.exit_reason,
                        br.strategy_name
                    FROM backtest_trades bt
                    JOIN backtest_runs br ON bt.run_id = br.id
                    WHERE br.strategy_name = 'Episodic Pivot'
                """).fetchall()
            for r in rows:
                trades.append({
                    "ticker":    r["ticker"],
                    "pnl_pct":   r["pnl_pct"],
                    "days_held": r["days_held"],
                    "source":    "backtest",
                })
        except Exception as e:
            logger.warning("Erro a carregar backtest trades: " + str(e))

        # Trades de forward tracker (fechados)
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT ticker, pnl_pct, days_held, exit_reason,
                           strategy_name, catalyst
                    FROM positions
                    WHERE status = 'closed'
                      AND strategy_name LIKE '%EP%'
                """).fetchall()
            for r in rows:
                trades.append({
                    "ticker":    r["ticker"],
                    "pnl_pct":   r["pnl_pct"],
                    "days_held": r["days_held"],
                    "source":    "forward",
                    "catalyst":  r["catalyst"],
                })
        except Exception as e:
            logger.warning("Erro a carregar forward trades: " + str(e))

        # Enriquecer com dados de decisões (catalisador, janela, score)
        trades = self._enrich_with_decisions(trades)

        return trades

    def _enrich_with_decisions(self, trades: list) -> list:
        """Adiciona metadados das decisões aos trades."""
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT ticker, scan_date, catalyst_type, catalyst_quality,
                           confidence
                    FROM decisions
                    WHERE action = 'ENTER' AND confirmed = 1
                """).fetchall()

            decision_map = {r["ticker"]: dict(r) for r in rows}

            for t in trades:
                d = decision_map.get(t["ticker"], {})
                t["catalyst_type"]    = d.get("catalyst_type", "")
                t["catalyst_quality"] = d.get("catalyst_quality", "")
                t["score"]            = d.get("confidence", 0)
                t["entry_window"]     = ""
                t["sector"]           = self._get_ticker_sector(t["ticker"])

        except Exception:
            for t in trades:
                t.setdefault("catalyst_type", "")
                t.setdefault("catalyst_quality", "")
                t.setdefault("score", 0)
                t.setdefault("entry_window", "")
                t.setdefault("sector", self._get_ticker_sector(t["ticker"]))

        return trades

    def _get_ticker_sector(self, ticker: str) -> str:
        """Descobre o sector de um ticker."""
        try:
            from universes import SECTORS
            for sector, tickers in SECTORS.items():
                if ticker in tickers:
                    return sector
        except Exception:
            pass
        return ""

    def _save_stats(self, category: str, data: dict):
        with get_conn() as conn:
            conn.execute("DELETE FROM learning_stats WHERE category = ?", (category,))
            for key, stats in data.items():
                if isinstance(stats, dict) and "trades" in stats:
                    conn.execute("""
                        INSERT INTO learning_stats
                          (category, key, trades, win_rate, avg_pnl,
                           profit_factor, avg_win, avg_loss, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """, (
                        category, key,
                        stats.get("trades", 0),
                        stats.get("win_rate", 0),
                        stats.get("avg_pnl", 0),
                        stats.get("profit_factor", 0),
                        stats.get("avg_win", 0),
                        stats.get("avg_loss", 0),
                        datetime.utcnow().isoformat(),
                    ))

    def _get_stats(self, category: str) -> dict:
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM learning_stats WHERE category = ?",
                    (category,)
                ).fetchall()
            return {
                r["key"]: {
                    "trades":        r["trades"],
                    "win_rate":      r["win_rate"],
                    "avg_pnl":       r["avg_pnl"],
                    "profit_factor": r["profit_factor"],
                    "avg_win":       r["avg_win"],
                    "avg_loss":      r["avg_loss"],
                }
                for r in rows
            }
        except Exception:
            return {}

    def _get_ticker_stats(self, ticker: str) -> Optional[dict]:
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT pnl_pct FROM backtest_trades bt
                    JOIN backtest_runs br ON bt.run_id = br.id
                    WHERE bt.ticker = ? AND br.strategy_name = 'Episodic Pivot'
                """, (ticker,)).fetchall()
            if not rows:
                return None
            pnls  = [r["pnl_pct"] for r in rows]
            wins  = [p for p in pnls if p > 0]
            return {
                "trades":   len(pnls),
                "win_rate": round(len(wins) / len(pnls) * 100, 1),
                "avg_pnl":  round(sum(pnls) / len(pnls), 2),
            }
        except Exception:
            return None

    def _load_sugar_babies_set(self) -> set:
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
            return {
                t for t, pnls in by_ticker.items()
                if len(pnls) >= 2 and sum(1 for p in pnls if p > 0) / len(pnls) >= 0.5
            }
        except Exception:
            return set()

    def _get_last_update(self) -> str:
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT value FROM learning_meta WHERE key = 'last_update'"
                ).fetchone()
            return row["value"] if row else "nunca"
        except Exception:
            return "nunca"

    def _count_trades(self) -> int:
        try:
            with get_conn() as conn:
                row = conn.execute("""
                    SELECT COUNT(*) as n FROM backtest_trades bt
                    JOIN backtest_runs br ON bt.run_id = br.id
                    WHERE br.strategy_name = 'Episodic Pivot'
                """).fetchone()
            return row["n"] if row else 0
        except Exception:
            return 0

    def _get_score_range(self, score: float) -> str:
        if score >= 80:   return "80-100"
        elif score >= 70: return "70-79"
        elif score >= 60: return "60-69"
        elif score >= 50: return "50-59"
        else:             return "0-49"

    def _ensure_tables(self):
        with get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS learning_stats (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                category       TEXT NOT NULL,
                key            TEXT NOT NULL,
                trades         INTEGER DEFAULT 0,
                win_rate       REAL DEFAULT 0,
                avg_pnl        REAL DEFAULT 0,
                profit_factor  REAL DEFAULT 0,
                avg_win        REAL DEFAULT 0,
                avg_loss       REAL DEFAULT 0,
                updated_at     TEXT NOT NULL,
                UNIQUE(category, key)
            );
            CREATE TABLE IF NOT EXISTS learning_meta (
                key        TEXT PRIMARY KEY,
                value      TEXT,
                updated_at TEXT
            );
            """)
