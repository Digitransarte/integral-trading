"""Dashboard - Backtest"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests

try:
    from engine.data_feed import DataFeed
    from engine.backtester import Backtester, BacktestConfig
    from engine.strategies.ep_strategy import EpisodicPivotStrategy
    from engine.database import save_backtest
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

API_BASE = "http://localhost:8000"

UNIVERSES = {
    "Personalizado": [],

    # ── Universos pequenos (teste rápido) ─────────────────────────────────────
    "Small Cap Growth": [
        "RXRX", "HIMS", "ACHR", "JOBY", "RKLB", "ASTS", "LUNR",
        "SOUN", "BBAI", "IONQ",
    ],
    "S&P 500 Sample": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
        "ORCL", "NFLX", "ADBE", "CRM", "UBER", "ABNB", "SHOP", "SNOW",
    ],
    "ETFs": [
        "SPY", "QQQ", "IWM", "XLK", "XLV", "XLE", "XLF", "XBI", "SMH",
    ],

    # ── Universos expandidos (análise séria) ──────────────────────────────────
    "Biotech (20)": [
        "HIMS", "RXRX", "ACAD", "ARWR", "BEAM", "CRSP", "EDIT", "NTLA",
        "VERA", "GILD", "REGN", "BMRN", "SRPT", "FOLD", "RARE",
        "KRYS", "PTGX", "ALKS", "INCY", "PRME",
    ],
    "Space & Defense (14)": [
        "RKLB", "ASTS", "LUNR", "ACHR", "JOBY", "SPCE", "MNTS",
        "RDW", "KTOS", "RCAT", "AVAV", "PLTR", "LILM", "ARCHER",
    ],
    "AI & Quantum (18)": [
        "IONQ", "QBTS", "RGTI", "QUBT", "ARQQ", "SOUN", "BBAI",
        "GFAI", "IREN", "CORZ", "BTDR", "CIFR", "WULF",
        "SMCI", "NVTS", "ALAB", "MRVL", "ARM",
    ],
    "Crypto & Fintech (14)": [
        "COIN", "MSTR", "MARA", "RIOT", "CLSK", "BTBT", "HUT",
        "HOOD", "SQ", "AFRM", "UPST", "LC", "DAVE", "SOFI",
    ],
    "Clean Energy (14)": [
        "ENPH", "SEDG", "FSLR", "ARRY", "SHLS", "NOVA", "RUN",
        "BE", "PLUG", "FCEL", "BLDP", "EVGO", "CHPT", "BLNK",
    ],
    "Healthcare Devices (13)": [
        "INSP", "IRTC", "NVCR", "AXNX", "SWAV", "TMDX", "NARI",
        "OFIX", "ATRC", "IART", "MMSI", "LMAT", "NVST",
    ],

    # ── Universo completo (~100 tickers, demora 3-5 min) ─────────────────────
    "Universo Completo (~100)": sorted(set([
        "HIMS", "RXRX", "ACAD", "ARWR", "BEAM", "CRSP", "EDIT", "NTLA",
        "VERA", "GILD", "REGN", "BMRN", "SRPT", "FOLD", "RARE",
        "KRYS", "PTGX", "ALKS", "INCY",
        "RKLB", "ASTS", "LUNR", "ACHR", "JOBY", "SPCE", "MNTS",
        "RDW", "KTOS", "RCAT", "AVAV", "PLTR",
        "IONQ", "QBTS", "RGTI", "QUBT", "SOUN", "BBAI",
        "IREN", "CORZ", "BTDR", "SMCI", "NVTS", "ALAB", "MRVL", "ARM",
        "COIN", "MSTR", "MARA", "RIOT", "CLSK", "HUT",
        "HOOD", "SQ", "AFRM", "UPST", "LC", "SOFI",
        "ENPH", "SEDG", "FSLR", "ARRY", "NOVA", "RUN",
        "BE", "PLUG", "EVGO", "CHPT", "BLNK",
        "INSP", "IRTC", "NVCR", "SWAV", "TMDX",
        "CELH", "DUOL", "MNDY", "GLBE", "AXON",
        "CAVA", "BROS", "ELF", "APP", "IBKR",
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
    ])),
}


def render():
    st.title("Backtest")

    api_ok = _check_api()
    if api_ok:
        st.success("API online", icon="🟢")
    elif ENGINE_AVAILABLE:
        st.info("Modo dev - engine directo", icon="🔵")
    else:
        st.error("Engine nao disponivel: " + ENGINE_ERROR, icon="🔴")
        return

    st.markdown("---")

    with st.form("bt_form"):
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Estrategia**")
            strategy_label = st.selectbox(
                "s", ["Episodic Pivot (EP)", "CANSLIM"],
                label_visibility="collapsed",
            )

            st.markdown("**Universo**")
            univ = st.selectbox(
                "u", list(UNIVERSES.keys()),
                label_visibility="collapsed",
            )

            if univ == "Personalizado":
                tickers_raw = st.text_area(
                    "Tickers (separados por virgula ou linha)",
                    placeholder="AAPL, MSFT, NVDA",
                    height=90,
                    value="",
                )
            else:
                preset = UNIVERSES[univ]
                st.info(str(len(preset)) + " tickers: " + ", ".join(preset[:8]) +
                        ("..." if len(preset) > 8 else ""))
                tickers_raw = ""

        with c2:
            st.markdown("**Periodo**")
            d1c, d2c = st.columns(2)
            with d1c:
                date_start = st.date_input(
                    "Inicio",
                    value=datetime.today() - timedelta(days=365),
                )
            with d2c:
                date_end = st.date_input(
                    "Fim",
                    value=datetime.today(),
                )

            st.markdown("**Capital inicial ($)**")
            capital = st.number_input(
                "cap",
                value=10000,
                min_value=100,
                step=1000,
                label_visibility="collapsed",
            )

            next_day    = st.checkbox("Execucao no dia seguinte (mais realista)", value=True)
            show_trades = st.checkbox("Mostrar lista de trades", value=True)
            save_to_db  = st.checkbox("Guardar resultado no historico", value=True)

            # Aviso para universo grande
            if "Completo" in univ:
                st.warning("Universo completo demora 3-5 minutos.", icon="⏳")

        submitted = st.form_submit_button(
            "Correr Backtest", use_container_width=True, type="primary"
        )

    if not submitted:
        return

    if univ == "Personalizado":
        raw = tickers_raw.replace(",", " ")
        tickers = [t.strip().upper() for t in raw.split() if t.strip()]
    else:
        tickers = UNIVERSES[univ]

    if not tickers:
        st.error("Adiciona pelo menos um ticker.")
        return

    if "CANSLIM" in strategy_label:
        st.warning("CANSLIM ainda nao implementado - a usar EP.")

    with st.spinner("A correr backtest em " + str(len(tickers)) + " tickers..."):
        if api_ok:
            result = _run_via_api(
                "ep", tickers, str(date_start), str(date_end),
                float(capital), next_day,
            )
        else:
            result = _run_direct(
                tickers, date_start, date_end,
                float(capital), next_day, save_to_db,
            )

    if result:
        _show_results(result, show_trades)


def _run_direct(tickers, d1, d2, capital, next_day, save):
    try:
        feed = DataFeed(polygon_key=POLYGON_API_KEY)
        config = BacktestConfig(
            tickers=tickers,
            start_date=datetime.combine(d1, datetime.min.time()),
            end_date=datetime.combine(d2, datetime.min.time()),
            initial_capital=capital,
            next_day_execution=next_day,
        )
        summary = Backtester(feed, EpisodicPivotStrategy()).run(config)

        if save and summary.total_trades > 0:
            run_id = save_backtest(summary)
            st.toast("Guardado (ID #" + str(run_id) + ")", icon="💾")

        if summary.errors:
            with st.expander("Erros (" + str(len(summary.errors)) + ")"):
                for e in summary.errors:
                    st.text(e)

        trades_list = []
        for t in summary.trades:
            trades_list.append({
                "ticker":      t.ticker,
                "entry_date":  t.entry_date.strftime("%Y-%m-%d") if t.entry_date else None,
                "entry_price": round(t.entry_price, 2),
                "exit_date":   t.exit_date.strftime("%Y-%m-%d") if t.exit_date else None,
                "exit_price":  round(t.exit_price, 2) if t.exit_price else None,
                "exit_reason": t.exit_reason,
                "pnl_pct":     round(t.pnl_pct, 2),
                "days_held":   t.days_held,
            })

        return {
            "summary":      summary.to_dict(),
            "equity_curve": summary.equity_curve,
            "trades":       trades_list,
        }
    except Exception as e:
        st.error("Erro no engine: " + str(e))
        return None


def _run_via_api(strat, tickers, start, end, capital, next_day):
    try:
        r = requests.post(
            API_BASE + "/backtest/run",
            json={
                "strategy_name":      strat,
                "tickers":            tickers,
                "start_date":         start,
                "end_date":           end,
                "initial_capital":    capital,
                "next_day_execution": next_day,
            },
            timeout=300,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error("Erro API: " + str(e))
        return None


def _check_api():
    try:
        return requests.get(API_BASE + "/health", timeout=2).status_code == 200
    except Exception:
        return False


def _show_results(data, show_trades):
    s      = data["summary"]
    trades = data["trades"]
    equity = data["equity_curve"]

    st.markdown("---")
    st.subheader("Resultados")

    if not s.get("total_trades"):
        st.warning("Nenhum trade gerado. Tenta um periodo mais longo ou universo diferente.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trades",        s["total_trades"])
    c2.metric("Win Rate",      str(s["win_rate"]) + "%")
    c3.metric("Profit Factor", s["profit_factor"])
    c4.metric("Retorno",       str(s["total_return_pct"]) + "%",
              delta=str(s["total_return_pct"]) + "%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Avg Win",      str(s["avg_win_pct"]) + "%")
    c6.metric("Avg Loss",     str(s["avg_loss_pct"]) + "%")
    c7.metric("Max Drawdown", str(s["max_drawdown_pct"]) + "%")
    c8.metric("Avg Hold",     str(s["avg_hold_days"]) + " dias")

    if equity and len(equity) > 1:
        st.subheader("Equity Curve")
        eq_df = pd.DataFrame({
            "Trade":       list(range(len(equity))),
            "Capital ($)": equity,
        }).set_index("Trade")
        st.line_chart(eq_df)

        a, b, c = st.columns(3)
        a.metric("Capital Inicial", "${:,.2f}".format(equity[0]))
        b.metric("Capital Final",   "${:,.2f}".format(equity[-1]))
        c.metric("Ganho/Perda",     "${:+,.2f}".format(equity[-1] - equity[0]))

    if trades:
        st.subheader("Distribuicao P&L")
        st.bar_chart(pd.DataFrame({"P&L (%)": [t["pnl_pct"] for t in trades]}))

    if show_trades and trades:
        st.subheader("Trades (" + str(len(trades)) + ")")
        df = pd.DataFrame(trades)
        df = df.sort_values("pnl_pct", ascending=False).reset_index(drop=True)
        df["pnl_pct"] = df["pnl_pct"].map(lambda x: "{:+.1f}%".format(x))
        df = df.rename(columns={
            "ticker":      "Ticker",
            "entry_date":  "Entrada",
            "entry_price": "P. Entrada",
            "exit_date":   "Saida",
            "exit_price":  "P. Saida",
            "pnl_pct":     "P&L",
            "days_held":   "Dias",
            "exit_reason": "Razao",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

        csv_data = pd.DataFrame(trades).to_csv(index=False)
        filename = "backtest_" + datetime.today().strftime("%Y%m%d") + ".csv"
        st.download_button(
            "Download CSV",
            data=csv_data,
            file_name=filename,
            mime="text/csv",
        )
