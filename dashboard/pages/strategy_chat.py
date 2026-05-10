"""Dashboard - Chat com Especialista de Estratégia"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime

try:
    from engine.specialists.ep_specialist import EPSpecialist
    ENGINE_AVAILABLE = True
    ENGINE_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    ENGINE_ERROR = str(e)

# Registo de especialistas disponíveis
SPECIALISTS = {
    "ep": {
        "label":    "Episodic Pivot",
        "icon":     "⚡",
        "class":    "EPSpecialist",
        "phase":    "forward_testing",
        "desc":     "Especialista no método EP do Pradeep Bonde. Conhece os critérios originais, o conceito de Neglect, a variante 9M EP e Sugar Babies.",
    },
    # Futuros especialistas:
    # "canslim": {...},
    # "momentum": {...},
}

PHASE_LABELS = {
    "development":    "🔧 Desenvolvimento",
    "backtesting":    "📊 Backtesting",
    "forward_testing": "🔬 Forward Testing",
    "live":           "🚀 Live Trading",
}


def render():
    st.title("Especialistas de Estratégia")
    st.markdown("Conversa com os especialistas, aprende os métodos e analisa resultados.")

    if not ENGINE_AVAILABLE:
        st.error("Engine nao disponivel: " + ENGINE_ERROR, icon="🔴")
        return

    st.markdown("---")

    # ── Selecção de especialista ──────────────────────────────────────────────
    col1, col2 = st.columns([1, 3])

    with col1:
        st.markdown("**Especialista**")
        selected = st.radio(
            "esp",
            list(SPECIALISTS.keys()),
            format_func=lambda x: SPECIALISTS[x]["icon"] + " " + SPECIALISTS[x]["label"],
            label_visibility="collapsed",
        )

        spec_info = SPECIALISTS[selected]
        phase = PHASE_LABELS.get(spec_info["phase"], spec_info["phase"])
        st.caption("Fase: " + phase)
        st.caption(spec_info["desc"])

        st.markdown("---")

        # Sugestões de perguntas
        st.markdown("**Perguntas sugeridas**")
        suggestions = _get_suggestions(selected)
        for s in suggestions:
            if st.button(s, key="sug_" + s[:20], use_container_width=True):
                st.session_state["pending_message"] = s
                st.rerun()

        st.markdown("---")
        if st.button("🗑 Limpar histórico", use_container_width=True):
            specialist = _get_specialist(selected)
            specialist.clear_history()
            st.success("Histórico limpo.")
            st.rerun()

    with col2:
        specialist = _get_specialist(selected)
        _render_chat(specialist, selected)


def _render_chat(specialist, selected_key):
    """Renderiza o chat com histórico persistente."""
    st.subheader(
        SPECIALISTS[selected_key]["icon"] + " " +
        SPECIALISTS[selected_key]["label"]
    )

    # ── Área de histórico ─────────────────────────────────────────────────────
    history = specialist.get_chat_history(limit=100)

    chat_container = st.container()
    with chat_container:
        if not history:
            st.info(
                "Nenhuma conversa ainda. Faz uma pergunta para começar.\n\n"
                "Podes perguntar sobre o método, pedir análise de resultados, "
                "ou discutir ajustes à estratégia."
            )
        else:
            for msg in history:
                role    = msg["role"]
                content = msg["content"]
                time    = msg.get("created_at", "")[:16].replace("T", " ")

                if role == "user":
                    with st.chat_message("user"):
                        st.markdown(content)
                        st.caption(time)
                else:
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown(content)
                        st.caption(time)

    # ── Input ─────────────────────────────────────────────────────────────────
    st.markdown("---")

    # Processar mensagem pendente (de sugestão clicada)
    pending = st.session_state.pop("pending_message", None)

    user_input = st.chat_input(
        "Pergunta ao especialista " + SPECIALISTS[selected_key]["label"] + "...",
    )

    message_to_send = pending or user_input

    if message_to_send:
        # Mostrar mensagem do utilizador imediatamente
        with st.chat_message("user"):
            st.markdown(message_to_send)

        # Obter resposta do especialista
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("A pensar..."):
                response = specialist.chat(message_to_send)
            st.markdown(response)

        st.rerun()

    # ── Acções rápidas ────────────────────────────────────────────────────────
    with st.expander("Análise rápida", expanded=False):
        col_a, col_b = st.columns(2)

        with col_a:
            if st.button("📊 Analisar último backtest", use_container_width=True):
                summary = _get_last_backtest(SPECIALISTS[selected_key]["label"])
                if summary:
                    with st.spinner("A analisar resultados..."):
                        response = specialist.analyse_backtest(summary)
                    st.markdown(response)
                else:
                    st.info("Nenhum backtest encontrado para esta estratégia.")

        with col_b:
            if st.button("📈 Resumo da estratégia", use_container_width=True):
                msg = "Faz-me um resumo completo do estado actual da estratégia: o que está a funcionar, o que precisa de melhoria, e a tua recomendação para os próximos passos."
                with st.spinner("A preparar resumo..."):
                    response = specialist.chat(msg)
                st.markdown(response)


def _get_specialist(key: str) -> "BaseSpecialist":
    """Instancia o especialista pelo key."""
    if key == "ep":
        return EPSpecialist()
    raise ValueError("Especialista desconhecido: " + key)


def _get_suggestions(key: str) -> list:
    """Sugestões de perguntas por especialista."""
    suggestions = {
        "ep": [
            "O que é o conceito de Neglect?",
            "Qual a diferença entre EP clássico e 9M EP?",
            "Como entro num EP atrasado?",
            "Porque é que o biotech falha no sistema?",
            "Como calculo o stop loss correctamente?",
            "O que são Sugar Babies?",
            "Quando devo evitar entrar num EP?",
        ],
    }
    return suggestions.get(key, [])


def _get_last_backtest(strategy_name: str) -> dict:
    """Busca o último backtest da estratégia."""
    try:
        from engine.database import get_conn, init_db
        init_db()
        with get_conn() as conn:
            row = conn.execute("""
                SELECT strategy_name, total_trades, win_rate, profit_factor,
                       total_return, max_drawdown, avg_hold_days, run_date
                FROM backtest_runs
                WHERE strategy_name = ?
                ORDER BY run_date DESC LIMIT 1
            """, (strategy_name,)).fetchone()
        if row:
            return dict(row)
    except Exception:
        pass
    return None
