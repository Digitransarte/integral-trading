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
    "M5":  ("5m",    5),
    "M15": ("15m",  10),
    "H1":  ("1h",   30),
    "H4":  ("4h",   60),
    "D1":  ("1d",  365),
    "W1":  ("1wk", 730),
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

    if htf_interval in ("1d", "1wk"):
        df_htf = feed.get_bars(ticker, days=htf_days, interval=htf_interval)
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
    if (rng.get("detected")
            and rng.get("anchor_price_high") and rng.get("anchor_price_low")):
        fig.add_hrect(
            y0=rng["anchor_price_low"], y1=rng["anchor_price_high"],
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


def _build_htf_chart(df_htf: pd.DataFrame, result: dict) -> go.Figure:
    """Candlestick HTF com KL e swing markers HTF."""
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_htf.index,
        open=df_htf["open"],
        high=df_htf["high"],
        low=df_htf["low"],
        close=df_htf["close"],
        name="",
        increasing_line_color="#34D399",
        decreasing_line_color="#F87171",
        increasing_fillcolor="#34D399",
        decreasing_fillcolor="#F87171",
        showlegend=False,
    ))

    # HTF Key Level
    htf_kl = result.get("htf_key_level")
    if htf_kl:
        fig.add_hline(
            y=htf_kl["price"],
            line_dash="dash",
            line_color="#F59E0B",
            line_width=1.5,
            annotation_text=f"HTF KL {htf_kl['price']:.5g}",
            annotation_position="top left",
            annotation_font_color="#F59E0B",
            annotation_font_size=10,
        )

    # HTF swing markers
    try:
        df_cl = classify_candles(df_htf.copy())
        ms    = analyze_market_structure(df_cl, window=5)
        df_sw = ms["df"]
        disp  = set(df_htf.index)

        sh_in = [i for i in df_sw[df_sw["swing_high"]].index if i in disp]
        sl_in = [i for i in df_sw[df_sw["swing_low"]].index  if i in disp]

        if sh_in:
            fig.add_trace(go.Scatter(
                x=sh_in,
                y=[float(df_htf.loc[i, "high"]) * 1.0005 for i in sh_in],
                mode="markers",
                marker=dict(symbol="triangle-down", color="#60A5FA", size=9),
                name="SH", showlegend=False,
            ))
        if sl_in:
            fig.add_trace(go.Scatter(
                x=sl_in,
                y=[float(df_htf.loc[i, "low"]) * 0.9995 for i in sl_in],
                mode="markers",
                marker=dict(symbol="triangle-up", color="#A78BFA", size=9),
                name="SL", showlegend=False,
            ))
    except Exception:
        pass

    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="#0D1117",
        paper_bgcolor="#0D1117",
        margin=dict(l=10, r=50, t=20, b=20),
        height=420,
        xaxis=dict(rangeslider_visible=False,
                   showgrid=True, gridcolor="#1E293B"),
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


# ── Reasoning (3 blocos) ──────────────────────────────────────────────────

_TREND_PT = {
    "uptrend":   "Alta  (HH + HL)",
    "downtrend": "Baixa  (LH + LL)",
    "range":     "Range / lateral",
    "undefined": "Indefinida",
}

_PAT_SHORT = {
    "two_marubozu":   "P1 Two Marubozu",
    "big_maru_small": "P2 Big Maru + Small",
    "pac":            "PAC",
}

_KL_Q_REASON = {
    "normal":  "sem range contaminante",
    "weak":    "range detectado antes do pullback — zona enfraquecida",
    "invalid": "range detectado após o pullback — pullback invalidado",
}

_BOS_SHORT = {
    "confirmed_bos": "BOS confirmado",
    "fake_breakout": "BOS falso",
    "pending":       "BOS pendente",
}


def _render_reasoning(result: dict, ticker: str, ltf: str, htf: str,
                      df_ltf: pd.DataFrame, df_htf: pd.DataFrame) -> None:
    """Renderiza análise NCI em 3 blocos via st.markdown()."""
    trend     = result.get("trend", "undefined")
    htf_trend = result.get("htf_trend", "undefined")
    kl        = result.get("key_level")
    kl_q      = result.get("key_level_quality", {})
    pb        = result.get("pullback")
    bos       = result.get("bos")
    cycle     = result.get("market_cycle", {})
    ff        = result.get("four_factors", {})
    rng       = result.get("range", {})

    # Swing prices (últimos 2 de cada lado, LTF e HTF)
    sh_ltf = sl_ltf = []
    sh_htf = sl_htf = []
    sh_htf_all = sl_htf_all = []
    try:
        ms_ltf    = analyze_market_structure(classify_candles(df_ltf.copy()), window=3)
        sh_ltf    = ms_ltf["swing_highs"][-2:]
        sl_ltf    = ms_ltf["swing_lows"][-2:]
    except Exception:
        pass
    try:
        ms_htf     = analyze_market_structure(classify_candles(df_htf.copy()), window=5)
        sh_htf     = ms_htf["swing_highs"][-2:]
        sl_htf     = ms_htf["swing_lows"][-2:]
        sh_htf_all = ms_htf["swing_highs"]
        sl_htf_all = ms_htf["swing_lows"]
    except Exception:
        pass

    # HTF zones (para mostrar preço exacto do ciclo)
    htf_kl = result.get("htf_key_level")
    htf_zones = {
        "down_key_level": htf_kl["price"] if (htf_kl and htf_trend == "downtrend") else None,
        "up_key_level":   htf_kl["price"] if (htf_kl and htf_trend == "uptrend")   else None,
        "recent_high":    float(max(sh_htf_all)) if sh_htf_all else None,
        "recent_low":     float(min(sl_htf_all)) if sl_htf_all else None,
    }

    def _fmt(prices: list) -> str:
        return "  ·  ".join(f"{v:.5g}" for v in prices) if prices else "n/a"

    # ── BLOCO 1 — Leitura da Estrutura ──────────────────────────────────────
    st.markdown(f"#### {ticker}  ·  LTF {ltf}  /  HTF {htf}")
    st.markdown("**Leitura da Estrutura**")

    st.markdown(
        f"**Tendência LTF ({ltf}):** {_TREND_PT.get(trend, trend)}  \n"
        f"SH: {_fmt(sh_ltf)}  |  SL: {_fmt(sl_ltf)}"
    )
    st.markdown(
        f"**Tendência HTF ({htf}):** {_TREND_PT.get(htf_trend, htf_trend)}  \n"
        f"SH: {_fmt(sh_htf)}  |  SL: {_fmt(sl_htf)}"
    )

    if kl:
        kl_type_label  = "Up KL"   if kl.get("type") == "HL" else "Down KL"
        kl_created_by  = "último HL que criou o HH" if kl.get("type") == "HL" \
                         else "último LH que criou o LL"
        q        = kl_q.get("quality", "normal")
        q_reason = _KL_Q_REASON.get(q, q)
        st.markdown(
            f"**Key Level:** {kl_type_label}: `{kl['price']:.5g}` — {kl_created_by}.  \n"
            f"Qualidade: **{q}** ({q_reason})."
        )
    else:
        st.markdown("**Key Level:** Não identificado — estrutura insuficiente.")

    # ── BLOCO 2 — O que o mercado está a fazer agora ─────────────────────────
    st.markdown("---")
    st.markdown("**O que o mercado está a fazer agora**")

    current_price = float(df_ltf["close"].iloc[-1])
    if kl:
        kl_price = kl["price"]
        dist_pct = abs(current_price - kl_price) / kl_price * 100 if kl_price else 100
        if dist_pct < 1.0:
            phase = f"a aproximar-se do KL ({dist_pct:.2f}% de distância)"
        elif (trend == "uptrend"   and current_price > kl_price) or \
             (trend == "downtrend" and current_price < kl_price):
            phase = "Pulse Wave — preço a avançar desde o KL"
        else:
            phase = "Pullback Wave — preço a recuar em direcção ao KL"
        st.markdown(f"**Fase actual:** {phase}  |  Preço: `{current_price:.5g}`")
    else:
        st.markdown(f"**Preço actual:** `{current_price:.5g}`")

    if not cycle.get("cycle_active"):
        tb    = cycle.get("terminated_by", "?")
        zp    = htf_zones.get(tb)
        zp_s  = f" `{zp:.5g}`" if zp else ""
        st.markdown(f"**Ciclo:** Terminado — atingiu zona HTF{zp_s} ({tb}).")
    elif cycle.get("warning"):
        wz   = cycle.get("warning_zone", "")
        zp   = htf_zones.get(wz)
        zp_s = f" `{zp:.5g}`" if zp else ""
        st.markdown(f"**Ciclo a ~80%** — próximo da zona HTF{zp_s} ({wz}).")
    else:
        st.markdown("**Ciclo:** Activo — espaço para continuar.")

    if rng.get("detected"):
        st.markdown(f"**Range detectado** ({rng.get('type', '?')}) — aguardar breakout.")

    # ── BLOCO 3 — Acção sugerida ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Acção sugerida**")

    if ff.get("all_aligned"):
        direction = "LONG" if trend == "uptrend" else "SHORT"
        pattern   = _PAT_SHORT.get(pb.get("pattern", ""), pb.get("pattern", "")) if pb else "?"
        bos_label = _BOS_SHORT.get(bos.get("type", ""), "confirmação") if bos else "confirmação"
        st.markdown(
            f"✅ **SETUP VÁLIDO — Entrar {direction} na zona `{kl['price']:.5g}`**  \n"
            f"Padrão: {pattern}. Confirmar com {bos_label}."
        )

        # ── Rótulo de confluência LTF↔HTF ──────────────────────────────
        # Direção do setup vs tendência do HTF → qualidade contextual
        setup_dir = "uptrend" if direction == "LONG" else "downtrend"
        if htf_trend == setup_dir:
            st.success(
                "🟢 **Confluência** — o HTF segue a mesma direcção do setup. "
                "Maior probabilidade: vento de fundo a favor. "
                "Risco: **baixo** — tamanho de posição normal."
            )
        elif htf_trend in ("range", "undefined"):
            st.warning(
                "🟡 **HTF em Range** — o timeframe superior está lateral, sem direcção. "
                "O LTF dá a direcção, mas sem vento de fundo. "
                "Risco: **médio** — considerar posição reduzida e alvos mais curtos."
            )
        else:
            st.error(
                "🔴 **Não-confluência** — o setup vai contra a tendência do HTF "
                "(entrada de reversão / scalp). Válido no NCI, mas exige timing preciso "
                "e o HTF deve estar a esgotar-se num Key Level. "
                "Risco: **elevado** — posição reduzida, alvo curto, sair rápido se falhar."
            )
    elif rng.get("detected"):
        st.markdown(
            f"⏭️ **Skip** — mercado em range ({rng.get('type', '?')}). "
            "Aguardar breakout válido."
        )
    elif not cycle.get("cycle_active"):
        st.markdown("🚫 **Não entrar** — ciclo terminado. Aguardar nova estrutura.")
    elif trend in ("range", "undefined"):
        st.markdown("⏭️ **Skip** — sem tendência clara. Estrutura insuficiente.")
    elif not ff.get("zone"):
        st.markdown(
            f"⏳ **Aguardar** — tendência {_TREND_PT.get(trend, trend)} "
            "identificada mas sem Key Level válido."
        )
    elif not ff.get("momentum"):
        direction = "LONG" if trend == "uptrend" else "SHORT"
        kl_s      = f"`{kl['price']:.5g}`" if kl else "KL"
        st.markdown(
            f"⏳ **Aguardar pullback** ao KL {kl_s} e confirmação  \n"
            f"(P1 Two Maru / P2 Big+Small / PAC) para entrar {direction}."
        )
    else:
        kl_s = f"`{kl['price']:.5g}`" if kl else "KL"
        st.markdown(f"⏳ **Aguardar confirmação BOS** na zona {kl_s}.")


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

        htf = st.selectbox("HTF (Higher Time Frame)", ["H1", "H4", "D1"], index=1)
        ltf = st.selectbox("LTF (Lower Time Frame)",  ["M5", "M15", "H1"], index=1)

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

    col_cards, col_htf, col_ltf = st.columns([1, 2, 2])

    # ── Factor cards ──────────────────────────────────────────────────────────
    with col_cards:
        st.markdown("#### 4 Factores NCI")

        kl_detail  = (f"{kl['price']:.5g}  ·  {kl_q.get('quality', '')}"
                      if kl else "não identificado")
        pb_detail  = _PAT_SHORT.get(pb.get("pattern", ""), "") if pb else "aguardar"
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
        st.markdown("**Ciclo**")

        if not cycle.get("cycle_active"):
            tb = cycle.get("terminated_by") or "?"
            st.markdown(
                f"<span style='color:#F87171;font-weight:600'>Terminado</span>"
                f"<span style='color:#94A3B8;font-size:0.75rem'> ({tb})</span>",
                unsafe_allow_html=True,
            )
        elif cycle.get("warning"):
            wz = cycle.get("warning_zone", "")
            st.markdown(
                f"<span style='color:#F59E0B;font-weight:600'>⚠ Aviso</span>"
                f"<span style='color:#94A3B8;font-size:0.75rem'> ({wz})</span>",
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

    # ── HTF chart ─────────────────────────────────────────────────────────────
    with col_htf:
        st.caption(f"HTF — {cur_htf}")
        fig_htf = _build_htf_chart(df_htf, result)
        st.plotly_chart(fig_htf, use_container_width=True,
                        config={"displayModeBar": False})

    # ── LTF chart ─────────────────────────────────────────────────────────────
    with col_ltf:
        st.caption(f"LTF — {cur_ltf}")
        df_display = df_ltf.tail(n_candles)
        fig_ltf = _build_chart(df_display, df_ltf, df_htf, result)
        st.plotly_chart(fig_ltf, use_container_width=True,
                        config={"displayModeBar": False})

    st.markdown("---")
    st.markdown("#### Raciocínio NCI")
    _render_reasoning(result, cur_tick, cur_ltf, cur_htf, df_ltf, df_htf)
