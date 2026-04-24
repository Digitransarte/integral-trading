"""
Integral Trading — Forward Tracker
=====================================
Regista posições abertas, actualiza preços diariamente,
detecta stops e targets, mantém histórico completo.

Uso:
    from engine.forward_tracker import ForwardTracker
    from engine.data_feed import DataFeed

    tracker = ForwardTracker(DataFeed())

    # Abrir posição
    pos_id = tracker.open_position(
        ticker="HIMS",
        strategy="ep",
        entry_price=31.50,
        stop_price=29.00,
        target_1=36.00,
        target_2=41.00,
        score=80.0,
        catalyst="Earnings beat Q1 2026",
    )

    # Actualizar todas as posições abertas
    summary = tracker.update_all()

    # Fechar posição manualmente
    tracker.close_position(pos_id, reason="manual")
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import logging

from engine.data_feed import DataFeed
from engine.database import get_conn, init_db

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Uma posição aberta ou fechada."""
    id: int
    ticker: str
    strategy_name: str
    entry_date: str
    entry_price: float
    stop_price: float
    target_1: float
    target_2: float
    current_price: float
    days_held: int
    status: str             # open / closed
    exit_date: Optional[str]
    exit_price: Optional[float]
    exit_reason: str
    pnl_pct: float
    score: float
    catalyst: str
    metadata: str

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    @property
    def pnl_dollar(self) -> float:
        """P&L em % desde a entrada."""
        return self.pnl_pct

    @property
    def distance_to_stop(self) -> float:
        if self.current_price <= 0:
            return 0.0
        return (self.current_price - self.stop_price) / self.current_price * 100

    @property
    def distance_to_target1(self) -> float:
        if self.current_price <= 0:
            return 0.0
        return (self.target_1 - self.current_price) / self.current_price * 100

    @property
    def risk_reward(self) -> float:
        risk   = abs(self.entry_price - self.stop_price)
        reward = abs(self.target_1 - self.entry_price)
        return reward / risk if risk > 0 else 0.0


@dataclass
class UpdateSummary:
    """Resultado de uma actualização de todas as posições."""
    updated: int = 0
    stopped_out: int = 0
    target_hit: int = 0
    errors: int = 0
    closed_positions: list = None

    def __post_init__(self):
        if self.closed_positions is None:
            self.closed_positions = []


class ForwardTracker:
    """
    Gere posições abertas — abre, actualiza e fecha.
    Usa a tabela `positions` da base de dados SQLite.
    """

    def __init__(self, feed: DataFeed):
        self.feed = feed
        init_db()

    # ── Abrir posição ─────────────────────────────────────────────────────────

    def open_position(
        self,
        ticker: str,
        strategy: str,
        entry_price: float,
        stop_price: float,
        target_1: float,
        target_2: float,
        score: float = 0.0,
        catalyst: str = "",
        notes: str = "",
    ) -> int:
        """
        Regista uma nova posição aberta.
        Retorna o ID da posição criada.
        """
        # Verificar se já existe posição aberta para este ticker
        existing = self.get_open_position(ticker)
        if existing:
            logger.warning("Já existe posição aberta para " + ticker +
                           " (ID #" + str(existing.id) + ")")
            return existing.id

        now = datetime.utcnow().strftime("%Y-%m-%d")

        with get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO positions
                  (ticker, strategy_name, entry_date, entry_price,
                   stop_price, target_1, target_2, current_price,
                   days_held, status, pnl_pct, score, catalyst, metadata)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ticker.upper(), strategy, now, entry_price,
                stop_price, target_1, target_2, entry_price,
                0, "open", 0.0, score, catalyst,
                '{"notes": "' + notes + '"}',
            ))
            pos_id = cur.lastrowid

        logger.info("Posição aberta: " + ticker +
                    " @ $" + str(round(entry_price, 2)) +
                    " | Stop: $" + str(round(stop_price, 2)) +
                    " | T1: $" + str(round(target_1, 2)) +
                    " (ID #" + str(pos_id) + ")")
        return pos_id

    # ── Actualizar posições ───────────────────────────────────────────────────

    def update_all(self) -> UpdateSummary:
        """
        Actualiza todas as posições abertas com preços actuais.
        Detecta stops e targets automaticamente.
        Retorna um resumo do que aconteceu.
        """
        positions = self.get_open_positions()
        summary   = UpdateSummary()

        if not positions:
            logger.info("Nenhuma posição aberta para actualizar.")
            return summary

        # Buscar preços de uma vez (mais eficiente)
        tickers = [p.ticker for p in positions]
        prices  = self.feed.get_multiple_prices(tickers)

        for pos in positions:
            try:
                current_price = prices.get(pos.ticker)
                if current_price is None or current_price <= 0:
                    logger.warning("Sem preço para " + pos.ticker)
                    summary.errors += 1
                    continue

                # Calcular dias em posição
                entry_dt  = datetime.strptime(pos.entry_date, "%Y-%m-%d")
                days_held = (datetime.utcnow() - entry_dt).days

                # Calcular P&L actual
                pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100

                # Verificar stop e target
                action = self._check_exit(pos, current_price, days_held)

                if action in ("stop", "target_1", "time_exit"):
                    self._close_position(pos.id, current_price, action)
                    summary.closed_positions.append({
                        "ticker":  pos.ticker,
                        "reason":  action,
                        "pnl_pct": round(pnl_pct, 2),
                    })
                    if action == "stop":
                        summary.stopped_out += 1
                    else:
                        summary.target_hit += 1
                    logger.info("Posição fechada: " + pos.ticker +
                                " | " + action +
                                " | P&L: " + str(round(pnl_pct, 1)) + "%")
                else:
                    # Actualizar preço e dias
                    self._update_price(pos.id, current_price, days_held, pnl_pct)
                    summary.updated += 1
                    logger.debug("Actualizado: " + pos.ticker +
                                 " $" + str(round(current_price, 2)) +
                                 " (" + str(round(pnl_pct, 1)) + "%)")

            except Exception as e:
                logger.error("Erro a actualizar " + pos.ticker + ": " + str(e))
                summary.errors += 1

        return summary

    def update_single(self, ticker: str) -> Optional[dict]:
        """Actualiza uma posição específica. Retorna estado actual."""
        pos = self.get_open_position(ticker)
        if not pos:
            return None

        price = self.feed.get_current_price(ticker)
        if not price:
            return None

        days_held = (datetime.utcnow() -
                     datetime.strptime(pos.entry_date, "%Y-%m-%d")).days
        pnl_pct   = (price - pos.entry_price) / pos.entry_price * 100
        action    = self._check_exit(pos, price, days_held)

        if action in ("stop", "target_1", "time_exit"):
            self._close_position(pos.id, price, action)
        else:
            self._update_price(pos.id, price, days_held, pnl_pct)

        return {
            "ticker":        ticker,
            "current_price": round(price, 2),
            "pnl_pct":       round(pnl_pct, 2),
            "days_held":     days_held,
            "action":        action,
        }

    # ── Fechar posição ────────────────────────────────────────────────────────

    def close_position(self, position_id: int, reason: str = "manual") -> bool:
        """Fecha uma posição manualmente."""
        pos = self.get_position_by_id(position_id)
        if not pos or not pos.is_open:
            return False

        price = self.feed.get_current_price(pos.ticker)
        if not price:
            price = pos.current_price

        self._close_position(position_id, price, reason)
        logger.info("Posição fechada manualmente: " + pos.ticker +
                    " @ $" + str(round(price, 2)))
        return True

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_open_positions(self) -> list:
        """Lista todas as posições abertas."""
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM positions
                WHERE status = 'open'
                ORDER BY entry_date DESC
            """).fetchall()
        return [self._row_to_position(r) for r in rows]

    def get_open_position(self, ticker: str) -> Optional[Position]:
        """Posição aberta para um ticker específico."""
        with get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM positions
                WHERE status = 'open' AND ticker = ?
            """, (ticker.upper(),)).fetchone()
        return self._row_to_position(row) if row else None

    def get_closed_positions(self, limit: int = 50) -> list:
        """Últimas N posições fechadas."""
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM positions
                WHERE status = 'closed'
                ORDER BY exit_date DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [self._row_to_position(r) for r in rows]

    def get_position_by_id(self, pos_id: int) -> Optional[Position]:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE id = ?", (pos_id,)
            ).fetchone()
        return self._row_to_position(row) if row else None

    def get_stats(self) -> dict:
        """Métricas gerais do tracker."""
        closed = self.get_closed_positions(limit=1000)
        if not closed:
            return {
                "total_closed": 0, "win_rate": 0,
                "avg_win": 0, "avg_loss": 0,
                "profit_factor": 0, "total_pnl": 0,
            }

        wins   = [p for p in closed if p.pnl_pct > 0]
        losses = [p for p in closed if p.pnl_pct <= 0]

        gp = sum(p.pnl_pct for p in wins)
        gl = abs(sum(p.pnl_pct for p in losses))

        return {
            "total_closed":  len(closed),
            "win_rate":      round(len(wins) / len(closed) * 100, 1),
            "avg_win":       round(sum(p.pnl_pct for p in wins) / len(wins), 2) if wins else 0,
            "avg_loss":      round(sum(p.pnl_pct for p in losses) / len(losses), 2) if losses else 0,
            "profit_factor": round(gp / gl, 2) if gl else 0,
            "total_pnl":     round(sum(p.pnl_pct for p in closed), 2),
        }

    # ── Internos ──────────────────────────────────────────────────────────────

    def _check_exit(self, pos: Position, price: float, days_held: int) -> str:
        """Decide se a posição deve ser fechada."""
        if price <= pos.stop_price:
            return "stop"
        if price >= pos.target_1:
            return "target_1"
        if days_held >= 20:
            return "time_exit"
        return "hold"

    def _update_price(self, pos_id: int, price: float,
                      days_held: int, pnl_pct: float):
        with get_conn() as conn:
            conn.execute("""
                UPDATE positions
                SET current_price = ?, days_held = ?, pnl_pct = ?
                WHERE id = ?
            """, (price, days_held, pnl_pct, pos_id))

    def _close_position(self, pos_id: int, price: float, reason: str):
        pos     = self.get_position_by_id(pos_id)
        pnl_pct = (price - pos.entry_price) / pos.entry_price * 100
        now     = datetime.utcnow().strftime("%Y-%m-%d")

        with get_conn() as conn:
            conn.execute("""
                UPDATE positions
                SET status      = 'closed',
                    exit_date   = ?,
                    exit_price  = ?,
                    exit_reason = ?,
                    pnl_pct     = ?,
                    current_price = ?
                WHERE id = ?
            """, (now, price, reason, pnl_pct, price, pos_id))

    def _row_to_position(self, row) -> Position:
        d = dict(row)
        return Position(
            id=d["id"],
            ticker=d["ticker"],
            strategy_name=d["strategy_name"],
            entry_date=d["entry_date"],
            entry_price=d["entry_price"],
            stop_price=d["stop_price"],
            target_1=d["target_1"],
            target_2=d["target_2"],
            current_price=d.get("current_price") or d["entry_price"],
            days_held=d.get("days_held") or 0,
            status=d["status"],
            exit_date=d.get("exit_date"),
            exit_price=d.get("exit_price"),
            exit_reason=d.get("exit_reason") or "",
            pnl_pct=d.get("pnl_pct") or 0.0,
            score=d.get("score") or 0.0,
            catalyst=d.get("catalyst") or "",
            metadata=d.get("metadata") or "{}",
        )
