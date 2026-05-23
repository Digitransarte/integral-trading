"""Dashboard — Regime de Mercado (Camada 01)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime

try:
    from engine.regime_detector import RegimeDetector
    from engine.data_feed import DataFeed
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)


def render():
    st.title("📡 Regime de Mercado")
    st.caption("Camada 01 — Devo estar no mercado? O scanner só corre em modo OFENSIVO.")

    if not ENGINE_AVAILABLE:
        st.error("Engine não disponível: " + ENGINE_ERROR)
        return

    # Botão de análise
    col1, col2 = st.columns([3, 1])
    with col2:
        run = st.button("🔄 Analisar agora", use_container_width=True, type="primary")

    # Cache do último resultado na sessão
    if "regime_result" not in st.session_state:
        st.session_state.regime_result = None

    if run or st.session_state.regime_result is None:
        with st.spinner("A analisar mercado..."):
            feed     = DataFeed(polygon_key=POLYGON_API_KEY)
            detector = RegimeDetector(feed)
            result   = detector.detect()
            st.session_state.regime_result = result.to_dict()

    data = st.session_state.regime_result
    if not data:
        return

    st.markdown("---")

    # Modo principal
    mode  = data["mode"]
    score = data["score"]

    mode_config = {
        "OFFENSIVE": {"icon": "🟢", "label": "OFENSIVO",  "color": "#34D399", "desc": "Scanner activo. Novas posições permitidas."},
        "DEFENSIVE": {"icon": "🟡", "label": "DEFENSIVO", "color": "#FBBF24", "desc": "Scanner pausado. Gerir posições existentes."},
        "CASH":      {"icon": "🔴", "label": "CASH",      "color": "#F87171", "desc": "Sistema parado. Zero novas posições."},
    }
    cfg = mode_config.get(mode, mode_config["DEFENSIVE"])

    # Card principal
    st.markdown(f"""
    <div style="
        background: #0D1117;
        border: 2px solid {cfg['color']}44;
        border-left: 4px solid {cfg['color']};
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    ">
        <div style="font-size: 2rem; margin-bottom: 0.3rem">{cfg['icon']} <span style="color:{cfg['color']};font-weight:bold;letter-spacing:0.1em">{cfg['label']}</span></div>
        <div style="color: #94A3B8; font-size: 0.9rem">{cfg['desc']}</div>
    </div>
    """, unsafe_allow_html=True)

    # Score + métricas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score", f"{score}/100")
    c2.metric("VIX", f"{data['vix_level']:.1f}", delta=None)
    c3.metric("Breadth", f"{data['breadth_pct']:.0f}%")
    c4.metric("Análise", data["date"][:10])

    st.markdown("---")

    # SPY e QQQ
    st.subheader("Índices principais")
    col1, col2 = st.columns(2)

    with col1:
        spy_ok = data["spy_above_sma200"]
        st.markdown(f"""
        **SPY** {"✅" if spy_ok else "❌"}
        - Preço: ${data['spy_price']:.2f}
        - SMA 200: ${data['spy_sma200']:.2f}
        - {"Acima" if spy_ok else "Abaixo"} da SMA200
        """)

    with col2:
        qqq_ok = data["qqq_above_sma200"]
        st.markdown(f"""
        **QQQ** {"✅" if qqq_ok else "❌"}
        - Preço: ${data['qqq_price']:.2f}
        - SMA 200: ${data['qqq_sma200']:.2f}
        - {"Acima" if qqq_ok else "Abaixo"} da SMA200
        """)

    st.markdown("---")

    # Sinais e avisos
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("✅ Sinais positivos")
        if data["signals"]:
            for s in data["signals"]:
                st.success(s)
        else:
            st.info("Nenhum sinal positivo")

    with col2:
        st.subheader("⚠️ Avisos")
        if data["warnings"]:
            for w in data["warnings"]:
                st.warning(w)
        else:
            st.success("Sem avisos")

    st.markdown("---")

    # Regra imutável
    st.markdown("""
    <div style="
        background: #15100A;
        border: 1px solid #3A2A1022;
        border-left: 3px solid #FBBF24;
        padding: 0.8rem 1rem;
        font-size: 0.8rem;
        color: #78716C;
    ">
    <span style="color:#FBBF24">⚠ REGRA IMUTÁVEL</span> —
    Regime DEFENSIVO ou CASH paralisa o sistema inteiro. Nenhuma camada pode ser saltada.
    </div>
    """, unsafe_allow_html=True)
