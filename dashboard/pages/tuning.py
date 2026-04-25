"""Dashboard — Tuning Agent"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

try:
    from engine.tuning_agent import TuningAgent
    AGENT_AVAILABLE = True
    AGENT_ERROR = ""
except ImportError as e:
    AGENT_AVAILABLE = False
    AGENT_ERROR = str(e)


def render():
    st.title("🔧 Tuning Agent")
    st.caption("Afina a estratégia EP em linguagem natural. O agente lê ficheiros, corre backtests e actualiza o knowledge JSON automaticamente.")

    if not AGENT_AVAILABLE:
        st.error("Agente não disponível: " + AGENT_ERROR)
        return

    # Inicializar agente na sessão
    if "tuning_agent" not in st.session_state:
        st.session_state.tuning_agent = TuningAgent()

    if "tuning_messages" not in st.session_state:
        st.session_state.tuning_messages = []

    if "tuning_tools_log" not in st.session_state:
        st.session_state.tuning_tools_log = []

    # Sidebar com ferramentas disponíveis e sugestões
    with st.sidebar:
        st.markdown("### 🛠️ Ferramentas disponíveis")
        st.markdown("""
- **read_file** — lê qualquer ficheiro do projecto
- **write_file** — edita estratégia ou knowledge JSON
- **run_backtest** — corre backtest e devolve métricas
- **update_knowledge** — regista lição aprendida
        """)

        st.markdown("### 💡 Exemplos")
        examples = [
            "Lê a estratégia EP actual e mostra-me os parâmetros principais",
            "Testa stop de 5% vs 6% e diz qual é melhor",
            "Corre um backtest com ep_close no universo principal",
            "Muda o MIN_VOLUME_RATIO para 4x e testa o impacto",
            "Analisa o knowledge JSON e sugere próximas afinações",
            "Adiciona ao knowledge JSON a lição sobre volume 5-10x",
        ]
        for ex in examples:
            if st.button(ex, use_container_width=True, key="ex_" + ex[:20]):
                st.session_state.tuning_input = ex

        st.markdown("---")
        if st.button("🗑️ Limpar conversa", use_container_width=True):
            st.session_state.tuning_agent.clear_history()
            st.session_state.tuning_messages = []
            st.session_state.tuning_tools_log = []
            st.rerun()

    # Área principal — histórico de mensagens
    chat_container = st.container()

    with chat_container:
        for msg in st.session_state.tuning_messages:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            elif msg["role"] == "assistant":
                with st.chat_message("assistant", avatar="🔧"):
                    st.markdown(msg["content"])
            elif msg["role"] == "tool":
                with st.expander(f"🔨 {msg['tool_name']} — {msg['summary']}", expanded=False):
                    if msg.get("input"):
                        st.caption("Input:")
                        st.json(msg["input"])
                    st.caption("Resultado:")
                    st.code(msg["result"][:2000] + ("..." if len(msg["result"]) > 2000 else ""))

    # Input do utilizador
    user_input = st.chat_input(
        "Pede uma afinação... ex: 'Testa MIN_VOLUME_RATIO=4 e compara com o actual'",
        key="tuning_chat_input",
    )

    # Suporte a clique nos exemplos
    if hasattr(st.session_state, "tuning_input") and st.session_state.tuning_input:
        user_input = st.session_state.tuning_input
        st.session_state.tuning_input = ""

    if user_input:
        # Mostrar mensagem do utilizador imediatamente
        st.session_state.tuning_messages.append({
            "role": "user", "content": user_input
        })

        # Placeholder para mostrar progresso
        with st.spinner("Agente a trabalhar..."):
            tools_called = []

            def on_tool_use(tool_name, tool_input, result):
                """Callback chamado quando o agente usa uma ferramenta."""
                # Criar sumário legível
                if tool_name == "read_file":
                    summary = f"leu {tool_input.get('path', '')}"
                elif tool_name == "write_file":
                    summary = f"editou {tool_input.get('path', '')} — {tool_input.get('description', '')}"
                elif tool_name == "run_backtest":
                    summary = f"backtest {tool_input.get('universe', 'principal')} | {tool_input.get('entry_mode', 'ep_close')}"
                elif tool_name == "update_knowledge":
                    summary = "actualizou knowledge JSON"
                else:
                    summary = tool_name

                tools_called.append({
                    "role":      "tool",
                    "tool_name": tool_name,
                    "summary":   summary,
                    "input":     tool_input,
                    "result":    result,
                })

            response = st.session_state.tuning_agent.chat(
                user_input,
                on_tool_use=on_tool_use,
            )

        # Adicionar ferramentas usadas ao histórico visual
        for tool_msg in tools_called:
            st.session_state.tuning_messages.append(tool_msg)

        # Adicionar resposta do agente
        st.session_state.tuning_messages.append({
            "role": "assistant", "content": response
        })

        st.rerun()
