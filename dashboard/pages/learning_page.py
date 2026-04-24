"""Dashboard - Aprendizagem e Estatísticas (Nível 1 + 2)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd

try:
    from engine.learning import LearningEngine
    from engine.trade_analyst import TradeAnalyst
    ENGINE_AVAILABLE = True
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)


def render():
    st.title("Aprendizagem — O que o sistema sabe")
    st.markdown("Estatísticas e lições acumuladas de todos os trades.")

    if not ENGINE_AVAILABLE:
        st.error("Engine nao disponivel.", icon="🔴")
        return

    le      = LearningEngine()
    analyst = TradeAnalyst()

    col1, col2, col3 = st.columns([2, 1, 1])
    with col2:
        if st.button("🔄 Actualizar stats", use_container_width=True):
            with st.spinner("A calcular..."):
                le.update()
            st.success("Estatísticas actualizadas!")
            st.rerun()
    with col3:
        if st.button("🧠 Analisar trades", use_container_width=True, type="primary"):
            with st.spinner("A analisar trades fechados..."):
                lessons = analyst.analyse_pending()
            if lessons:
                st.success(str(len(lessons)) + " novas lições!")
            else:
                st.info("Sem novos trades para analisar.")
            st.rerun()

    report = le.get_full_report()
    total  = report.get("total_trades", 0)
    last   = report.get("last_update", "nunca")

    lessons_count = len(analyst.get_lessons(limit=1000))

    c1, c2, c3 = st.columns(3)
    c1.metric("Total de Trades",    total)
    c2.metric("Lições Acumuladas",  lessons_count)
    c3.metric("Última actualização", last)

    if total == 0:
        st.info("Corre backtests para acumular histórico.")
        return

    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Por Sector", "Por Catalisador", "Por Janela",
        "Por Score", "Sugar Babies", "📖 Lições"
    ])

    with tab1:
        st.subheader("Performance por Sector")
        data = report.get("by_sector", {})
        if data:
            _render_stats_table(data, "Sector")
            _render_insights(data, "sector")
        else:
            st.info("Sem dados.")

    with tab2:
        st.subheader("Performance por Tipo de Catalisador")
        data = report.get("by_catalyst", {})
        if data:
            _render_stats_table(data, "Catalisador")
            _render_insights(data, "catalisador")
        else:
            st.info("Sem dados por catalisador. Necessita de decisões confirmadas.")

    with tab3:
        st.subheader("Performance por Janela de Entrada")
        data = report.get("by_window", {})
        if data:
            _render_stats_table(data, "Janela")
            prime = data.get("PRIME", {})
            open_ = data.get("OPEN", {})
            if prime and open_ and prime.get("trades", 0) >= 3 and open_.get("trades", 0) >= 3:
                diff = prime.get("win_rate", 0) - open_.get("win_rate", 0)
                if abs(diff) > 10:
                    if diff > 0:
                        st.success("💡 PRIME tem win rate " + str(round(diff, 1)) +
                                   "% superior a OPEN. Priorizar entradas PRIME.")
                    else:
                        st.info("💡 OPEN tem win rate " + str(round(-diff, 1)) +
                                "% superior a PRIME neste histórico.")
        else:
            st.info("Sem dados.")

    with tab4:
        st.subheader("Performance por Range de Score EP")
        data = report.get("by_score", {})
        if data:
            ordered = dict(sorted(data.items(), reverse=True))
            _render_stats_table(ordered, "Score Range")
        else:
            st.info("Sem dados.")

    with tab5:
        st.subheader("Sugar Babies vs Não Sugar Babies")
        data  = report.get("sugar_baby", {})
        sugar = data.get("sugar_baby", {})
        other = data.get("non_sugar_baby", {})
        if sugar and other and sugar.get("trades", 0) >= 2:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**⭐ Sugar Babies**")
                st.metric("Trades",        sugar.get("trades", 0))
                st.metric("Win Rate",      str(sugar.get("win_rate", 0)) + "%")
                st.metric("Profit Factor", sugar.get("profit_factor", 0))
                st.metric("Avg P&L",       str(sugar.get("avg_pnl", 0)) + "%")
            with c2:
                st.markdown("**Não Sugar Babies**")
                st.metric("Trades",        other.get("trades", 0))
                st.metric("Win Rate",      str(other.get("win_rate", 0)) + "%")
                st.metric("Profit Factor", other.get("profit_factor", 0))
                st.metric("Avg P&L",       str(other.get("avg_pnl", 0)) + "%")
            diff = sugar.get("win_rate", 0) - other.get("win_rate", 0)
            if diff > 10:
                st.success("⭐ Sugar Babies têm win rate " + str(round(diff, 1)) +
                           "% superior. Prioridade máxima quando fazem EP.")
            elif diff < -10:
                st.warning("⚠️ Não Sugar Babies têm melhor performance. Reavaliar critérios.")
        else:
            st.info("Dados insuficientes para comparação.")

    # ── Tab 6: Lições (Nível 2) ───────────────────────────────────────────────
    with tab6:
        st.subheader("📖 Lições Aprendidas")
        st.caption("Análise narrativa de cada trade fechado pelo especialista EP.")

        lessons = analyst.get_lessons(limit=50)

        if not lessons:
            st.info(
                "Ainda sem lições. Clica **🧠 Analisar trades** para o especialista "
                "analisar os trades fechados e extrair padrões."
            )
        else:
            # Filtros
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                filter_outcome = st.selectbox(
                    "Filtrar por resultado",
                    ["Todos", "WIN", "LOSS"],
                )
            with col_f2:
                filter_ticker = st.text_input("Filtrar por ticker", "").upper()

            filtered = lessons
            if filter_outcome != "Todos":
                filtered = [l for l in filtered if l.get("outcome") == filter_outcome]
            if filter_ticker:
                filtered = [l for l in filtered if l.get("ticker") == filter_ticker]

            st.caption(str(len(filtered)) + " lições")

            # Resumo de sugestões de critérios
            suggestions = analyst.get_criteria_suggestions()
            if suggestions:
                with st.expander("💡 Sugestões de ajuste aos critérios (" +
                                 str(len(suggestions)) + ")"):
                    for s in suggestions:
                        if s.get("criteria_suggestion"):
                            st.markdown(
                                "- **" + str(s["count"]) + "x** — " +
                                s["criteria_suggestion"]
                            )

            st.markdown("---")

            # Lista de lições
            for lesson in filtered:
                outcome = lesson.get("outcome", "")
                ticker  = lesson.get("ticker", "")
                pnl     = lesson.get("pnl_pct", 0)
                icon    = "✅" if outcome == "WIN" else "❌"
                color   = "#22c55e" if outcome == "WIN" else "#ef4444"

                with st.expander(
                    icon + " **" + ticker + "**  " +
                    "{:+.1f}%".format(pnl) + "  |  " +
                    lesson.get("pattern_tag", "") + "  |  " +
                    lesson.get("created_at", "")[:10],
                    expanded=False,
                ):
                    st.markdown("**Lição principal:**")
                    st.info(lesson.get("key_learning", ""))

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if lesson.get("what_worked"):
                            st.markdown("**✅ O que funcionou:**")
                            st.markdown(lesson["what_worked"])
                        if lesson.get("catalyst_assessment"):
                            st.markdown("**Catalisador:**")
                            st.markdown(lesson["catalyst_assessment"])
                    with col_b:
                        if lesson.get("what_failed"):
                            st.markdown("**❌ O que falhou:**")
                            st.markdown(lesson["what_failed"])
                        if lesson.get("timing_assessment"):
                            st.markdown("**Timing:**")
                            st.markdown(lesson["timing_assessment"])

                    if lesson.get("criteria_suggestion"):
                        st.markdown("**💡 Sugestão de critério:**")
                        st.success(lesson["criteria_suggestion"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _render_stats_table(data: dict, label: str):
    rows = []
    for key, stats in data.items():
        if not isinstance(stats, dict) or stats.get("trades", 0) == 0:
            continue
        rows.append({
            label:           key,
            "Trades":        stats.get("trades", 0),
            "Win Rate":      str(stats.get("win_rate", 0)) + "%",
            "Profit Factor": stats.get("profit_factor", 0),
            "Avg Win":       str(stats.get("avg_win", 0)) + "%",
            "Avg Loss":      str(stats.get("avg_loss", 0)) + "%",
            "Avg P&L":       str(stats.get("avg_pnl", 0)) + "%",
            "_wr":           stats.get("win_rate", 0),
        })
    if not rows:
        st.info("Sem dados.")
        return
    df = pd.DataFrame(rows).sort_values("_wr", ascending=False).drop(columns=["_wr"])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_insights(data: dict, category: str):
    valid = [
        (k, v) for k, v in data.items()
        if isinstance(v, dict) and v.get("trades", 0) >= 3
    ]
    if len(valid) < 2:
        return
    best  = max(valid, key=lambda x: x[1]["win_rate"])
    worst = min(valid, key=lambda x: x[1]["win_rate"])
    if best[1]["win_rate"] > 55:
        st.success(
            "💡 Melhor " + category + ": **" + best[0] + "** — " +
            str(best[1]["win_rate"]) + "% win rate | " +
            str(best[1]["trades"]) + " trades"
        )
    if worst[1]["win_rate"] < 40 and worst[1]["trades"] >= 5:
        st.warning(
            "⚠️ Pior " + category + ": **" + worst[0] + "** — " +
            str(worst[1]["win_rate"]) + "% win rate | " +
            str(worst[1]["trades"]) + " trades — considerar excluir"
        )
