"""Dashboard - Automação e Recomendações"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import json
from datetime import datetime, date, timedelta

try:
    from engine.database import get_conn, init_db
    from engine.decision_engine import DecisionEngine
    from engine.forward_tracker import ForwardTracker
    from engine.data_feed import DataFeed
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)


def render():
    st.title("Automação e Recomendações")

    if not ENGINE_AVAILABLE:
        st.error("Engine nao disponivel.", icon="🔴")
        return

    init_db()
    _ensure_tables()

    tab1, tab2, tab3 = st.tabs([
        "Recomendações de Hoje",
        "Histórico de Decisões",
        "Estado do Sistema",
    ])

    # ── Tab 1: Recomendações de Hoje ──────────────────────────────────────────
    with tab1:
        today = date.today().isoformat()
        st.subheader("Recomendações — " + today)

        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🔍 Correr Scanner + Análise", use_container_width=True, type="primary"):
                _run_full_scan()
                st.rerun()

        # Verificar se o scan correu hoje
        scan_log = _get_scan_log(today)
        if scan_log:
            st.caption(
                "Scanner correu às " + scan_log["created_at"][11:16] + " UTC  |  " +
                str(scan_log["tickers_scanned"]) + " tickers  |  " +
                str(scan_log["candidates_found"]) + " candidatos"
            )
        else:
            st.info("O scanner ainda não correu hoje. Corre manualmente ou aguarda as 15:00.", icon="⏳")

        # Decisões de hoje
        decisions = _get_decisions(today)

        if not decisions:
            st.info("Nenhuma decisão hoje. Corre o scanner para gerar recomendações.")
        else:
            # Resumo
            enters = [d for d in decisions if d["action"] == "ENTER"]
            watches = [d for d in decisions if d["action"] == "WATCH"]
            skips  = [d for d in decisions if d["action"] == "SKIP"]

            c1, c2, c3 = st.columns(3)
            c1.metric("🟢 Entrar",   len(enters))
            c2.metric("🟡 Aguardar", len(watches))
            c3.metric("🔴 Saltar",   len(skips))

            st.markdown("---")

            # Mostrar ENTER primeiro, depois WATCH
            priority = enters + watches
            if priority:
                st.subheader("Acção Recomendada")
                for d in priority:
                    _render_decision_card(d)

            # SKIP compacto
            if skips:
                with st.expander("Candidatos descartados (" + str(len(skips)) + ")"):
                    for d in skips:
                        st.caption(
                            "🔴 **" + d["ticker"] + "** — " +
                            d["reasoning"][:100] + "..."
                        )

    # ── Tab 2: Histórico de Decisões ──────────────────────────────────────────
    with tab2:
        st.subheader("Histórico de Decisões (30 dias)")

        engine  = DecisionEngine()
        history = engine.get_decision_history(days=30)

        if not history:
            st.info("Nenhuma decisão registada ainda.")
        else:
            # Métricas globais
            enters_hist = [d for d in history if d["action"] == "ENTER"]
            confirmed   = [d for d in enters_hist if d["confirmed"] == 1]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Decisões",  len(history))
            c2.metric("ENTER",           len(enters_hist))
            c3.metric("Confirmadas",     len(confirmed))
            c4.metric("Taxa Confirmação",
                      str(round(len(confirmed) / len(enters_hist) * 100, 0)) + "%" if enters_hist else "-")

            st.markdown("---")

            rows = []
            for d in history:
                icon = {"ENTER": "🟢", "WATCH": "🟡", "SKIP": "🔴"}.get(d["action"], "")
                conf_status = {1: "✅ Confirmada", -1: "❌ Rejeitada", 0: "⏳ Pendente"}.get(
                    d["confirmed"], "")
                rows.append({
                    "":           icon,
                    "Data":       d["scan_date"],
                    "Ticker":     d["ticker"],
                    "Decisão":    d["action"],
                    "Confiança":  str(round(d["confidence"], 0)) + "%",
                    "R/R":        str(round(d["risk_reward"], 2)),
                    "Entrada":    "$" + str(round(d["entry_price"], 2)),
                    "Stop":       "$" + str(round(d["stop_loss"], 2)),
                    "Status":     conf_status,
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Tab 3: Estado do Sistema ──────────────────────────────────────────────
    with tab3:
        st.subheader("Estado das Tarefas Agendadas")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Scanner EP + Decision Engine**")
            st.caption("Horário: todos os dias úteis às 15:00")
            scan_today = _get_scan_log(date.today().isoformat())
            if scan_today:
                st.success("Correu hoje às " + scan_today["created_at"][11:16] + " UTC", icon="✅")
            else:
                st.warning("Ainda não correu hoje", icon="⏳")

        with col2:
            st.markdown("**Tracker de Posições**")
            st.caption("Horário: todos os dias úteis às 22:30")
            report_today = _get_daily_report(date.today().isoformat())
            if report_today:
                st.success("Correu hoje às " + report_today["created_at"][11:16] + " UTC", icon="✅")
            else:
                st.warning("Ainda não correu hoje", icon="⏳")

        st.markdown("---")
        st.subheader("Logs recentes")

        logs = _get_scan_logs(7)
        if logs:
            df = pd.DataFrame(logs)[["scan_date", "tickers_scanned", "candidates_found", "duration_seconds"]]
            df.columns = ["Data", "Tickers", "Candidatos", "Tempo(s)"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Sem logs ainda.")

        with st.expander("Configuração do Task Scheduler"):
            st.markdown("""
**Tarefas activas:**
```
IntegralTrading_Scanner  → 15:00 Seg-Sex
IntegralTrading_Tracker  → 22:30 Seg-Sex
```

**Verificar:**
```
schtasks /query /tn "IntegralTrading_Scanner"
schtasks /query /tn "IntegralTrading_Tracker"
```

**Correr manualmente:**
```
python scheduled_scan.py
python scheduled_update.py
```

**Logs:** `C:\\integral-trading\\logs\\`
            """)


# ── Render de card de decisão ─────────────────────────────────────────────────

def _render_decision_card(d: dict):
    """Card completo para uma decisão ENTER ou WATCH."""
    action      = d["action"]
    ticker      = d["ticker"]
    confidence  = d["confidence"]
    reasoning   = d["reasoning"]
    confirmed   = d["confirmed"]

    icon = "🟢" if action == "ENTER" else "🟡"
    border_color = "#22c55e" if action == "ENTER" else "#eab308"

    alerts = []
    try:
        alerts = json.loads(d.get("alerts", "[]"))
    except Exception:
        pass

    with st.container():
        st.markdown(
            "<div style='border-left: 4px solid " + border_color + "; "
            "padding: 12px 16px; margin-bottom: 16px; "
            "background: #f8f9fa; border-radius: 4px;'>"
            "<b>" + icon + " " + ticker + "</b> — " + action +
            " | Confiança: " + str(round(confidence, 0)) + "%"
            "</div>",
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Entrada",  "$" + str(round(d["entry_price"], 2)))
        c2.metric("Stop",     "$" + str(round(d["stop_loss"], 2)),
                  delta="-" + str(round(d["risk_pct"], 1)) + "%",
                  delta_color="inverse")
        c3.metric("Target 1", "$" + str(round(d["target_1"], 2)),
                  delta="+" + str(round(d["reward_pct"], 1)) + "%")
        c4.metric("R/R",      str(round(d["risk_reward"], 2)))

        # Raciocínio
        st.markdown("**Raciocínio do especialista:**")
        st.info(reasoning)

        if alerts:
            st.caption("Alertas: " + " | ".join(alerts))

        # Botões de acção
        if confirmed == 0:
            col_enter, col_watch, col_skip = st.columns([2, 1, 1])
            with col_enter:
                if action == "ENTER":
                    if st.button(
                        "✅ Confirmar entrada em " + ticker,
                        key="confirm_" + str(d["id"]),
                        use_container_width=True,
                        type="primary",
                    ):
                        _confirm_entry(d)
                        st.success("Posição aberta em " + ticker + "!")
                        st.rerun()
            with col_watch:
                if st.button("👁 Aguardar", key="watch_" + str(d["id"]),
                             use_container_width=True):
                    _reject_decision(d["id"], "manual_watch")
                    st.rerun()
            with col_skip:
                if st.button("❌ Saltar", key="skip_" + str(d["id"]),
                             use_container_width=True):
                    _reject_decision(d["id"], "manual_skip")
                    st.rerun()
        elif confirmed == 1:
            st.success("✅ Entrada confirmada", icon="✅")
        elif confirmed == -1:
            st.caption("❌ Descartada: " + d.get("rejection_reason", ""))

        st.markdown("---")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _confirm_entry(d: dict):
    """Confirma entrada e abre posição no tracker."""
    engine = DecisionEngine()
    engine.confirm_entry(d["id"])

    feed    = DataFeed(polygon_key=POLYGON_API_KEY)
    tracker = ForwardTracker(feed)
    tracker.open_position(
        ticker=d["ticker"],
        strategy="EP",
        entry_price=d["entry_price"],
        stop_price=d["stop_loss"],
        target_1=d["target_1"],
        target_2=d["target_2"],
        score=d["confidence"],
        catalyst="Decision Engine — confiança " + str(round(d["confidence"], 0)) + "%",
    )


def _reject_decision(decision_id: int, reason: str):
    engine = DecisionEngine()
    engine.reject_decision(decision_id, reason)


def _get_decisions(scan_date: str) -> list:
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM decisions
                WHERE scan_date = ?
                ORDER BY
                  CASE action WHEN 'ENTER' THEN 1 WHEN 'WATCH' THEN 2 ELSE 3 END,
                  confidence DESC
            """, (scan_date,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _get_scan_log(scan_date: str) -> dict:
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM scan_log WHERE scan_date = ? LIMIT 1",
                (scan_date,)
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _get_daily_report(report_date: str) -> dict:
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE report_date = ? LIMIT 1",
                (report_date,)
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _get_scan_logs(days: int) -> list:
    try:
        since = (date.today() - timedelta(days=days)).isoformat()
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM scan_log WHERE scan_date >= ? ORDER BY scan_date DESC",
                (since,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _run_full_scan():
    """Corre scanner + decision engine via subprocess."""
    with st.spinner("A correr scanner e a avaliar candidatos..."):
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "scheduled_scan.py"],
                capture_output=True, text=True, timeout=180,
                cwd=str(Path(__file__).parent.parent.parent)
            )
            if result.returncode == 0:
                st.success("Scanner e Decision Engine concluidos!")
            else:
                st.error("Erro: " + result.stderr[:300])
        except Exception as e:
            st.error("Erro: " + str(e))


def _ensure_tables():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT, tickers_scanned INTEGER,
            candidates_found INTEGER, duration_seconds REAL,
            errors TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT, open_positions INTEGER,
            closed_today INTEGER, total_pnl_open REAL,
            stops_hit INTEGER, targets_hit INTEGER,
            errors INTEGER, summary_json TEXT, created_at TEXT
        );
        """)
