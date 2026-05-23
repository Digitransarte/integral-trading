"""Dashboard — Calendário Económico"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime

try:
    from engine.economic_calendar import EconomicCalendar, EVENT_ASSET_MAP
    from config import POLYGON_API_KEY
    import os
    FINNHUB_KEY    = os.getenv("FINNHUB_API_KEY", "")
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

IMPACT_COLOR = {
    "HIGH":   "#F87171",
    "MEDIUM": "#FBBF24",
    "LOW":    "#60A5FA",
}

# Activos do sistema com nomes legíveis
SYSTEM_TICKERS = {
    "GC=F":     "Ouro",
    "SI=F":     "Prata",
    "CL=F":     "Petróleo WTI",
    "BZ=F":     "Petróleo Brent",
    "NG=F":     "Gás Natural",
    "ZC=F":     "Milho",
    "ZS=F":     "Soja",
    "CT=F":     "Algodão",
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "AUDJPY=X": "AUD/JPY",
}


def render():
    st.title("📅 Calendário Económico")
    st.caption("Eventos HIGH/MEDIUM impact e risco para cada activo.")

    if not ENGINE_AVAILABLE:
        st.error("Engine não disponível: " + ENGINE_ERROR)
        return

    if not FINNHUB_KEY:
        st.error(
            "FINNHUB_API_KEY não configurada. "
            "Adiciona ao ficheiro .env do servidor:\n\n"
            "`FINNHUB_API_KEY=o_teu_token`"
        )
        st.info("Regista em https://finnhub.io/register (gratuito)")
        return

    calendar = EconomicCalendar(finnhub_key=FINNHUB_KEY)

    col_ctrl, col_main = st.columns([1, 3])

    with col_ctrl:
        st.markdown("#### Filtros")

        hours_ahead = st.slider("Janela (horas)", 12, 96, 48, step=12)
        show_medium = st.toggle("Incluir MEDIUM impact", value=True)

        if st.button("🔄 Actualizar", use_container_width=True, type="primary"):
            # Limpar cache para forçar re-fetch
            from pathlib import Path as _P
            cache = _P("data/calendar_cache.json")
            if cache.exists():
                cache.unlink()
            st.rerun()

        st.markdown("---")
        st.markdown("#### Risco por activo")

        # Mini-painel de risco para cada activo do sistema
        for ticker, name in SYSTEM_TICKERS.items():
            try:
                risk = calendar.get_asset_risk(ticker, hours_ahead=hours_ahead)
                if risk.risk_level == "NONE":
                    continue
                color = IMPACT_COLOR.get(risk.risk_level, "#60A5FA")
                block_str = " 🔴" if risk.in_block_zone else ""
                st.markdown(
                    "<span style='color:" + color + ";font-size:0.8rem'>"
                    "● </span><span style='font-size:0.8rem'><b>" +
                    name + "</b> — " + risk.risk_level + block_str + "</span>",
                    unsafe_allow_html=True
                )
            except Exception:
                continue

    with col_main:
        # ── Eventos próximos ──────────────────────────────────────────────────
        impact_filter = "MEDIUM" if show_medium else "HIGH"
        events = calendar.get_upcoming_events(
            hours_ahead=hours_ahead,
            impact_filter=impact_filter
        )

        if not events:
            st.info(
                "Sem eventos " + impact_filter + "+ impact nas próximas " +
                str(hours_ahead) + "h.\n\n"
                "Clica **Actualizar** para re-buscar."
            )
        else:
            st.markdown("### " + str(len(events)) + " eventos nas próximas " +
                        str(hours_ahead) + "h")
            st.markdown("---")

            # Separar por timing
            critical = [e for e in events if 0 <= e.hours_until <= 4]
            soon     = [e for e in events if 4 < e.hours_until <= 24]
            later    = [e for e in events if e.hours_until > 24]

            for group, label in [
                (critical, "🔴 Nas próximas 4 horas"),
                (soon,     "🟡 Hoje (4-24h)"),
                (later,    "🔵 Amanhã+"),
            ]:
                if not group:
                    continue

                st.markdown("##### " + label)
                for event in group:
                    _render_event_card(event, calendar, SYSTEM_TICKERS)
                st.markdown("")

        st.markdown("---")

        # ── Impacto por activo ────────────────────────────────────────────────
        st.markdown("### Como afecta os teus activos")

        affected_tickers = []
        for ticker, name in SYSTEM_TICKERS.items():
            try:
                risk = calendar.get_asset_risk(ticker, hours_ahead=hours_ahead)
                if risk.risk_level != "NONE":
                    affected_tickers.append((ticker, name, risk))
            except Exception:
                continue

        if not affected_tickers:
            st.info("Nenhum activo do sistema afectado por eventos nas próximas " +
                    str(hours_ahead) + "h.")
        else:
            for ticker, name, risk in affected_tickers:
                _render_asset_risk(ticker, name, risk)


def _render_event_card(event, calendar, tickers: dict):
    """Card de um evento económico."""
    impact   = event.impact
    color    = IMPACT_COLOR.get(impact, "#60A5FA")
    h        = event.hours_until
    time_str = event.dt.strftime("%d/%m %H:%M UTC")

    if h < 1:
        timing = "em " + str(int(h * 60)) + "min"
    elif h < 24:
        timing = "em " + str(int(h)) + "h"
    else:
        timing = "em " + str(round(h/24, 1)) + "d"

    # Activos afectados
    affected = []
    for ticker, name in tickers.items():
        risk = calendar.get_asset_risk(ticker, hours_ahead=96)
        if any((e.event_id if hasattr(e, "event_id") else e.get("event_id","")) == event.event_id for e in risk.events):
            affected.append(name)

    affected_str = " · ".join(affected[:4]) if affected else "—"

    st.markdown(
        "<div style='background:#0D1117;border:1px solid " + color + "44;"
        "border-left:3px solid " + color + ";padding:0.7rem 1rem;"
        "margin-bottom:0.4rem'>"
        "<div style='display:flex;justify-content:space-between'>"
        "<span style='font-weight:600;color:#F1F5F9'>" + event.name + "</span>"
        "<span style='color:" + color + ";font-size:0.8rem;font-weight:700'>"
        + impact + " · " + timing + "</span>"
        "</div>"
        "<div style='font-size:0.78rem;color:#94A3B8;margin-top:0.2rem'>"
        + event.country.upper() + " · " + time_str +
        (" · Activos: " + affected_str if affected else "") +
        "</div>"
        "</div>",
        unsafe_allow_html=True
    )


def _render_asset_risk(ticker: str, name: str, risk):
    """Painel de risco fundamental para um activo."""
    color    = IMPACT_COLOR.get(risk.risk_level, "#60A5FA")
    block    = risk.in_block_zone

    with st.expander(
        ("🔴 BLOQUEADO — " if block else "⚠️ ") + name +
        " (" + ticker + ") — " + risk.risk_level,
        expanded=(risk.risk_level == "HIGH")
    ):
        if block:
            st.error("Evento a decorrer — não abrir novas posições em " + name)
        elif risk.risk_level == "HIGH":
            st.warning("Evento HIGH IMPACT próximo — aguardar ou reduzir size")

        if risk.context_text:
            st.caption(risk.context_text)

        if risk.events:
            for e in risk.events:
                h = e.hours_until
                timing = str(int(h)) + "h" if h >= 0 else "há " + str(int(abs(h))) + "h"
                st.caption(
                    "• " + e.name + " — " + timing +
                    (" [HIGH]" if e.is_high_impact else " [MEDIUM]")
                )
