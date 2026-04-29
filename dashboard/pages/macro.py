"""Dashboard — Macro Dashboard (Ouro & Prata)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime

try:
    from engine.macro_analyzer import MacroAnalyzer
    from engine.data_feed import DataFeed
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)


def render():
    st.title("📊 Macro Dashboard")
    st.caption("Contexto macro para trading manual de Ouro (XAU/USD) e Prata (XAG/USD) no XTB.")

    if not ENGINE_AVAILABLE:
        st.error("Engine não disponível: " + ENGINE_ERROR)
        return

    col1, col2 = st.columns([3, 1])
    with col2:
        run = st.button("🔄 Analisar agora", use_container_width=True, type="primary")

    if "macro_result" not in st.session_state:
        st.session_state.macro_result = None

    if run or st.session_state.macro_result is None:
        with st.spinner("A analisar contexto macro..."):
            feed     = DataFeed(polygon_key=POLYGON_API_KEY)
            analyzer = MacroAnalyzer(feed)
            result   = analyzer.analyze()
            st.session_state.macro_result = result.to_dict()

    data = st.session_state.macro_result
    if not data:
        return

    st.markdown("---")

    # Bias principal
    bias  = data["bias"]
    score = data["score"]

    bias_config = {
        "BULLISH": {"icon": "🟢", "color": "#34D399", "desc": "Contexto macro favorável ao ouro/prata"},
        "BEARISH": {"icon": "🔴", "color": "#F87171", "desc": "Contexto macro desfavorável ao ouro/prata"},
        "NEUTRAL": {"icon": "🟡", "color": "#FBBF24", "desc": "Contexto macro neutro — aguardar alinhamento"},
    }
    cfg = bias_config.get(bias, bias_config["NEUTRAL"])

    st.markdown(f"""
    <div style="background:#0D1117;border:2px solid {cfg['color']}44;border-left:4px solid {cfg['color']};padding:1.2rem;margin-bottom:1.5rem">
        <div style="font-size:1.8rem;margin-bottom:0.2rem">{cfg['icon']} <span style="color:{cfg['color']};font-weight:bold;letter-spacing:0.1em">{bias}</span></div>
        <div style="color:#94A3B8;font-size:0.85rem">{cfg['desc']}</div>
    </div>
    """, unsafe_allow_html=True)

    # Setup alert
    if data.get("setup_alert"):
        st.warning(data["setup_alert"])

    # Métricas macro
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score", f"{score}/100")
    c2.metric("VIX", f"{data['vix_level']:.1f}", help="VIX > 25 = safe haven demand favorável ao ouro")
    c3.metric("Confiança", data["confidence"])
    c4.metric("Análise", data["date"][:10])

    st.markdown("---")

    # DXY e Yields
    st.subheader("📈 Filtros Macro")
    col1, col2 = st.columns(2)

    with col1:
        dxy = data["dxy"]
        trend_icon = "🟢" if dxy["trend"] == "BEARISH" else "🔴" if dxy["trend"] == "BULLISH" else "🟡"
        st.markdown(f"**DXY (Dólar Index)** {trend_icon}")
        st.caption("Correlação negativa com ouro — DXY baixo = ouro sobe")
        st.info(dxy["detail"])
        st.markdown(f"Sinal: *{dxy['signal']}*")

    with col2:
        yields = data["yields"]
        trend_icon = "🟢" if yields["trend"] == "BULLISH" else "🔴" if yields["trend"] == "BEARISH" else "🟡"
        st.markdown(f"**US Yields (TLT proxy)** {trend_icon}")
        st.caption("TLT sobe = yields caem = favorável ao ouro")
        st.info(yields["detail"])
        st.markdown(f"Sinal: *{yields['signal']}*")

    # VIX
    vix = data["vix_level"]
    if vix >= 35:
        st.error(f"⚠️ VIX extremo: {vix:.1f} — forte procura por safe haven (ouro)")
    elif vix >= 25:
        st.warning(f"⚠️ VIX elevado: {vix:.1f} — safe haven demand presente")
    else:
        st.success(f"✅ VIX controlado: {vix:.1f}")

    st.markdown("---")

    # Estrutura de mercado
    st.subheader("🕯️ Estrutura de Mercado (Jayce SMC)")

    col1, col2 = st.columns(2)

    for col, asset_key, name, emoji in [
        (col1, "gold",   "Ouro (GLD proxy)",   "🥇"),
        (col2, "silver", "Prata (SLV proxy)",  "🥈"),
    ]:
        with col:
            asset = data[asset_key]
            trend = asset["trend"]
            setup = asset["setup"]

            trend_color = "#34D399" if trend == "UPTREND" else "#F87171" if trend == "DOWNTREND" else "#FBBF24"
            trend_icon  = "⬆️" if trend == "UPTREND" else "⬇️" if trend == "DOWNTREND" else "↔️"

            st.markdown(f"**{emoji} {name}**")
            st.markdown(f"""
            <div style="background:#0D1117;border:1px solid {trend_color}33;border-left:3px solid {trend_color};padding:0.8rem;margin-bottom:0.5rem">
                <div style="color:{trend_color};font-size:0.8rem;letter-spacing:0.1em">{trend_icon} {trend}</div>
                <div style="font-size:1.3rem;font-weight:bold;margin:0.2rem 0">${asset['price']:.2f}</div>
                <div style="font-size:0.75rem;color:#64748B">SMA20: ${asset['sma20']:.2f} | SMA50: ${asset['sma50']:.2f}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            | Zona | Nível |
            |------|-------|
            | 🎯 Key Level | ${asset['key_level']:.2f} |
            | ⬆️ Recent High | ${asset['recent_high']:.2f} |
            | ⬇️ Recent Low | ${asset['recent_low']:.2f} |
            | 📏 Dist. Key Level | {asset['distance_to_kl']:.1f}% |
            """)

            if setup == "NEAR_KEY_LEVEL":
                st.warning(f"⚡ Perto do Key Level — potencial setup de entrada")
            elif setup == "EXTENDED":
                st.info("📏 Preço estendido — aguardar pullback para key level")

    st.markdown("---")

    # Sinais
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("✅ Sinais Bullish")
        if data["signals_bullish"]:
            for s in data["signals_bullish"]:
                st.success(s)
        else:
            st.info("Nenhum sinal bullish")

    with col2:
        st.subheader("🔴 Sinais Bearish")
        if data["signals_bearish"]:
            for s in data["signals_bearish"]:
                st.error(s)
        else:
            st.success("Nenhum sinal bearish")

    st.markdown("---")

    # Checklist de entrada (SMC)
    with st.expander("📋 Entry Checklist (Jayce SMC — 9 passos)", expanded=False):
        st.markdown("""
1. ✅ Definir estrutura do mercado (HH/HL ou LH/LL) — timeframe maior
2. ✅ Identificar key level ou Order Block onde entrar
3. ✅ Analisar momentum (grupo de candles + volume de ondas)
4. ✅ Aguardar preço chegar à zona
5. ✅ Confirmar com candle pattern (Marubozu/Engulfing forte + volume)
6. ✅ Definir stop loss (abaixo/acima da key zone)
7. ✅ Calcular TP e verificar RR >= 2.5x
8. ✅ Verificar se há zonas de risco antes do TP
9. ✅ Calcular lot size (máx. 2% risco da conta)

**Macro alinhado quando:**
- DXY em downtrend ✓
- TLT em uptrend (yields a cair) ✓
- VIX > 25 (safe haven demand) ✓
- Ouro em uptrend acima do key level ✓
        """)

    st.caption("Dados: GLD/SLV/UUP/TLT via yfinance. Proxy — não são preços reais de XAU/USD e XAG/USD.")
