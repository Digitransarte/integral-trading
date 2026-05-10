"""Dashboard - Historico de Backtests"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd


def render():
    st.title("Historico de Backtests")

    try:
        from engine.database import get_backtest_history
        rows = get_backtest_history(limit=50)
    except Exception as e:
        st.error("Erro ao carregar historico: " + str(e))
        return

    if not rows:
        st.info("Ainda nao ha backtests guardados. Corre o primeiro em Backtest.")
        return

    df = pd.DataFrame(rows)

    # Formatar colunas
    df["win_rate"]      = df["win_rate"].map(lambda x: "{:.1f}%".format(x * 100))
    df["profit_factor"] = df["profit_factor"].map(lambda x: "{:.2f}".format(x))
    df["total_return"]  = df["total_return"].map(lambda x: "{:+.1f}%".format(x))
    df["max_drawdown"]  = df["max_drawdown"].map(lambda x: "{:.1f}%".format(x))
    df["run_date"]      = pd.to_datetime(df["run_date"]).dt.strftime("%Y-%m-%d %H:%M")

    st.dataframe(
        df[[
            "id", "strategy_name", "start_date", "end_date",
            "total_trades", "win_rate", "profit_factor",
            "total_return", "max_drawdown", "run_date",
        ]].rename(columns={
            "id":            "#",
            "strategy_name": "Estrategia",
            "start_date":    "Inicio",
            "end_date":      "Fim",
            "total_trades":  "Trades",
            "win_rate":      "Win Rate",
            "profit_factor": "PF",
            "total_return":  "Retorno",
            "max_drawdown":  "Max DD",
            "run_date":      "Data",
        }),
        use_container_width=True,
        hide_index=True,
    )
