"""Dashboard — NCI Alertas"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime

try:
    from engine.nci_alert_engine import NCIAlertEngine
    from engine.data_feed import DataFeed
    from config import POLYGON_API_KEY
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

PRIORITY_COLOR = {
    "HIGH":   "#F87171",
    "MEDIUM": "#FBBF24",
    "LOW":    "#60A5FA",
}

TYPE_LABEL = {
    "SETUP_ACTIVE":   "Setup Activo",
    "BOS_CONFIRMED":  "BOS Confirmado",
    "PULLBACK_ZONE":  "Zona de Entrada",
    "TREND_FORMED":   "Tendência Formada",
    "SCORE_IMPROVED": "Score Melhorou",
    "SETUP_LOST":     "Setup Perdido",
}


def render():
    st.title("🔔 Alertas NCI")
    st.caption("Transições de estado — quando o setup muda, és avisado.")

    if not ENGINE_AVAILABLE:
        st.error("Engine não disponível: " + ENGINE_ERROR)
        return

    feed   = DataFeed(polygon_key=POLYGON_API_KEY)
    engine = NCIAlertEngine(feed)

    # ── Controlos ─────────────────────────────────────────────────────────────

    col_ctrl, col_main = st.columns([1, 3])

    with col_ctrl:
        st.markdown("#### Controlos")

        if st.button("🔄 Verificar agora", use_container_width=True, type="primary"):
            with st.spinner("A analisar todos os activos..."):
                new_alerts = engine.run()
                if new_alerts:
                    st.success(str(len(new_alerts)) + " novo(s) alerta(s)!")
                else:
                    st.info("Sem novas transições detectadas.")
            st.rerun()

        st.markdown("---")

        unseen_only = st.toggle("Só não vistos", value=False)
        days_back   = st.slider("Histórico (dias)", 1, 30, 7)

        if st.button("✓ Marcar todos como vistos", use_container_width=True):
            engine.mark_all_seen()
            st.rerun()

        st.markdown("---")
        st.markdown("#### Estado actual")

        states = engine.get_all_states()
        if states:
            for ticker, state in states.items():
                trend  = state.get("daily_trend", "?")
                score  = state.get("score", 0)
                active = state.get("setup_active", False)
                bos    = state.get("bos_confirmed", False)
                pullb  = state.get("in_pullback_zone", False)

                trend_icon = "↑" if trend == "UPTREND" else "↓" if trend == "DOWNTREND" else "→"
                status_icon = "✅" if active else "🎯" if bos else "📍" if pullb else "⏳"

                name = NCIAlertEngine.WATCHLIST.get(ticker, {}).get("name", ticker)
                st.caption(
                    status_icon + " **" + name + "** " + trend_icon +
                    " " + str(score) + "pt"
                )
        else:
            st.caption("Sem estados. Clica 'Verificar agora'.")

    # ── Alertas ───────────────────────────────────────────────────────────────

    with col_main:
        alerts = engine.get_alerts(unseen_only=unseen_only, days=days_back)

        if not alerts:
            st.info(
                "Nenhum alerta" +
                (" não visto" if unseen_only else "") +
                " nos últimos " + str(days_back) + " dias." +
                "\n\nClica **Verificar agora** para correr uma análise."
            )
            return

        # Separar por prioridade
        high   = [a for a in alerts if a["priority"] == "HIGH"]
        medium = [a for a in alerts if a["priority"] == "MEDIUM"]
        low    = [a for a in alerts if a["priority"] == "LOW"]

        unseen_count = sum(1 for a in alerts if not a.get("seen", False))
        if unseen_count > 0:
            st.markdown("**" + str(unseen_count) + " alerta(s) por ver** · " +
                        str(len(alerts)) + " total")
        else:
            st.markdown(str(len(alerts)) + " alerta(s)")

        st.markdown("---")

        for group, label in [(high, "🔴 Alta prioridade"),
                             (medium, "🟡 Média prioridade"),
                             (low, "🔵 Informação")]:
            if not group:
                continue
            st.markdown("##### " + label)
            for alert in group:
                _render_alert(alert, engine)
            st.markdown("")


def _render_alert(alert: dict, engine: NCIAlertEngine):
    """Renderiza um card de alerta."""
    seen     = alert.get("seen", False)
    priority = alert.get("priority", "LOW")
    pc       = PRIORITY_COLOR.get(priority, "#60A5FA")
    opacity  = "0.6" if seen else "1.0"
    border   = "2px" if seen else "4px"

    ticker    = alert["ticker"]
    name      = alert["name"]
    atype     = alert["alert_type"]
    message   = alert["message"]
    score     = alert["score"]
    direction = alert["direction"]
    entry     = alert["entry_price"]
    stop      = alert["stop_loss"]
    t1        = alert["target_1"]
    rr        = alert["risk_reward"]
    ts        = alert["timestamp"][:16].replace("T", " ")
    type_icon = alert.get("type_icon", "📢")
    type_label = TYPE_LABEL.get(atype, atype)

    entry_str = "${:,.2f}".format(entry) if entry > 0 else "—"
    stop_str  = "${:,.2f}".format(stop)  if stop  > 0 else "—"
    t1_str    = "${:,.2f}".format(t1)    if t1    > 0 else "—"
    rr_str    = "R:R {:.1f}".format(rr)  if rr    > 0 else ""

    dir_color = "#34D399" if direction == "LONG" else "#F87171" if direction == "SHORT" else "#94A3B8"

    st.markdown(
        "<div style='background:#0D1117;border:1px solid {pc}44;"
        "border-left:{bl} solid {pc};padding:1rem 1.2rem;"
        "margin-bottom:0.5rem;opacity:{op}'>"

        "<div style='display:flex;justify-content:space-between;margin-bottom:0.4rem'>"
        "<div>"
        "<span style='font-size:1.1rem'>{ti}</span> "
        "<span style='font-weight:700;color:#F1F5F9'>{name}</span> "
        "<span style='color:#64748B;font-size:0.8rem'>{ticker}</span>"
        "</div>"
        "<div style='text-align:right'>"
        "<span style='background:{pc}22;color:{pc};font-size:0.75rem;"
        "font-weight:700;padding:0.1rem 0.5rem'>{tlabel}</span>"
        "</div>"
        "</div>"

        "<div style='font-size:0.85rem;color:#CBD5E1;margin-bottom:0.5rem;"
        "white-space:pre-line'>{msg}</div>"

        "<div style='display:flex;gap:1.2rem;font-size:0.78rem;color:#94A3B8'>"
        "<span>Score <b style='color:#F1F5F9'>{score}/100</b></span>"
        "<span style='color:{dc}'>{direction}</span>"
        "<span>Entry <b style='color:#F1F5F9'>{entry}</b></span>"
        "<span>Stop <b style='color:#F87171'>{stop}</b></span>"
        "<span>T1 <b style='color:#34D399'>{t1}</b></span>"
        "<span>{rr}</span>"
        "<span style='color:#475569'>{ts}</span>"
        "</div>"
        "</div>".format(
            pc=pc, bl=border, op=opacity,
            ti=type_icon, name=name, ticker=ticker,
            tlabel=type_label,
            msg=message,
            score=score, dc=dir_color, direction=direction,
            entry=entry_str, stop=stop_str, t1=t1_str, rr=rr_str,
            ts=ts,
        ),
        unsafe_allow_html=True,
    )

    # Botão marcar como visto + abrir posição
    col_seen, col_pos, col_space = st.columns([1, 1, 3])
    with col_seen:
        if not seen:
            if st.button("✓ Visto", key="seen_" + alert["alert_id"]):
                engine.mark_seen(alert["alert_id"])
                st.rerun()
    with col_pos:
        if alert["priority"] == "HIGH" and entry > 0:
            if st.button("📋 Abrir Posição", key="pos_" + alert["alert_id"]):
                st.session_state["nci_prefill"] = {
                    "entry":     entry,
                    "stop":      stop,
                    "target_1":  t1,
                    "target_2":  t1 * 1.1,
                    "direction": direction,
                    "score":     score,
                    "catalyst":  name + " — " + type_label,
                }
                st.info("Valores copiados. Vai a **Posições → Abrir Posição**.")
