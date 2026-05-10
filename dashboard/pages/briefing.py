"""Dashboard — Briefing Diário"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime

try:
    from engine.opportunity_ranker import OpportunityRanker
    from engine.data_feed import DataFeed
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

QUALITY_COLOR = {
    "A+": "#34D399", "A": "#6EE7B7",
    "B":  "#FBBF24", "C": "#F97316", "NONE": "#475569",
}
DIRECTION_COLOR = {"LONG": "#34D399", "SHORT": "#F87171", "NONE": "#475569"}


def render():
    st.title("◈ Briefing Diário")
    st.caption("Top oportunidades NCI + EP. Actualiza uma vez por dia.")

    if not ENGINE_AVAILABLE:
        st.error("Engine não disponível: " + ENGINE_ERROR)
        return

    col_cfg, col_main = st.columns([1, 3])

    with col_cfg:
        st.markdown("#### Filtros")

        direction_filter = st.radio(
            "Direcção", ["LONG", "ALL", "SHORT"],
            index=0, horizontal=True,
        )

        min_score = st.slider(
            "Score mínimo", min_value=20, max_value=80, value=25, step=5,
        )

        include_stocks = st.toggle("Incluir stocks EP", value=False)

        st.markdown("---")
        run = st.button("🔄 Actualizar briefing",
                        use_container_width=True, type="primary")

        if "briefing_last" in st.session_state:
            st.caption("Último: " + st.session_state.briefing_last)

    cache_key = "briefing_" + direction_filter + "_" + str(min_score)

    if run or cache_key not in st.session_state:
        with col_main:
            with st.spinner("A varrer activos..."):
                try:
                    feed   = DataFeed(polygon_key=POLYGON_API_KEY)
                    ranker = OpportunityRanker(feed)
                    opps   = ranker.run(
                        include_stocks=include_stocks,
                        min_score=min_score,
                        direction_filter=direction_filter,
                    )
                    st.session_state[cache_key] = [o.to_dict() for o in opps]
                    st.session_state["briefing_last"] = datetime.now().strftime("%H:%M")
                except Exception as e:
                    st.error("Erro: " + str(e))
                    return

    opps = st.session_state.get(cache_key, [])

    with col_main:
        if not opps:
            st.info("Nenhuma oportunidade encontrada. Reduz o score mínimo.")
            return

        active = [o for o in opps if o["setup_active"]]
        watch  = [o for o in opps if not o["setup_active"]]

        total  = len(opps)
        n_act  = len(active)
        n_long = sum(1 for o in opps if o["direction"] == "LONG")
        n_short= sum(1 for o in opps if o["direction"] == "SHORT")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total", total)
        m2.metric("Activos", n_act)
        m3.metric("LONG", n_long)
        m4.metric("SHORT", n_short)

        st.markdown("---")

        if active:
            st.markdown("##### ✅ Setups activos")
            for opp in active:
                _render_opp(opp)

        if watch:
            if active:
                st.markdown("---")
            st.markdown("##### ⏳ A aguardar confirmação")
            for opp in watch:
                _render_opp(opp)


def _render_opp(opp: dict):
    qc = QUALITY_COLOR.get(opp["quality"], "#475569")
    dc = DIRECTION_COLOR.get(opp["direction"], "#475569")
    active = opp["setup_active"]
    border = "4px" if active else "2px"
    opacity = "1.0" if active else "0.65"

    entry = opp["entry_price"]
    stop  = opp["stop_loss"]
    t1    = opp["target_1"]
    rr    = opp["risk_reward"]

    entry_str = "${:,.2f}".format(entry) if entry > 0 else "—"
    stop_str  = "${:,.2f}".format(stop)  if stop  > 0 else "—"
    t1_str    = "${:,.2f}".format(t1)    if t1    > 0 else "—"
    rr_str    = "R:R {:.1f}".format(rr)  if rr    > 0 else ""

    alerts_html = ""
    for a in opp.get("alerts", [])[:4]:
        bg = "#05291A" if "✅" in a else "#1C0A0A" if "⚠️" in a else "#0F172A"
        fc = "#34D399" if "✅" in a else "#FBBF24" if "⚠️" in a else "#94A3B8"
        alerts_html += "<span style='background:{};color:{};font-size:0.72rem;padding:0.1rem 0.5rem;margin-right:0.3rem'>{}</span>".format(bg, fc, a)

    rank    = opp["rank"]
    name    = opp["name"]
    ticker  = opp["ticker"]
    strat   = opp["strategy"]
    quality = opp["quality"]
    score   = opp["score"]
    direc   = opp["direction"]

    st.markdown(
        "<div style='background:#0D1117;border:1px solid {qc}44;border-left:{bl} solid {qc};"
        "padding:0.9rem 1.2rem;margin-bottom:0.5rem;opacity:{op}'>"
        "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem'>"
        "<div><span style='font-size:0.75rem;color:#475569'>#{rank} · {strat}</span> "
        "<span style='font-size:1rem;font-weight:700;color:#F1F5F9'> {name}</span> "
        "<span style='font-size:0.75rem;color:#64748B'>{ticker}</span></div>"
        "<div><span style='color:{dc};font-weight:700;font-size:0.85rem'>{direc}</span> "
        "<span style='background:{qc}22;color:{qc};border:1px solid {qc}44;"
        "font-size:0.75rem;font-weight:700;padding:0.1rem 0.4rem;margin-left:0.3rem'>{quality}</span></div>"
        "</div>"
        "<div style='background:#1E293B;height:3px;margin-bottom:0.5rem;border-radius:2px'>"
        "<div style='background:{qc};width:{score}%;height:3px;border-radius:2px;opacity:0.7'></div></div>"
        "<div style='display:flex;gap:1.2rem;font-size:0.8rem;color:#94A3B8;margin-bottom:0.3rem'>"
        "<span>Score <b style='color:#F1F5F9'>{score}/100</b></span>"
        "<span>Entry <b style='color:#F1F5F9'>{entry}</b></span>"
        "<span>Stop <b style='color:#F87171'>{stop}</b></span>"
        "<span>T1 <b style='color:#34D399'>{t1}</b></span>"
        "<span>{rr}</span></div>"
        "{alerts}</div>".format(
            qc=qc, dc=dc, bl=border, op=opacity,
            rank=rank, strat=strat, name=name, ticker=ticker,
            direc=direc, quality=quality, score=score,
            entry=entry_str, stop=stop_str, t1=t1_str, rr=rr_str,
            alerts=alerts_html,
        ),
        unsafe_allow_html=True,
    )
