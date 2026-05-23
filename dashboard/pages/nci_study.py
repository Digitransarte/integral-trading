"""Dashboard — NCI Study"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from engine.data_feed import DataFeed
from engine.nci_engine import (
    analyze_nci, classify_candles, analyze_market_structure,
)
from universes import COMMODITIES, FOREX, REFERENCE

# ── Timeframe fetch config ─────────────────────────────────────────────────

_TF_FETCH = {
    "M5":  ("5m",   10),
    "M15": ("15m",  30),
    "H1":  ("1h",   60),
    "H4":  ("4h",  120),
    "D1":  ("1d",  365),
}

# ── Asset list ─────────────────────────────────────────────────────────────

def _build_asset_options() -> list:
    """Retorna [(display_label, ticker)] para o selectbox."""
    opts = []
    for ticker, name in COMMODITIES["metais_preciosos"].items():
        opts.append((f"[Metal] {ticker}  —  {name.split('(')[0].strip()}", ticker))
    for ticker, name in COMMODITIES["energia"].items():
        opts.append((f"[Energy] {ticker}  —  {name.split('(')[0].strip()}", ticker))
    for ticker, name in FOREX["majors"].items():
        opts.append((f"[FX] {ticker}  —  {name.split('—')[0].strip()}", ticker))
    for ticker, name in FOREX["crosses"].items():
        opts.append((f"[FX] {ticker}  —  {name.split('—')[0].strip()}", ticker))
    for ticker in REFERENCE["etf"][:5]:
        opts.append((f"[ETF] {ticker}", ticker))
    for ticker in REFERENCE["sp500_sample"][:6]:
        opts.append((f"[Stock] {ticker}", ticker))
    return opts


# ── Data loading ───────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _load_data(ticker: str, ltf: str, htf: str):
    """Carrega LTF e HTF. Cache de 5 minutos."""
    feed = DataFeed()
    ltf_interval, ltf_days = _TF_FETCH[ltf]
    htf_interval, htf_days = _TF_FETCH[htf]

    df_ltf = feed.get_bars_intraday(ticker, interval=ltf_interval, days=ltf_days)

    if htf_interval == "1d":
        df_htf = feed.get_bars(ticker, days=htf_days)
    else:
        df_htf = feed.get_bars_intraday(ticker, interval=htf_interval, days=htf_days)

    return df_ltf, df_htf


# ── Chart builder ──────────────────────────────────────────────────────────

def _build_chart(df_display: pd.DataFrame,
                 df_ltf_full: pd.DataFrame,
                 df_htf: pd.DataFrame | None,
                 result: dict) -> go.Figure:
    """Candlestick Plotly com anotações NCI."""
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_display.index,
        open=df_display["open"],
        high=df_display["high"],
        low=df_display["low"],
        close=df_display["close"],
        name="",
        increasing_line_color="#34D399",
        decreasing_line_color="#F87171",
        increasing_fillcolor="#34D399",
        decreasing_fillcolor="#F87171",
        showlegend=False,
    ))

    disp_set = set(df_display.index)

    # ── Key Level
    kl = result.get("key_level")
    if kl:
        fig.add_hline(
            y=kl["price"],
            line_dash="dash",
            line_color="#F59E0B",
            line_width=1.5,
            annotation_text=f"KL {kl['price']:.5g}",
            annotation_position="top left",
            annotation_font_color="#F59E0B",
            annotation_font_size=10,
        )

    # ── Swing markers
    try:
        df_cl = classify_candles(df_ltf_full.copy())
        ms    = analyze_market_structure(df_cl, window=3)
        df_sw = ms["df"]

        sh_in = [i for i in df_sw[df_sw["swing_high"]].index if i in disp_set]
        sl_in = [i for i in df_sw[df_sw["swing_low"]].index  if i in disp_set]

        if sh_in:
            fig.add_trace(go.Scatter(
                x=sh_in,
                y=[float(df_display.loc[i, "high"]) * 1.0005 for i in sh_in],
                mode="markers",
                marker=dict(symbol="triangle-down", color="#60A5FA", size=9),
                name="SH", showlegend=False,
            ))
        if sl_in:
            fig.add_trace(go.Scatter(
                x=sl_in,
                y=[float(df_display.loc[i, "low"]) * 0.9995 for i in sl_in],
                mode="markers",
                marker=dict(symbol="triangle-up", color="#A78BFA", size=9),
                name="SL", showlegend=False,
            ))
    except Exception:
        pass

    # ── Pullback highlight
    pb = result.get("pullback")
    if pb and pb.get("candles"):
        pb_in = [c for c in pb["candles"] if c in disp_set]
        if len(pb_in) >= 2:
            fig.add_vrect(
                x0=pb_in[0], x1=pb_in[-1],
                fillcolor="#F59E0B", opacity=0.15,
                layer="below", line_width=0,
            )
            try:
                fig.add_annotation(
                    x=pb_in[0],
                    y=float(df_display.loc[pb_in[0], "high"]),
                    text="PB", showarrow=False,
                    font=dict(color="#F59E0B", size=9),
                    yanchor="bottom",
                )
            except Exception:
                pass

    # ── BOS line
    bos = result.get("bos")
    if bos and bos.get("valid") and bos.get("breakout"):
        bk = bos["breakout"]
        if bk and bk.get("candles"):
            bos_c = bk["candles"][-1]
            if bos_c in disp_set:
                fig.add_vline(
                    x=bos_c,
                    line_color="#34D399", line_dash="dot", line_width=1,
                )
                try:
                    fig.add_annotation(
                        x=bos_c,
                        y=float(df_display.loc[bos_c, "high"]),
                        text="BOS", showarrow=False,
                        font=dict(color="#34D399", size=9),
                        yanchor="bottom",
                    )
                except Exception:
                    pass

    # ── Range rectangle
    rng = result.get("range", {})
    if rng.get("has_range") and rng.get("range_high") and rng.get("range_low"):
        fig.add_hrect(
            y0=rng["range_low"], y1=rng["range_high"],
            fillcolor="#475569", opacity=0.08,
            layer="below", line_width=0,
        )

    # ── HTF warning zone
    cycle = result.get("market_cycle", {})
    if cycle.get("warning") and cycle.get("warning_zone") and df_htf is not None:
        try:
            df_hc   = classify_candles(df_htf.copy())
            htf_ms  = analyze_market_structure(df_hc, window=5)
            htf_kl2 = htf_ms["key_level"]
            htf_zones = {
                "down_key_level": (htf_kl2["price"]
                                   if htf_kl2 and htf_ms["trend"] == "downtrend"
                                   else None),
                "up_key_level":   (htf_kl2["price"]
                                   if htf_kl2 and htf_ms["trend"] == "uptrend"
                                   else None),
                "recent_high":    (float(max(htf_ms["swing_highs"]))
                                   if htf_ms["swing_highs"] else None),
                "recent_low":     (float(min(htf_ms["swing_lows"]))
                                   if htf_ms["swing_lows"] else None),
            }
            wz_price = htf_zones.get(cycle["warning_zone"])
            if wz_price:
                fig.add_hline(
                    y=wz_price,
                    line_color="#EF4444", line_dash="dot", line_width=1.5,
                    annotation_text=f"HTF ⚠ {wz_price:.5g}",
                    annotation_position="bottom right",
                    annotation_font_color="#EF4444",
                    annotation_font_size=9,
                )
        except Exception:
            pass

    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="#0D1117",
        paper_bgcolor="#0D1117",
        margin=dict(l=10, r=60, t=20, b=20),
        height=460,
        xaxis=dict(
            rangeslider_visible=False,
            showgrid=True, gridcolor="#1E293B",
        ),
        yaxis=dict(showgrid=True, gridcolor="#1E293B", side="right"),
        font=dict(family="monospace", size=11),
    )

    return fig


# ── Factor card helpers ────────────────────────────────────────────────────

def _factor_html(label: str, ok: bool, detail: str = "") -> str:
    color = "#34D399" if ok else "#F87171"
    icon  = "✓" if ok else "✗"
    det   = (f"<br><span style='color:#64748B;font-size:0.72rem'>{detail}</span>"
             if detail else "")
    return (
        f"<div style='background:#0D1117;border-left:3px solid {color};"
        f"padding:0.45rem 0.7rem;margin-bottom:0.35rem;font-size:0.85rem'>"
        f"<span style='color:{color};font-weight:700'>{icon} {label}</span>"
        f"{det}</div>"
    )


def _status_html(all_aligned: bool) -> str:
    if all_aligned:
        return (
            "<div style='background:#065F46;border:1px solid #34D399;"
            "color:#34D399;font-size:0.95rem;font-weight:700;"
            "text-align:center;padding:0.55rem;border-radius:4px;"
            "margin-top:0.6rem'>◈ ALINHADO — ENTRADA VÁLIDA</div>"
        )
    return (
        "<div style='background:#111827;border:1px solid #374151;"
        "color:#6B7280;font-size:0.8rem;text-align:center;"
        "padding:0.5rem;border-radius:4px;margin-top:0.6rem'>"
        "Aguardar — factores incompletos</div>"
    )


# ── Reasoning text ─────────────────────────────────────────────────────────

_TREND_PT = {
    "uptrend":   "Alta  (HH + HL)",
    "downtrend": "Baixa  (LH + LL)",
    "range":     "Range / lateral",
    "undefined": "Indefinida",
}

_PAT_PT = {
    "two_marubozu":   "P1 — Two Marubozu",
    "big_maru_small": "P2 — Big Maru + Small",
    "pac":            "PAC — confirmação alargada",
}

_KL_Q_PT = {
    "normal":  "normal",
    "weak":    "fraco  (range antes do pullback)",
    "invalid": "inválido  (range após pullback)",
}


def _build_reasoning(result: dict, ticker: str, ltf: str, htf: str) -> str:
    trend     = result.get("trend", "undefined")
    htf_trend = result.get("htf_trend", "undefined")
    kl        = result.get("key_level")
    kl_q      = result.get("key_level_quality", {})
    pb        = result.get("pullback")
    bos       = result.get("bos")
    cycle     = result.get("market_cycle", {})
    ff        = result.get("four_factors", {})

    lines = [
        f"**{ticker}  |  LTF {ltf}  /  HTF {htf}**",
        "",
        f"**Estrutura LTF:** {_TREND_PT.get(trend, trend)}",
        f"**Estrutura HTF:** {_TREND_PT.get(htf_trend, htf_trend)}",
        "",
    ]

    if not cycle.get("cycle_active"):
        tb = cycle.get("terminated_by") or "zona desconhecida"
        lines.append(f"**Ciclo:** Terminado — preço atingiu zona HTF `{tb}`.")
    elif cycle.get("warning"):
        wz = cycle.get("warning_zone", "")
        lines.append(f"**Ciclo:** Activo ⚠ — a aproximar zona HTF `{wz}` (< 20 % de margem).")
    else:
        lines.append("**Ciclo:** Activo — preço tem espaço para avançar.")

    lines.append("")

    if kl:
        q_label = _KL_Q_PT.get(kl_q.get("quality", ""), kl_q.get("quality", ""))
        lines.append(
            f"**Key Level ({kl.get('type', '?')}):** `{kl['price']:.5g}` "
            f"— qualidade {q_label}."
        )
    else:
        lines.append("**Key Level:** Não identificado — estrutura insuficiente.")

    if pb:
        pat = _PAT_PT.get(pb.get("pattern", ""), pb.get("pattern", ""))
        nc  = len(pb.get("candles", []))
        lines.append(f"**Pullback:** {pat} ({nc} candle{'s' if nc > 1 else ''}).")
    else:
        lines.append("**Pullback:** Não detectado — aguardar setup de entrada.")

    if bos:
        if bos.get("valid"):
            lines.append("**BOS:** Confirmado — breakout legítimo sobre a Key Level.")
        elif bos.get("type") == "fake_breakout":
            lines.append("**BOS:** Falso breakout — preço cruzou mas padrão não validado.")
        else:
            lines.append("**BOS:** Sem confirmação ainda.")
    else:
        lines.append("**BOS:** Aguardar pullback para avaliar.")

    lines.append("")

    n_ok = sum([ff.get("trend", False), ff.get("zone", False),
                ff.get("momentum", False), ff.get("confirmation", False)])
    if ff.get("all_aligned"):
        lines.append(
            "**→ Setup completo:** 4/4 factores NCI presentes e ciclo activo. "
            "Entrada válida sujeita a gestão de risco."
        )
    else:
        missing = []
        if not ff.get("trend"):           missing.append("tendência indefinida")
        if not ff.get("zone"):            missing.append("KL inválido ou ausente")
        if not ff.get("momentum"):        missing.append("sem pullback")
        if not ff.get("confirmation"):    missing.append("sem BOS confirmado")
        if not cycle.get("cycle_active"): missing.append("ciclo terminado")
        lines.append(
            f"**→ Factores: {n_ok}/4.**"
            + (f"  Aguardar: {', '.join(missing)}." if missing else "")
        )

    return "\n".join(lines)


# ── Main render ────────────────────────────────────────────────────────────

def render():
    st.title("◈ NCI Study")

    asset_options = _build_asset_options()
    labels  = [a[0] for a in asset_options]
    tickers = [a[1] for a in asset_options]

    with st.sidebar:
        st.markdown("### Configuração NCI")

        sel_idx = st.selectbox(
            "Activo",
            range(len(labels)),
            format_func=lambda i: labels[i],
            index=0,
        )
        ticker = tickers[sel_idx]

        htf = st.selectbox("HTF (Higher Time Frame)", ["H4", "D1", "H1"], index=0)
        ltf = st.selectbox("LTF (Lower Time Frame)",  ["M15", "M5"],       index=0)

        n_candles = st.slider("Candles no gráfico", 50, 200, 100, step=10)

        run = st.button("◈ Analisar", type="primary", use_container_width=True)

    # Session state
    for key in ("nci_result", "nci_ticker", "nci_ltf", "nci_htf",
                "nci_df_ltf", "nci_df_htf"):
        if key not in st.session_state:
            st.session_state[key] = None

    if run:
        with st.spinner(f"A carregar {ticker} ({ltf} / {htf})…"):
            df_ltf, df_htf = _load_data(ticker, ltf, htf)

        ok = True
        if df_ltf is None or (isinstance(df_ltf, pd.DataFrame) and df_ltf.empty):
            st.error(f"Sem dados LTF para {ticker} ({ltf}). Tenta outro activo ou timeframe.")
            ok = False
        elif len(df_ltf) < 20:
            st.warning(f"Dados insuficientes: apenas {len(df_ltf)} candles LTF.")
            ok = False
        if df_htf is None or (isinstance(df_htf, pd.DataFrame) and df_htf.empty):
            st.error(f"Sem dados HTF para {ticker} ({htf}).")
            ok = False

        if ok:
            try:
                result = analyze_nci(df_ltf, df_htf, ltf_window=3, htf_window=5)
                st.session_state.nci_result = result
                st.session_state.nci_ticker = ticker
                st.session_state.nci_ltf    = ltf
                st.session_state.nci_htf    = htf
                st.session_state.nci_df_ltf = df_ltf.copy()
                st.session_state.nci_df_htf = df_htf.copy()
            except Exception as e:
                st.error(f"Erro na análise NCI: {e}")

    result   = st.session_state.nci_result
    df_ltf   = st.session_state.nci_df_ltf
    df_htf   = st.session_state.nci_df_htf
    cur_tick = st.session_state.nci_ticker
    cur_ltf  = st.session_state.nci_ltf
    cur_htf  = st.session_state.nci_htf

    if result is None:
        st.info("Selecciona um activo e clica **◈ Analisar** para iniciar a análise NCI.")
        return

    ff    = result["four_factors"]
    kl    = result.get("key_level")
    kl_q  = result.get("key_level_quality", {})
    pb    = result.get("pullback")
    bos   = result.get("bos")
    cycle = result.get("market_cycle", {})

    col_left, col_right = st.columns([2, 3])

    with col_left:
        st.markdown("#### 4 Factores NCI")

        kl_detail  = (f"{kl['price']:.5g}  ·  {kl_q.get('quality', '')}"
                      if kl else "não identificado")
        pb_detail  = _PAT_PT.get(pb.get("pattern", ""), "") if pb else "aguardar"
        bos_detail = bos.get("type", "") if bos else "aguardar"

        st.markdown(
            _factor_html("Trend",        ff["trend"],
                         _TREND_PT.get(result.get("trend"), "")) +
            _factor_html("Zone",         ff["zone"],         kl_detail) +
            _factor_html("Momentum",     ff["momentum"],     pb_detail) +
            _factor_html("Confirmation", ff["confirmation"], bos_detail) +
            _status_html(ff["all_aligned"]),
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("**Ciclo de mercado**")

        if not cycle.get("cycle_active"):
            tb = cycle.get("terminated_by") or "?"
            st.markdown(
                f"<span style='color:#F87171;font-weight:600'>Terminado</span>"
                f"<span style='color:#94A3B8;font-size:0.78rem'> ({tb})</span>",
                unsafe_allow_html=True,
            )
        elif cycle.get("warning"):
            wz = cycle.get("warning_zone", "")
            st.markdown(
                f"<span style='color:#F59E0B;font-weight:600'>⚠ Aviso</span>"
                f"<span style='color:#94A3B8;font-size:0.78rem'> ({wz})</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<span style='color:#34D399;font-weight:600'>Activo</span>",
                unsafe_allow_html=True,
            )

        st.caption(f"HTF trend: {result.get('htf_trend', '?')}")
        htf_kl = result.get("htf_key_level")
        if htf_kl:
            st.caption(f"HTF KL: {htf_kl['price']:.5g}")

    with col_right:
        df_display = df_ltf.tail(n_candles)
        fig = _build_chart(df_display, df_ltf, df_htf, result)
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

    st.markdown("---")
    st.markdown("#### Raciocínio NCI")
    st.markdown(_build_reasoning(result, cur_tick, cur_ltf, cur_htf))
