"""Integral Trading — Dashboard v0.7.0"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.set_page_config(
    page_title="Integral Trading",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }
    </style>
""", unsafe_allow_html=True)

st.sidebar.markdown("## ◈ Integral Trading")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "",
    ["Dashboard", "Scanner", "Posicoes", "Especialistas",
     "Automacao", "Aprendizagem", "Backtest", "Historico"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption("v0.7.0 — paper trading")

if page == "Dashboard":
    st.title("◈ Integral Trading")
    try:
        from engine.forward_tracker import ForwardTracker
        from engine.data_feed import DataFeed
        from engine.database import get_conn, init_db
        from config import POLYGON_API_KEY
        from datetime import date

        tracker  = ForwardTracker(DataFeed(polygon_key=POLYGON_API_KEY))
        open_pos = tracker.get_open_positions()
        stats    = tracker.get_stats()

        init_db()
        today = date.today().isoformat()
        try:
            with get_conn() as conn:
                scan_today = conn.execute(
                    "SELECT candidates_found FROM scan_log WHERE scan_date = ? LIMIT 1",
                    (today,)
                ).fetchone()
            candidatos_hoje = scan_today["candidates_found"] if scan_today else "-"
        except Exception:
            candidatos_hoje = "-"

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Posicoes Abertas",  len(open_pos))
        c2.metric("Win Rate",          str(stats["win_rate"]) + "%" if stats["total_closed"] else "-")
        c3.metric("Profit Factor",     stats["profit_factor"] if stats["total_closed"] else "-")
        c4.metric("Posicoes Fechadas", stats["total_closed"])
        c5.metric("Candidatos Hoje",   candidatos_hoje)

        if open_pos:
            st.markdown("---")
            st.subheader("Posicoes Abertas")
            for p in open_pos:
                icon = "🟢" if p.pnl_pct >= 0 else "🔴"
                st.write(
                    icon + " **" + p.ticker + "**" +
                    "  $" + str(round(p.current_price, 2)) +
                    "  " + "{:+.1f}%".format(p.pnl_pct) +
                    "  Dia " + str(p.days_held) + "/20"
                )
        else:
            st.markdown("---")
            st.info("Nenhuma posicao aberta. Usa o **Scanner** ou **Automacao** para encontrar candidatos.")
    except Exception:
        for col in st.columns(5):
            col.metric("-", "-")

elif page == "Scanner":
    from pages.scanner import render
    render()

elif page == "Posicoes":
    from pages.positions import render
    render()

elif page == "Especialistas":
    from pages.strategy_chat import render
    render()

elif page == "Automacao":
    from pages.notifications import render
    render()

elif page == "Aprendizagem":
    from pages.learning_page import render
    render()

elif page == "Backtest":
    from pages.backtest import render
    render()

elif page == "Historico":
    from pages.history import render
    render()
