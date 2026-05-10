"""Dashboard — Diário de Trading"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import json
from datetime import datetime, date
from engine.database import get_conn, init_db

# ── Inicializar tabelas ───────────────────────────────────────────────────────

def _ensure_tables():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS diary_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date  TEXT NOT NULL,
            market_ctx  TEXT DEFAULT '',
            app_signal  TEXT DEFAULT '',
            decision    TEXT DEFAULT '',
            result      TEXT DEFAULT '',
            learned     TEXT DEFAULT '',
            questions   TEXT DEFAULT '',
            watch_next  TEXT DEFAULT '',
            mood        TEXT DEFAULT '',
            is_insight  INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS xtb_trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument      TEXT,
            category        TEXT,
            ticker          TEXT,
            direction       TEXT,
            volume          REAL,
            open_price      REAL,
            close_price     REAL,
            open_time       TEXT,
            close_time      TEXT,
            pnl             REAL,
            stop_loss       REAL,
            take_profit     REAL,
            duration_hours  REAL,
            position_id     TEXT,
            imported_at     TEXT
        );
        """)

# ── Importar XTB ──────────────────────────────────────────────────────────────

def _import_xtb(file) -> tuple:
    """Importa ficheiro XTB. Retorna (n_imported, df_preview, error)."""
    try:
        df = pd.read_excel(file, sheet_name='Closed Positions', header=3)
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
        df = df.dropna(subset=['Instrument'])
        df = df[df['Instrument'] != 'Profit/loss']

        df['PL']         = pd.to_numeric(df['Profit/Loss'], errors='coerce').fillna(0)
        df['OpenPrice']  = pd.to_numeric(df['Open Price'],  errors='coerce').fillna(0)
        df['ClosePrice'] = pd.to_numeric(df['Close Price'], errors='coerce').fillna(0)
        df['Volume']     = pd.to_numeric(df['Volume'],      errors='coerce').fillna(0)
        df['SL']         = pd.to_numeric(df['Stop Loss'],   errors='coerce').fillna(0)
        df['TP']         = pd.to_numeric(df['Take Profit'], errors='coerce').fillna(0)

        df['OpenTime']  = pd.to_datetime(df['Open Time (UTC)'],  errors='coerce')
        df['CloseTime'] = pd.to_datetime(df['Close Time (UTC)'], errors='coerce')
        df['DurH']      = (df['CloseTime'] - df['OpenTime']).dt.total_seconds() / 3600

        now = datetime.utcnow().isoformat()
        imported = 0

        with get_conn() as conn:
            # Verificar IDs já importados
            existing_ids = {
                r[0] for r in conn.execute("SELECT position_id FROM xtb_trades").fetchall()
            }

            for _, row in df.iterrows():
                pos_id = str(row.get('Position ID', ''))
                if pos_id in existing_ids:
                    continue

                conn.execute("""
                    INSERT INTO xtb_trades
                      (instrument, category, ticker, direction, volume,
                       open_price, close_price, open_time, close_time,
                       pnl, stop_loss, take_profit, duration_hours,
                       position_id, imported_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    str(row.get('Instrument', '')),
                    str(row.get('Category', '')),
                    str(row.get('Ticker', '')),
                    str(row.get('Type', '')),
                    float(row['Volume']),
                    float(row['OpenPrice']),
                    float(row['ClosePrice']),
                    str(row['OpenTime']) if pd.notna(row['OpenTime']) else '',
                    str(row['CloseTime']) if pd.notna(row['CloseTime']) else '',
                    float(row['PL']),
                    float(row['SL']),
                    float(row['TP']),
                    float(row['DurH']) if pd.notna(row['DurH']) else 0,
                    pos_id, now,
                ))
                imported += 1

        return imported, df, None

    except Exception as e:
        return 0, None, str(e)


def _get_xtb_stats() -> dict:
    """Métricas agregadas das trades XTB."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT instrument, category, pnl, duration_hours
            FROM xtb_trades
        """).fetchall()

    if not rows:
        return {}

    df = pd.DataFrame(rows, columns=['instrument', 'category', 'pnl', 'duration_h'])
    wins   = df[df['pnl'] > 0]
    losses = df[df['pnl'] < 0]

    by_asset = df.groupby('instrument').agg(
        trades=('pnl', 'count'),
        pnl=('pnl', 'sum'),
        wins=('pnl', lambda x: (x > 0).sum())
    ).sort_values('pnl', ascending=False).reset_index()
    by_asset['wr'] = (by_asset['wins'] / by_asset['trades'] * 100).round(1)

    by_cat = df.groupby('category').agg(
        trades=('pnl', 'count'),
        pnl=('pnl', 'sum'),
    ).reset_index()

    return {
        'total':     len(df),
        'wins':      len(wins),
        'losses':    len(losses),
        'wr':        round(len(wins) / len(df) * 100, 1) if len(df) > 0 else 0,
        'pnl_total': round(df['pnl'].sum(), 2),
        'avg_win':   round(wins['pnl'].mean(), 2) if len(wins) > 0 else 0,
        'avg_loss':  round(losses['pnl'].mean(), 2) if len(losses) > 0 else 0,
        'avg_dur':   round(df['duration_h'].mean(), 1),
        'by_asset':  by_asset.head(10),
        'by_cat':    by_cat,
    }


# ── Diário ────────────────────────────────────────────────────────────────────

def _save_entry(data: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO diary_entries
              (entry_date, market_ctx, app_signal, decision, result,
               learned, questions, watch_next, mood, is_insight, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data['entry_date'], data['market_ctx'], data['app_signal'],
            data['decision'],   data['result'],     data['learned'],
            data['questions'],  data['watch_next'], data['mood'],
            1 if data.get('is_insight') else 0,
            datetime.utcnow().isoformat(),
        ))
        return cur.lastrowid


def _get_entries(days: int = 30) -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM diary_entries
            ORDER BY entry_date DESC, created_at DESC
            LIMIT 100
        """).fetchall()
    return [dict(r) for r in rows]


def _get_insights() -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM diary_entries
            WHERE is_insight = 1
            ORDER BY entry_date DESC
        """).fetchall()
    return [dict(r) for r in rows]


# ── UI ────────────────────────────────────────────────────────────────────────

MOOD_OPTIONS = ["😐 Neutro", "😊 Confiante", "🤔 Incerto", "😤 Frustrado", "🎯 Focado"]


def render():
    _ensure_tables()

    st.title("📓 Diário de Trading")

    tab1, tab2, tab3 = st.tabs(["Registar", "Historial", "XTB Import"])

    # ── TAB 1: NOVA ENTRADA ───────────────────────────────────────────────────
    with tab1:
        st.caption("2 minutos. Preenche o que conseguires — o hábito vale mais que a perfeição.")

        col1, col2 = st.columns([2, 1])

        with col1:
            entry_date = st.date_input("Data", value=date.today())
            mood = st.select_slider("Humor", options=MOOD_OPTIONS, value="😐 Neutro")

        with col2:
            is_insight = st.toggle("⭐ Insight importante", value=False,
                                   help="Marca os dias com aprendizagens chave")

        st.markdown("---")

        market_ctx = st.text_area(
            "🌐 Contexto de mercado",
            placeholder="O que está a acontecer? DXY, eventos, sentimento...",
            height=70,
        )

        app_signal = st.text_area(
            "◈ O que a APP mostrou",
            placeholder="Setups, alertas, algo que surpreendeu...",
            height=70,
        )

        decision = st.text_area(
            "🎯 Decisão",
            placeholder="Entrei em X porque... / Não entrei porque...",
            height=70,
        )

        result = st.text_input(
            "📊 Resultado",
            placeholder="ex: LONG CL=F +2.1%  /  Sem trade  /  Stop -1.3%",
        )

        learned = st.text_area(
            "💡 O que aprendi",
            placeholder="1-2 frases. Mesmo que não tenhas feito trade.",
            height=80,
        )

        col_q, col_w = st.columns(2)
        with col_q:
            questions = st.text_area(
                "❓ Ficou em aberto",
                placeholder="Dúvidas, hipóteses a testar...",
                height=68,
            )
        with col_w:
            watch_next = st.text_area(
                "👁️ Vigiar amanhã",
                placeholder="Activo, condição, evento...",
                height=68,
            )

        if st.button("💾 Guardar entrada", type="primary", use_container_width=True):
            if not learned and not decision:
                st.warning("Preenche pelo menos a decisão ou o que aprendeste.")
            else:
                _save_entry({
                    'entry_date': entry_date.isoformat(),
                    'market_ctx': market_ctx,
                    'app_signal': app_signal,
                    'decision':   decision,
                    'result':     result,
                    'learned':    learned,
                    'questions':  questions,
                    'watch_next': watch_next,
                    'mood':       mood,
                    'is_insight': is_insight,
                })
                st.success("Guardado ✓")
                st.rerun()

    # ── TAB 2: HISTORIAL ──────────────────────────────────────────────────────
    with tab2:
        entries  = _get_entries()
        insights = _get_insights()

        if not entries:
            st.info("Ainda sem entradas. Regista a primeira na tab **Registar**.")
        else:
            col_h, col_i = st.columns([2, 1])

            with col_h:
                st.markdown("#### Entradas recentes")
                for e in entries:
                    icon = "⭐ " if e['is_insight'] else ""
                    mood_short = e['mood'].split(" ")[0] if e['mood'] else ""
                    with st.expander(
                        icon + e['entry_date'] + "  " + mood_short +
                        ("  · " + e['result'] if e['result'] else ""),
                        expanded=False
                    ):
                        if e['market_ctx']:
                            st.caption("🌐 " + e['market_ctx'])
                        if e['app_signal']:
                            st.caption("◈ " + e['app_signal'])
                        if e['decision']:
                            st.markdown("**Decisão:** " + e['decision'])
                        if e['result']:
                            st.markdown("**Resultado:** " + e['result'])
                        if e['learned']:
                            st.markdown("**Aprendizagem:** " + e['learned'])
                        if e['questions']:
                            st.caption("❓ " + e['questions'])
                        if e['watch_next']:
                            st.caption("👁️ " + e['watch_next'])

            with col_i:
                st.markdown("#### ⭐ Insights")
                if not insights:
                    st.caption("Ainda sem insights marcados.")
                else:
                    for ins in insights:
                        st.markdown(
                            "<div style='background:#0D1117;border-left:3px solid #F59E0B;"
                            "padding:0.6rem 0.8rem;margin-bottom:0.4rem;font-size:0.8rem'>"
                            "<span style='color:#F59E0B;font-size:0.65rem'>" + ins['entry_date'] + "</span><br>"
                            + (ins['learned'] or ins['decision'] or '') +
                            "</div>",
                            unsafe_allow_html=True
                        )

    # ── TAB 3: XTB IMPORT ────────────────────────────────────────────────────
    with tab3:
        st.markdown("#### Importar histórico XTB")
        st.caption("Exporta do XTB: Relatórios → Histórico de transacções → Excel")

        uploaded = st.file_uploader("Ficheiro Excel XTB", type=["xlsx"])

        if uploaded:
            n, df_prev, err = _import_xtb(uploaded)
            if err:
                st.error("Erro: " + err)
            elif n == 0:
                st.info("Todas as trades já estavam importadas.")
            else:
                st.success(str(n) + " trades importadas com sucesso!")

        # Métricas XTB
        stats = _get_xtb_stats()
        if stats:
            st.markdown("---")
            st.markdown("#### Análise do teu histórico XTB")

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Trades", stats['total'])
            c2.metric("Win Rate", str(stats['wr']) + "%",
                      delta=str(round(stats['wr'] - 50, 1)) + "pp vs 50%")
            c3.metric("PnL Total", str(stats['pnl_total']) + "€")
            c4.metric("Avg Win",  str(stats['avg_win'])  + "€")
            c5.metric("Avg Loss", str(stats['avg_loss']) + "€")

            st.markdown("---")

            col_a, col_c = st.columns(2)

            with col_a:
                st.markdown("**Por activo** (ordenado por PnL)")
                df_a = stats['by_asset']
                for _, row in df_a.iterrows():
                    pnl_color = "#34D399" if row['pnl'] > 0 else "#F87171"
                    icon      = "✅" if row['pnl'] > 0 else "❌"
                    st.markdown(
                        "<div style='display:flex;justify-content:space-between;"
                        "font-size:0.8rem;padding:0.2rem 0;border-bottom:1px solid #1E293B'>"
                        "<span>" + icon + " " + str(row['instrument']) + "</span>"
                        "<span style='color:#64748B'>" + str(int(row['trades'])) + "t · " + str(row['wr']) + "% WR</span>"
                        "<span style='color:" + pnl_color + ";font-weight:700'>" + str(round(row['pnl'], 2)) + "€</span>"
                        "</div>",
                        unsafe_allow_html=True
                    )

            with col_c:
                st.markdown("**Por categoria**")
                df_c = stats['by_cat']
                for _, row in df_c.iterrows():
                    pnl_color = "#34D399" if row['pnl'] > 0 else "#F87171"
                    st.markdown(
                        "<div style='display:flex;justify-content:space-between;"
                        "font-size:0.8rem;padding:0.3rem 0;border-bottom:1px solid #1E293B'>"
                        "<span style='font-weight:700'>" + str(row['category']) + "</span>"
                        "<span style='color:#64748B'>" + str(int(row['trades'])) + " trades</span>"
                        "<span style='color:" + pnl_color + ";font-weight:700'>" + str(round(row['pnl'], 2)) + "€</span>"
                        "</div>",
                        unsafe_allow_html=True
                    )

                st.markdown("")
                st.markdown("**Duração média:** " + str(stats['avg_dur']) + "h por trade")

                # Insight automático
                if stats.get('by_cat') is not None and len(stats['by_cat']) > 0:
                    df_c2 = stats['by_cat'].sort_values('pnl', ascending=False)
                    best_cat  = df_c2.iloc[0]['category']
                    worst_cat = df_c2.iloc[-1]['category']
                    if df_c2.iloc[-1]['pnl'] < 0:
                        st.info(
                            "💡 **Insight automático:** " + best_cat + " está a dar lucro · " +
                            worst_cat + " está a perder. Vale a pena reflectir porquê."
                        )
