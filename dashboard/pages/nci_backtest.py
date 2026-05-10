"""Dashboard — NCI Backtesting"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

try:
    from engine.nci_backtester import NCIBacktester
    from engine.data_feed import DataFeed
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

# Tickers disponíveis para backtest
BACKTEST_TICKERS = {
    "Ouro (GC=F)":     "GC=F",
    "Prata (SI=F)":    "SI=F",
    "Petróleo WTI (CL=F)": "CL=F",
    "Gás Natural (NG=F)":  "NG=F",
    "Cobre (HG=F)":    "HG=F",
    "EUR/USD":         "EURUSD=X",
    "GBP/USD":         "GBPUSD=X",
    "USD/JPY":         "USDJPY=X",
    "AUD/USD":         "AUDUSD=X",
}


def render():
    st.title("◈ NCI — Backtesting")
    st.caption("Walk-forward backtesting da estratégia NCI/SMC.")

    if not ENGINE_AVAILABLE:
        st.error("Engine não disponível: " + ENGINE_ERROR)
        return

    # ── Configuração ──────────────────────────────────────────────────────────

    col_cfg, col_main = st.columns([1, 3])

    with col_cfg:
        st.markdown("#### Configuração")

        ticker_name = st.selectbox("Activo", list(BACKTEST_TICKERS.keys()))
        ticker      = BACKTEST_TICKERS[ticker_name]

        mode = st.radio(
            "Modo",
            ["MTF (Daily+H4+H1)", "Daily only"],
            help="MTF: mais preciso, últimos 2 anos. Daily: histórico longo.",
        )
        mode_key = "mtf" if "MTF" in mode else "daily"

        years = st.slider(
            "Anos de histórico",
            min_value=1, max_value=5, value=2,
            help="MTF: limitado a 2 anos (limite yfinance H1). Para mais histórico usa Daily only.",
        )
        if mode_key == "mtf" and years > 2:
            st.caption("⚠️ MTF limitado a 2 anos. Para " + str(years) + " anos usa **Daily only**.")

        min_score = st.slider(
            "Score mínimo para entrada",
            min_value=20, max_value=90, value=30, step=5,
        )

        trailing_pct = st.slider(
            "Trailing stop (%)",
            min_value=0.0, max_value=5.0, value=2.0, step=0.5,
            help="% de recuo do máximo para sair. 0 = timeout fixo.",
        )

        direction_filter = st.radio(
            "Direcção",
            ["ALL", "LONG", "SHORT"],
            index=1,
            horizontal=True,
            help="LONG only elimina shorts com baixo WR.",
        )

        st.markdown("---")
        run = st.button("▶ Correr backtest", use_container_width=True, type="primary")

        if "nci_bt_last" in st.session_state:
            st.caption("Último: " + st.session_state.nci_bt_last)

    # ── Execução ──────────────────────────────────────────────────────────────

    cache_key = "nci_bt_" + ticker + "_" + mode_key + "_" + str(years) + "_" + str(min_score) + "_t" + str(trailing_pct) + "_d" + direction_filter + "_d" + direction_filter

    if run:
        with col_main:
            with st.spinner("A correr backtest " + ticker_name + " (" + mode_key + ")..."):
                try:
                    feed      = DataFeed(polygon_key=POLYGON_API_KEY)
                    backtester = NCIBacktester(feed)
                    backtester.TRAILING_STOP_PCT = trailing_pct
                    backtester.DIRECTION_FILTER  = direction_filter
                    result = backtester.run(
                        ticker=ticker,
                        mode=mode_key,
                        years=years,
                        min_score=min_score,
                    )
                    st.session_state[cache_key]  = result
                    st.session_state["nci_bt_last"] = ticker_name + " " + mode_key
                except Exception as e:
                    st.error("Erro: " + str(e))
                    return

    result = st.session_state.get(cache_key)

    # ── Resultados ────────────────────────────────────────────────────────────

    with col_main:
        if result is None:
            st.info("Configura os parâmetros e clica **▶ Correr backtest**.")
            return

        if result.total_trades == 0:
            st.warning("Nenhum trade encontrado com score ≥ " + str(min_score) + ".")

            diag = result.params.get("_diag", {})
            if diag:
                st.markdown("**Diagnóstico — o que aconteceu a cada barra:**")
                d1, d2, d3, d4, d5 = st.columns(5)
                d1.metric("Barras analisadas", diag.get("bars_total", 0))
                d2.metric("Signal None",  diag.get("signal_none", 0),
                          help="Daily RANGING ou sem dados suficientes")
                d3.metric("Score baixo",  diag.get("score_low", 0),
                          help="Score abaixo do mínimo definido")
                d4.metric("Stop zero",   diag.get("stop_zero", 0),
                          help="Stop ou target calculados como 0")
                d5.metric("Entradas",    diag.get("entered", 0))

                total = diag.get("bars_total", 1)
                none_pct = round(diag.get("signal_none", 0) / total * 100)
                st.caption(
                    str(none_pct) + "% das barras sem sinal. " +
                    ("Mercado maioritariamente RANGING — tenta modo Daily only." if none_pct > 70
                     else "Reduz o score mínimo para ver trades.")
                )
                score_low = diag.get("score_low", 0)
                if score_low > 0:
                    st.info(
                        str(score_low) + " barras têm sinal válido mas score < " + str(min_score) +
                        ". Experimenta score mínimo de **25-30**."
                    )
            return

        rd = result.to_dict()

        # ── Métricas principais ───────────────────────────────────────────────

        st.markdown("### " + ticker_name + " · " + rd["mode"].upper() +
                    " · " + rd["start_date"] + " → " + rd["end_date"])

        # Linha 1 — resultados chave
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Trades",        result.total_trades)
        c2.metric("Win Rate",      str(result.win_rate) + "%",
                  delta=str(result.win_rate - 50) + "pp vs 50%")
        c3.metric("Profit Factor", result.profit_factor)
        c4.metric("Expectancy",    str(result.expectancy_r) + "R")
        c5.metric("Retorno Total", str(result.total_return) + "%")
        c6.metric("Max Drawdown",  str(result.max_drawdown) + "%")

        # Linha 2 — detalhes
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Wins / Losses", str(result.wins) + " / " + str(result.losses))
        c2.metric("Avg Win",  str(result.avg_win_pct) + "%")
        c3.metric("Avg Loss", str(result.avg_loss_pct) + "%")
        c4.metric("Avg Bars",  str(result.avg_bars_held) + "d")

        st.markdown("---")

        # ── Equity curve ──────────────────────────────────────────────────────

        st.markdown("##### Equity Curve (capital normalizado a 100)")

        eq = result.equity_curve
        if len(eq) > 1:
            eq_df = pd.DataFrame({
                "Trade":   list(range(len(eq))),
                "Capital": eq,
            }).set_index("Trade")
            st.line_chart(eq_df, height=220)

        st.markdown("---")

        # ── Breakdown por qualidade e direcção ────────────────────────────────

        trades_df = result.trades_to_df()

        col_q, col_d, col_ex = st.columns(3)

        with col_q:
            st.markdown("**Por qualidade do setup**")
            for quality in ["A+", "A", "B", "C"]:
                t_q = [t for t in result.trades if t.setup_quality == quality]
                if t_q:
                    wr = round(sum(1 for t in t_q if t.is_win) / len(t_q) * 100, 0)
                    st.caption(quality + ": " + str(len(t_q)) + " trades · " + str(int(wr)) + "% WR")

        with col_d:
            st.markdown("**Por direcção**")
            for direction in ["LONG", "SHORT"]:
                t_d = [t for t in result.trades if t.direction == direction]
                if t_d:
                    wr = round(sum(1 for t in t_d if t.is_win) / len(t_d) * 100, 0)
                    st.caption(direction + ": " + str(len(t_d)) + " trades · " + str(int(wr)) + "% WR")

        with col_ex:
            st.markdown("**Por saída**")
            for reason in ["TARGET", "TRAILING", "STOP", "TIMEOUT"]:
                t_e = [t for t in result.trades if t.exit_reason == reason]
                if t_e:
                    avg = round(float(sum(t.pnl_pct for t in t_e) / len(t_e)), 2)
                    st.caption(reason + ": " + str(len(t_e)) + " · avg " + str(avg) + "%")

        st.markdown("---")

        # ── BOS e Manipulação ─────────────────────────────────────────────────

        col_b, col_m = st.columns(2)

        with col_b:
            st.markdown("**BOS confirmado vs pendente**")
            bos_yes = [t for t in result.trades if t.bos_confirmed]
            bos_no  = [t for t in result.trades if not t.bos_confirmed]
            if bos_yes:
                wr = round(sum(1 for t in bos_yes if t.is_win) / len(bos_yes) * 100, 0)
                st.caption("Com BOS: " + str(len(bos_yes)) + " trades · " + str(int(wr)) + "% WR")
            if bos_no:
                wr = round(sum(1 for t in bos_no if t.is_win) / len(bos_no) * 100, 0)
                st.caption("Sem BOS: " + str(len(bos_no)) + " trades · " + str(int(wr)) + "% WR")

        with col_m:
            st.markdown("**Manipulação detectada**")
            manip_yes = [t for t in result.trades if t.manipulation]
            manip_no  = [t for t in result.trades if not t.manipulation]
            if manip_yes:
                wr = round(sum(1 for t in manip_yes if t.is_win) / len(manip_yes) * 100, 0)
                st.caption("Com manip: " + str(len(manip_yes)) + " trades · " + str(int(wr)) + "% WR")
            if manip_no:
                wr = round(sum(1 for t in manip_no if t.is_win) / len(manip_no) * 100, 0)
                st.caption("Sem manip: " + str(len(manip_no)) + " trades · " + str(int(wr)) + "% WR")

        st.markdown("---")

        # ── Trade log ─────────────────────────────────────────────────────────

        with st.expander("Trade log completo (" + str(result.total_trades) + " trades)"):
            if not trades_df.empty:
                # Colorir wins/losses
                def color_pnl(val):
                    if isinstance(val, (int, float)):
                        return "color: #34D399" if val > 0 else "color: #F87171"
                    return ""

                st.dataframe(
                    trades_df.style.map(color_pnl, subset=["PnL%", "R"]),
                    use_container_width=True,
                    hide_index=True,
                )

        # ── Parâmetros usados ─────────────────────────────────────────────────

        with st.expander("Parâmetros do backtest"):
            params = rd["params"]
            c1, c2, c3, c4 = st.columns(4)
            c1.caption("Modo: " + params.get("mode", "—"))
            c2.caption("Min score: " + str(params.get("min_score", "—")))
            c3.caption("Pivot strength: " + str(params.get("pivot_str", "—")))
            c4.caption("Pullback zone: " + str(params.get("pullback%", "—")) + "%")
            c1.caption("Min R:R: " + str(params.get("min_rr", "—")))
            c2.caption("BOS obrigatório: " + str(params.get("bos_req", "—")))
            c3.caption("Anos: " + str(params.get("years", "—")))
