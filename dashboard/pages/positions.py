"""Dashboard - Posições / Forward Tracker"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime

try:
    from engine.data_feed import DataFeed
    from engine.forward_tracker import ForwardTracker
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)


def render():
    st.title("Posições — Forward Tracker")

    if not ENGINE_AVAILABLE:
        st.error("Engine nao disponivel: " + ENGINE_ERROR, icon="🔴")
        return

    feed    = DataFeed(polygon_key=POLYGON_API_KEY)
    tracker = ForwardTracker(feed)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["Abertas", "Fechadas", "Abrir Posição"])

    # ── Tab 1: Posições abertas ───────────────────────────────────────────────
    with tab1:
        col_title, col_btn = st.columns([3, 1])
        with col_title:
            st.subheader("Posições Abertas")
        with col_btn:
            if st.button("🔄 Actualizar Preços", use_container_width=True):
                with st.spinner("A actualizar..."):
                    summary = tracker.update_all()
                msg = ("Actualizadas: " + str(summary.updated) +
                       " | Stops: " + str(summary.stopped_out) +
                       " | Targets: " + str(summary.target_hit))
                st.success(msg)
                if summary.closed_positions:
                    for c in summary.closed_positions:
                        icon = "✅" if c["pnl_pct"] > 0 else "❌"
                        st.info(icon + " " + c["ticker"] + " fechada | " +
                                c["reason"] + " | " + str(c["pnl_pct"]) + "%")
                st.rerun()

        open_positions = tracker.get_open_positions()

        if not open_positions:
            st.info("Nenhuma posição aberta. Abre uma na tab **Abrir Posição**.")
        else:
            # Métricas resumo
            pnls = [p.pnl_pct for p in open_positions]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Posições Abertas", len(open_positions))
            c2.metric("P&L Médio", "{:+.1f}%".format(sum(pnls) / len(pnls)))
            c3.metric("Melhor",    "{:+.1f}%".format(max(pnls)))
            c4.metric("Pior",      "{:+.1f}%".format(min(pnls)))

            st.markdown("---")

            # Tabela de posições
            for pos in open_positions:
                _render_position_card(pos, tracker)

    # ── Tab 2: Posições fechadas ──────────────────────────────────────────────
    with tab2:
        st.subheader("Histórico de Posições")

        closed = tracker.get_closed_positions(limit=100)

        if not closed:
            st.info("Nenhuma posição fechada ainda.")
        else:
            stats = tracker.get_stats()
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total Fechadas",  stats["total_closed"])
            c2.metric("Win Rate",        str(stats["win_rate"]) + "%")
            c3.metric("Profit Factor",   stats["profit_factor"])
            c4.metric("Avg Win",         str(stats["avg_win"]) + "%")
            c5.metric("Avg Loss",        str(stats["avg_loss"]) + "%")

            st.markdown("---")

            rows = []
            for p in closed:
                rows.append({
                    "":          "✅" if p.pnl_pct > 0 else "❌",
                    "Ticker":    p.ticker,
                    "Estrategia": p.strategy_name,
                    "Entrada":   p.entry_date,
                    "P. Entrada": "$" + str(round(p.entry_price, 2)),
                    "Saida":     p.exit_date or "-",
                    "P. Saida":  "$" + str(round(p.exit_price, 2)) if p.exit_price else "-",
                    "P&L":       "{:+.1f}%".format(p.pnl_pct),
                    "Dias":      p.days_held,
                    "Razao":     p.exit_reason,
                })

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            csv = pd.DataFrame(rows).to_csv(index=False)
            st.download_button(
                "Download CSV",
                data=csv,
                file_name="posicoes_" + datetime.today().strftime("%Y%m%d") + ".csv",
                mime="text/csv",
            )

    # ── Tab 3: Abrir posição ──────────────────────────────────────────────────
    with tab3:
        st.subheader("Registar Nova Posição")
        st.caption("Usa isto para registar manualmente uma posição aberta.")

        with st.form("open_position_form"):
            col1, col2 = st.columns(2)

            with col1:
                ticker   = st.text_input("Ticker", placeholder="HIMS").upper()
                strategy = st.selectbox("Estrategia", ["EP", "CANSLIM", "Manual"])
                catalyst = st.text_input("Catalisador", placeholder="Earnings beat Q1 2026")

            with col2:
                entry_price = st.number_input("Preco de Entrada ($)", min_value=0.01, value=10.00, step=0.01)
                stop_price  = st.number_input("Stop Loss ($)",         min_value=0.01, value=9.00,  step=0.01)
                target_1    = st.number_input("Target 1 ($)",          min_value=0.01, value=11.50, step=0.01)
                target_2    = st.number_input("Target 2 ($)",          min_value=0.01, value=13.00, step=0.01)

            # Calcular risco/reward automaticamente
            if entry_price > 0 and stop_price > 0 and target_1 > 0:
                risk   = abs(entry_price - stop_price) / entry_price * 100
                reward = abs(target_1 - entry_price) / entry_price * 100
                rr     = reward / risk if risk > 0 else 0
                st.caption(
                    "Risco: -{:.1f}%  |  Reward: +{:.1f}%  |  R/R: {:.2f}".format(
                        risk, reward, rr)
                )

            submitted = st.form_submit_button(
                "Abrir Posição", use_container_width=True, type="primary"
            )

        if submitted:
            if not ticker:
                st.error("Introduz um ticker.")
            elif stop_price >= entry_price:
                st.error("Stop loss deve ser inferior ao preco de entrada.")
            elif target_1 <= entry_price:
                st.error("Target 1 deve ser superior ao preco de entrada.")
            else:
                pos_id = tracker.open_position(
                    ticker=ticker,
                    strategy=strategy,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    target_1=target_1,
                    target_2=target_2,
                    catalyst=catalyst,
                )
                st.success("Posição aberta: " + ticker +
                           " @ $" + str(round(entry_price, 2)) +
                           " (ID #" + str(pos_id) + ")")
                st.rerun()


def _render_position_card(pos, tracker):
    """Renderiza um card para uma posição aberta."""
    pnl_color = "🟢" if pos.pnl_pct >= 0 else "🔴"

    with st.expander(
        pnl_color + " " + pos.ticker +
        "  |  " + pos.strategy_name +
        "  |  P&L: " + "{:+.1f}%".format(pos.pnl_pct) +
        "  |  Dia " + str(pos.days_held) + "/20",
        expanded=pos.pnl_pct > 5,
    ):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preco Actual",   "$" + str(round(pos.current_price, 2)))
        c2.metric("Entrada",        "$" + str(round(pos.entry_price, 2)))
        c3.metric("P&L",            "{:+.1f}%".format(pos.pnl_pct),
                  delta="{:+.1f}%".format(pos.pnl_pct))
        c4.metric("Dias em posição", str(pos.days_held) + " / 20")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Stop Loss",   "$" + str(round(pos.stop_price, 2)),
                  delta="-{:.1f}%".format(pos.distance_to_stop),
                  delta_color="inverse")
        c6.metric("Target 1",    "$" + str(round(pos.target_1, 2)),
                  delta="+{:.1f}%".format(pos.distance_to_target1))
        c7.metric("Target 2",    "$" + str(round(pos.target_2, 2)))
        c8.metric("R/R",         str(round(pos.risk_reward, 2)))

        if pos.catalyst:
            st.caption("Catalisador: " + pos.catalyst)

        # Barra de progresso stop → entrada → target
        if pos.stop_price > 0 and pos.target_1 > 0:
            total_range = pos.target_1 - pos.stop_price
            current_pos = pos.current_price - pos.stop_price
            progress    = max(0.0, min(1.0, current_pos / total_range))
            st.progress(progress, text="Stop → Target 1")

        # Botão fechar
        col_close, col_space = st.columns([1, 3])
        with col_close:
            if st.button("Fechar Posição", key="close_" + str(pos.id)):
                tracker.close_position(pos.id, reason="manual")
                st.success(pos.ticker + " fechada.")
                st.rerun()
