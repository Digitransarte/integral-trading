"""Dashboard — NCI Briefing Diário"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime

try:
    from engine.nci_analyzer import NCIAnalyzer
    from engine.data_feed import DataFeed
    from universes import (
        COMMODITIES_UNIVERSE, FOREX_UNIVERSE, FOREX_MAJORS,
        METAIS_UNIVERSE, ENERGIA_UNIVERSE, AGRICOLAS_UNIVERSE,
        get_commodity_name, get_forex_name,
    )
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

# ── Universos disponíveis para o NCI scanner ─────────────────────────────────

NCI_UNIVERSES = {
    "Metais Preciosos (4)":    METAIS_UNIVERSE if ENGINE_AVAILABLE else [],
    "Energia (5)":             ENERGIA_UNIVERSE if ENGINE_AVAILABLE else [],
    "Agrícolas (6)":           AGRICOLAS_UNIVERSE if ENGINE_AVAILABLE else [],
    "Commodities — todas (17)": COMMODITIES_UNIVERSE if ENGINE_AVAILABLE else [],
    "Forex Majors (7)":        FOREX_MAJORS if ENGINE_AVAILABLE else [],
    "Forex — todos (15)":      FOREX_UNIVERSE if ENGINE_AVAILABLE else [],
}

# ── Helpers visuais ───────────────────────────────────────────────────────────

QUALITY_CONFIG = {
    "A+": {"color": "#34D399", "icon": "🟢", "label": "A+"},
    "A":  {"color": "#6EE7B7", "icon": "🟢", "label": "A"},
    "B":  {"color": "#FBBF24", "icon": "🟡", "label": "B"},
    "C":  {"color": "#F97316", "icon": "🟠", "label": "C"},
    "NONE": {"color": "#475569", "icon": "⚪", "label": "—"},
}

DIRECTION_CONFIG = {
    "LONG":  {"color": "#34D399", "label": "LONG  ▲"},
    "SHORT": {"color": "#F87171", "label": "SHORT ▼"},
    "NONE":  {"color": "#475569", "label": "NONE"},
}

TREND_ICON = {
    "UPTREND":   "↑",
    "DOWNTREND": "↓",
    "RANGING":   "→",
}

def _ticker_label(ticker: str) -> str:
    """Nome legível de um ticker."""
    name = get_commodity_name(ticker)
    if name == ticker:
        name = get_forex_name(ticker)
    # Simplificar — mostrar só o nome sem o ticker técnico
    if name != ticker:
        return name.split("(")[0].strip()
    return ticker.replace("=X", "").replace("=F", "")


def _render_signal_card(sig_dict: dict):
    """Renderiza um card de sinal NCI — f-string directa, sem concatenação."""
    ticker    = sig_dict["ticker"]
    quality   = sig_dict["setup_quality"]
    score     = sig_dict["confluence_score"]
    direction = sig_dict["direction"]
    active    = sig_dict["setup_active"]
    entry     = sig_dict["entry_price"]
    stop      = sig_dict["stop_loss"]
    t1        = sig_dict["target_1"]
    rr        = sig_dict["risk_reward"]
    alerts    = sig_dict.get("alerts", [])
    daily_t   = sig_dict.get("daily_trend", "—")
    h4_t      = sig_dict.get("h4_trend", "—")
    h1_t      = sig_dict.get("h1_trend", "—")
    bos_h1    = sig_dict.get("h1_bos", False)
    bos_h4    = sig_dict.get("h4_bos", False)
    manip     = sig_dict.get("manipulation", False)
    kl        = sig_dict.get("key_level", 0)

    qcfg = QUALITY_CONFIG.get(quality, QUALITY_CONFIG["NONE"])
    dcfg = DIRECTION_CONFIG.get(direction, DIRECTION_CONFIG["NONE"])

    # Pré-computar TUDO antes da f-string
    border_color = qcfg["color"] if active else "#1E293B"
    border_left  = "4px" if active else "2px"
    opacity      = "1.0" if active else "0.6"
    q_color      = qcfg["color"]
    q_icon       = qcfg["icon"]
    q_label      = qcfg["label"]
    d_color      = dcfg["color"]
    d_label      = dcfg["label"]
    name         = _ticker_label(ticker)

    bos_str      = "BOS ✅" if (bos_h1 or bos_h4) else "BOS ⏳"
    manip_str    = " · Manip ✅" if manip else ""
    kl_str       = "KL ${:,.2f}".format(kl) if kl > 0 else ""
    kl_part      = " · " + kl_str if kl_str else ""
    daily_icon   = TREND_ICON.get(daily_t, "?")
    h4_icon      = TREND_ICON.get(h4_t, "?")
    h1_icon      = TREND_ICON.get(h1_t, "?")

    entry_str = "${:,.2f}".format(entry) if entry > 0 else ""
    stop_str  = "${:,.2f}".format(stop)  if stop > 0 else ""
    t1_str    = "${:,.2f}".format(t1)    if t1 > 0 else ""
    rr_str    = "R:R {:.1f}".format(rr)  if rr > 0 else ""

    alerts_html = _render_alerts_inline(alerts) if alerts else ""

    st.markdown(f"""
<div style="background:#0D1117;border:1px solid {border_color}44;border-left:{border_left} solid {border_color};padding:1rem 1.2rem;margin-bottom:0.6rem;opacity:{opacity}">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem">
<div><span style="font-size:1.05rem;font-weight:600;color:#F1F5F9">{q_icon} {name}</span> <span style="font-size:0.75rem;color:#64748B">{ticker}</span></div>
<div><span style="color:{d_color};font-weight:700;font-size:0.85rem">{d_label}</span> <span style="background:{q_color}22;color:{q_color};border:1px solid {q_color}44;font-size:0.75rem;font-weight:700;padding:0.1rem 0.4rem">{q_label}</span></div>
</div>
<div style="background:#1E293B;height:4px;margin-bottom:0.6rem;border-radius:2px"><div style="background:{q_color};width:{score}%;height:4px;border-radius:2px;opacity:0.7"></div></div>
<div style="display:flex;gap:1.2rem;font-size:0.8rem;color:#94A3B8;margin-bottom:0.4rem;flex-wrap:wrap">
<span>Score <b style="color:#F1F5F9">{score}/100</b></span>
<span>Entry <b style="color:#F1F5F9">{entry_str}</b></span>
<span>Stop <b style="color:#F87171">{stop_str}</b></span>
<span>T1 <b style="color:#34D399">{t1_str}</b></span>
<span style="color:#94A3B8">{rr_str}</span>
</div>
<div style="font-size:0.75rem;color:#64748B">Daily {daily_icon} · H4 {h4_icon} · H1 {h1_icon}{kl_part} · {bos_str}{manip_str}</div>
{alerts_html}
</div>
""", unsafe_allow_html=True)


def _render_alerts_inline(alerts: list) -> str:
    if not alerts:
        return ""
    items = "".join(
        f'<span style="'
        f'background:{"#05291A" if "✅" in a else "#1C0A0A" if "⚠️" in a else "#0F172A"};'
        f'color:{"#34D399" if "✅" in a else "#FBBF24" if "⚠️" in a else "#94A3B8"};'
        f'font-size:0.72rem;padding:0.1rem 0.5rem;margin:0.1rem 0.2rem 0 0;display:inline-block">'
        f'{a}</span>'
        for a in alerts[:5]
    )
    return f'<div style="margin-top:0.3rem">{items}</div>'


# ── Página principal ──────────────────────────────────────────────────────────

def render():
    st.title("◈ NCI — Briefing Diário")
    st.caption("Análise NCI/SMC multi-timeframe. Daily + H4 + H1.")

    if not ENGINE_AVAILABLE:
        st.error("Engine não disponível: " + ENGINE_ERROR)
        return

    # ── Sidebar de controlo ───────────────────────────────────────────────────

    col_ctrl, col_main = st.columns([1, 3])

    with col_ctrl:
        st.markdown("#### Filtros")

        univ_name = st.selectbox(
            "Universo",
            list(NCI_UNIVERSES.keys()),
            index=0,
        )

        quality_filter = st.multiselect(
            "Qualidade mínima",
            ["A+", "A", "B", "C"],
            default=["A+", "A", "B"],
        )

        active_only = st.toggle("Só setups activos", value=False)

        direction_filter = st.radio(
            "Direcção",
            ["Todas", "LONG", "SHORT"],
            horizontal=True,
        )

        st.markdown("---")

        run = st.button(
            "🔄 Actualizar",
            use_container_width=True,
            type="primary",
        )

        if "nci_last_run" in st.session_state:
            st.caption("Última análise: " + st.session_state.nci_last_run)

    # ── Execução ──────────────────────────────────────────────────────────────

    cache_key = "nci_results_" + univ_name.replace(" ", "_")

    if run or cache_key not in st.session_state:
        tickers = NCI_UNIVERSES.get(univ_name, [])
        if not tickers:
            with col_main:
                st.warning("Universo vazio.")
            return

        with col_main:
            progress = st.progress(0, text="A iniciar análise NCI...")

        feed     = DataFeed(polygon_key=POLYGON_API_KEY)
        analyzer = NCIAnalyzer(feed)

        results  = []
        errors   = []
        total    = len(tickers)

        for i, ticker in enumerate(tickers):
            progress.progress(
                (i + 1) / total,
                text=f"A analisar {ticker} ({i+1}/{total})..."
            )
            try:
                sig  = analyzer.analyze(ticker)
                results.append(sig.to_dict())
            except Exception as e:
                errors.append(ticker + ": " + str(e))

        progress.empty()

        st.session_state[cache_key] = results
        st.session_state["nci_errors_" + univ_name] = errors
        st.session_state["nci_last_run"] = datetime.now().strftime("%H:%M:%S")

    results = st.session_state.get(cache_key, [])
    errors  = st.session_state.get("nci_errors_" + univ_name, [])

    # ── Filtrar resultados ────────────────────────────────────────────────────

    filtered = [r for r in results if r["setup_quality"] in quality_filter + ["NONE"]]

    if quality_filter:
        filtered = [r for r in results if r["setup_quality"] in quality_filter]
    else:
        filtered = results

    if active_only:
        filtered = [r for r in filtered if r["setup_active"]]

    if direction_filter != "Todas":
        filtered = [r for r in filtered if r["direction"] == direction_filter]

    # Ordenar: activos primeiro, depois por score
    filtered.sort(key=lambda r: (not r["setup_active"], -r["confluence_score"]))

    # ── Renderizar ────────────────────────────────────────────────────────────

    with col_main:

        # Métricas de sumário
        total_r   = len(results)
        active_r  = sum(1 for r in results if r["setup_active"])
        longs_r   = sum(1 for r in results if r["direction"] == "LONG")
        shorts_r  = sum(1 for r in results if r["direction"] == "SHORT")
        ap_r      = sum(1 for r in results if r["setup_quality"] == "A+")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Analisados", total_r)
        m2.metric("Setups activos", active_r)
        m3.metric("LONG", longs_r)
        m4.metric("SHORT", shorts_r)
        m5.metric("Qualidade A+", ap_r)

        st.markdown("---")

        if not filtered:
            st.info("Nenhum resultado com os filtros seleccionados.")
            if errors:
                with st.expander("Erros (" + str(len(errors)) + ")"):
                    for e in errors:
                        st.caption(e)
            return

        st.caption(
            str(len(filtered)) + " resultado(s) · " +
            ("filtros activos" if active_only or direction_filter != "Todas"
             else "todos os setups")
        )

        # Separar activos dos restantes
        active_signals  = [r for r in filtered if r["setup_active"]]
        passive_signals = [r for r in filtered if not r["setup_active"]]

        if active_signals:
            st.markdown("##### ✅ Setups activos")
            for sig in active_signals:
                _render_signal_card(sig)
            if passive_signals:
                st.markdown("---")

        if passive_signals:
            label = "##### Outros setups" if active_signals else "##### Todos os setups"
            st.markdown(label)
            for sig in passive_signals:
                _render_signal_card(sig)

        # Erros no final
        if errors:
            with st.expander("⚠️ Erros de dados (" + str(len(errors)) + ")"):
                for e in errors:
                    st.caption(e)
