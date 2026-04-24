"""Dashboard - Scanner EP em Tempo Real"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime

try:
    from engine.data_feed import DataFeed
    from engine.scanner import Scanner
    from engine.strategies.ep_strategy import EpisodicPivotStrategy
    from universes import DASHBOARD_UNIVERSES, MAIN_UNIVERSE
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

# Universos disponíveis para o scanner (exclui watchlists e ETFs)
SCANNER_UNIVERSES = {
    "Universo Principal (~55)": None,   # usa MAIN_UNIVERSE
    "Small Cap Growth (20)":    "Small Cap Growth (20)",
    "Space & Defense (8)":      "Space & Defense (8)",
    "AI & Tech (14)":           "AI & Tech (14)",
    "Mid Cap Momentum (9)":     "Mid Cap Momentum (9)",
    "Healthcare Devices (8)":   "Healthcare Devices (8)",
    "Personalizado":            "Personalizado",
}

WINDOW_COLOR = {
    "PRIME": "🟢",
    "OPEN":  "🟡",
    "LATE":  "🔴",
}


def render():
    st.title("Scanner EP")
    st.markdown("Detecta candidatos Episodic Pivot nos mercados actuais.")

    if not ENGINE_AVAILABLE:
        st.error("Engine nao disponivel: " + ENGINE_ERROR, icon="🔴")
        return

    st.markdown("---")

    # ── Configuração ──────────────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])

    with col1:
        univ_name = st.selectbox(
            "Universo",
            list(SCANNER_UNIVERSES.keys()),
        )

        tickers_raw = ""
        if univ_name == "Personalizado":
            tickers_raw = st.text_area(
                "Tickers (separados por virgula ou linha)",
                placeholder="HIMS, IONQ, RKLB, ASTS",
                height=80,
                value="",
            )
        else:
            # Resolver tickers do universo seleccionado
            universe_key = SCANNER_UNIVERSES[univ_name]
            if universe_key is None:
                preset = MAIN_UNIVERSE
            else:
                preset = DASHBOARD_UNIVERSES.get(universe_key, MAIN_UNIVERSE)
            st.caption(
                str(len(preset)) + " tickers: " +
                ", ".join(preset[:6]) +
                ("..." if len(preset) > 6 else "")
            )

    with col2:
        min_score = st.slider("Score mínimo", 0, 100, 60, step=5)
        top_n = st.number_input("Top candidatos", value=20, min_value=5, max_value=100)
        lookback = st.number_input("Dias de histórico", value=60, min_value=30, max_value=365)

    run_scan = st.button("🔍 Correr Scanner", type="primary", use_container_width=True)

    if not run_scan:
        # Mostrar info de último scan se existir
        if "last_scan" in st.session_state:
            st.markdown("---")
            st.caption("Último scan: " + st.session_state["last_scan_time"])
            _show_results(st.session_state["last_scan"], int(top_n), int(min_score))
        return

    # ── Resolver tickers ──────────────────────────────────────────────────────
    if univ_name == "Personalizado":
        raw = tickers_raw.replace(",", " ")
        tickers = [t.strip().upper() for t in raw.split() if t.strip()]
    else:
        universe_key = SCANNER_UNIVERSES[univ_name]
        tickers = MAIN_UNIVERSE if universe_key is None else DASHBOARD_UNIVERSES.get(universe_key, MAIN_UNIVERSE)

    if not tickers:
        st.error("Adiciona pelo menos um ticker.")
        return

    # ── Correr scanner ────────────────────────────────────────────────────────
    with st.spinner("A analisar " + str(len(tickers)) + " tickers..."):
        try:
            feed     = DataFeed(polygon_key=POLYGON_API_KEY)
            strategy = EpisodicPivotStrategy()
            strategy.min_score = min_score   # aplicar score mínimo configurado

            scanner = Scanner(feed, strategy)
            result  = scanner.run(tickers, lookback_days=int(lookback))

            # Guardar no session state para persistir
            st.session_state["last_scan"] = result
            st.session_state["last_scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        except Exception as e:
            st.error("Erro no scanner: " + str(e))
            return

    st.markdown("---")
    _show_results(result, int(top_n), int(min_score))


def _show_results(result, top_n, min_score):
    candidates = result.top(top_n)

    # ── Métricas do scan ──────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tickers Analisados", result.tickers_scanned)
    c2.metric("Candidatos EP",      result.total_candidates)
    c3.metric("Score Mínimo",       min_score)
    c4.metric("Tempo",              str(round(result.duration_seconds, 1)) + "s")

    if result.errors:
        with st.expander("Avisos de dados (" + str(len(result.errors)) + ")"):
            for e in result.errors:
                st.caption(e)

    if not candidates:
        st.info("Nenhum candidato EP encontrado com score >= " +
                str(min_score) + ". Tenta reduzir o score mínimo ou alargar o universo.")
        return

    st.markdown("---")

    # ── Tabela de candidatos ──────────────────────────────────────────────────
    st.subheader("Candidatos (" + str(len(candidates)) + ")")

    rows = []
    for c in candidates:
        rows.append({
            "Janela":     WINDOW_COLOR.get(c.entry_window, "") + " " + c.entry_window,
            "Score":      round(c.score, 0),
            "Ticker":     c.ticker,
            "Preco":      "$" + str(round(c.current_price, 2)),
            "Gap %":      str(round(c.gap_pct, 1)) + "%",
            "Vol x":      str(round(c.vol_ratio, 1)) + "x",
            "Stop":       "$" + str(round(c.stop_loss, 2)),
            "Target 1":   "$" + str(round(c.target_1, 2)),
            "Risco":      str(round(c.risk_pct, 1)) + "%",
            "Reward":     "+" + str(round(c.reward_pct, 1)) + "%",
            "Dias":       c.days_since_gap,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Detalhe dos top 3 ─────────────────────────────────────────────────────
    if candidates:
        st.markdown("---")
        st.subheader("Detalhe — Top 3")

        for c in candidates[:3]:
            window_icon = WINDOW_COLOR.get(c.entry_window, "")
            with st.expander(
                window_icon + " " + c.ticker +
                " — Score: " + str(round(c.score, 0)) +
                " | Gap: " + str(round(c.gap_pct, 1)) + "%" +
                " | " + c.entry_window,
                expanded=True,
            ):
                d1, d2, d3 = st.columns(3)
                d1.metric("Preco Actual", "$" + str(round(c.current_price, 2)))
                d2.metric("Gap",  str(round(c.gap_pct, 1)) + "%")
                d3.metric("Volume", str(round(c.vol_ratio, 1)) + "x média")

                d4, d5, d6 = st.columns(3)
                d4.metric("Stop Loss",  "$" + str(round(c.stop_loss, 2)),
                          delta="-" + str(round(c.risk_pct, 1)) + "%",
                          delta_color="inverse")
                d5.metric("Target 1",  "$" + str(round(c.target_1, 2)),
                          delta="+" + str(round(c.reward_pct, 1)) + "%")
                d6.metric("Target 2",  "$" + str(round(c.target_2, 2)))

                if c.signal.notes:
                    st.caption("Notas: " + c.signal.notes)
                st.caption(
                    "Janela: " + c.entry_window +
                    " (" + str(c.days_since_gap) + " dias desde o gap)" +
                    " | Scan: " + c.scan_date.strftime("%Y-%m-%d %H:%M UTC")
                )
