"""Integral Trading — NCI Dashboard v1.0.0"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

st.set_page_config(
    page_title="Integral Trading — NCI",
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
st.sidebar.markdown("### NCI")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "",
    ["Relatório", "NCI", "Relações", "Notícias","NCI Backtest", "NCI Study", "Alertas", "Posicoes", "Diario"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption("v1.0.0 — NCI · paper trading")

if page == "NCI":
    from pages.nci import render
    render()

elif page == "Relatório":
    from pages.relatorio import render
    render()   

elif page == "Relações":
    from pages.relacoes import render
    render() 

elif page == "Notícias":
    from pages.noticias import render
    render()

elif page == "NCI Backtest":
    from pages.nci_backtest import render
    render()

elif page == "NCI Study":
    from pages.nci_study import render
    render()

elif page == "Alertas":
    from pages.alerts import render
    render()

elif page == "Posicoes":
    from pages.positions import render
    render()

elif page == "Diario":
    from pages.diary import render
    render()
