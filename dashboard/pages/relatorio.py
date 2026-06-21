"""
Integral Trading — Página Relatório Matinal
=============================================
A síntese das camadas (regime, notícias, NCI) numa leitura única.
O 'produto' da app: lê o mundo e diz onde as camadas convergem.
"""
import streamlit as st

from engine.knowledge import list_commodities
from engine.morning_report import gerar_relatorio


_COR_CONV = {"alta": "🟢", "média": "🟡", "baixa": "🔴"}
_COR_DIR = {"alta": "📈", "baixa": "📉", "mista": "🔀"}
_COR_VOTO = {"alta": "📈 alta", "baixa": "📉 baixa", "neutro": "➖ neutro"}


def render():
    st.markdown("# ◈ Relatório Matinal")
    st.caption("A síntese de todas as camadas numa leitura única do dia.")

    commodities = list_commodities()
    if not commodities:
        st.warning("Nenhuma ficha encontrada.")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        cid = st.selectbox("Matéria-prima", commodities,
                           format_func=lambda c: c.capitalize())
    with col2:
        st.write("")
        gerar = st.button("📋 Gerar relatório", use_container_width=True)

    if not gerar:
        st.info("Carrega em **Gerar relatório** para a leitura do dia.")
        return

    with st.spinner("A juntar as camadas..."):
        r = gerar_relatorio(cid)

    # ── Cabeçalho: a síntese em destaque ─────────────────────────────
    st.markdown(f"### {r.nome} · {r.gerado_em}")

    dir_emoji = _COR_DIR.get(r.direcao_sintese, "")
    conv_emoji = _COR_CONV.get(r.conviccao, "")
    if r.direcao_sintese == "alta":
        st.success(f"## {dir_emoji} Viés ALTA · convicção {r.conviccao.upper()} {conv_emoji}")
    elif r.direcao_sintese == "baixa":
        st.error(f"## {dir_emoji} Viés BAIXA · convicção {r.conviccao.upper()} {conv_emoji}")
    else:
        st.warning(f"## {dir_emoji} Sinais MISTOS · convicção {r.conviccao.upper()} {conv_emoji}")
    st.markdown(f"**{r.leitura}**")

    st.markdown("---")

    # ── Os votos das camadas ─────────────────────────────────────────
    st.markdown("### Como votam as camadas")
    for v in r.votos:
        st.markdown(f"**{v.camada}** — {_COR_VOTO.get(v.direcao, v.direcao)}  \n"
                    f"<span style='color:gray'>{v.detalhe}</span>",
                    unsafe_allow_html=True)

    st.markdown("---")

    # ── Detalhe: Regime ──────────────────────────────────────────────
    st.markdown("### Regime de mercado")
    reg = r.regime
    if reg.get("regime") != "indefinido":
        st.markdown(f"**{reg.get('regime')}** · confiança {reg.get('confianca',0):.0%}")
        st.caption(reg.get("justificacao", ""))
    else:
        st.caption("Regime indefinido.")

    # ── Detalhe: NCI ─────────────────────────────────────────────────
    st.markdown("### Sinal técnico (NCI)")
    nci = r.nci
    if nci.get("direcao"):
        rotulo = nci.get("rotulo", "")
        st.markdown(f"Setup **{nci['direcao']}** · {rotulo}")
        st.caption(nci.get("nota", ""))
    else:
        st.caption(f"Sem setup: {nci.get('nota','')}")

    # ── Detalhe: Notícias (top 5) ────────────────────────────────────
    st.markdown("### Notícias materiais")
    if r.noticias:
        for n in r.noticias[:5]:
            sent = {"alta": "📈", "baixa": "📉", "neutro": "➖"}.get(n.get("sentido"), "")
            st.markdown(f"{sent} **[{n.get('relevancia_ajustada','')}]** "
                        f"{n.get('resumo','')}  \n"
                        f"<span style='color:gray'>{n.get('driver_nome','')} · "
                        f"{n.get('fonte','')} · {n.get('data','')}</span>",
                        unsafe_allow_html=True)
    else:
        st.caption("Sem notícias materiais. Atualiza na página Notícias.")