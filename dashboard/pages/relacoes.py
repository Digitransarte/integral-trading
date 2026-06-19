"""
Integral Trading — Página Relações
====================================
Mostra as correlações da matéria-prima com os ativos relacionados,
o regime de mercado inferido, e avisos de descolagem face à ficha.
"""
import streamlit as st

from engine.correlations import analyze_correlations, detectar_regime
from engine.knowledge import load_commodity, list_commodities


def render():
    st.markdown("# ◈ Relações de Mercado")
    st.caption("Correlações móveis (60 dias) e regime inferido, face à ficha de conhecimento.")

    commodities = list_commodities()
    if not commodities:
        st.warning("Nenhuma ficha de conhecimento encontrada em knowledge/commodities/.")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        cid = st.selectbox("Matéria-prima", commodities,
                           format_func=lambda c: c.capitalize())
    with col2:
        atualizar = st.button("🔄 Atualizar", use_container_width=True)

    # Carrega a ficha (para o resumo) — barato, sem rede
    ficha = load_commodity(cid)
    st.markdown(f"**{ficha.nome}** — {ficha.natureza}")

    # Cálculo (com rede; cache para não repetir a cada interação)
    @st.cache_data(ttl=1800, show_spinner="A calcular correlações...")
    def _calcular(commodity_id: str):
        res = analyze_correlations(commodity_id)
        reg = detectar_regime(res)
        return res, reg

    if atualizar:
        _calcular.clear()

    try:
        res, reg = _calcular(cid)
    except Exception as e:
        st.error(f"Erro ao calcular correlações: {e}")
        return

    if not res.pares:
        st.warning("Sem dados suficientes para calcular correlações.")
        for a in res.avisos:
            st.caption(f"⚠ {a}")
        return

    # ── Regime inferido ──────────────────────────────────────────────
    st.markdown("### Regime ativo")
    conf = reg.get("confianca", 0)
    if reg["regime"] == "indefinido":
        st.info(f"**Regime indefinido** — {reg['justificacao']}")
    else:
        st.success(f"**{reg['regime']}**  ·  confiança {conf:.0%}")
        st.caption(f"→ {reg['justificacao']}")
        for s in reg.get("sinais_secundarios", []):
            st.caption(f"· {s}")

    # ── Tabela de correlações ────────────────────────────────────────
    st.markdown("### Correlações (60 dias)")

    def _emoji(estado: str) -> str:
        return {"alinhado": "✅", "DESCOLADO": "⚠️",
                "contextual": "◽", "neutro": "➖",
                "sem_referência": "❔"}.get(estado, "")

    linhas = []
    for p in res.pares:
        linhas.append({
            "Ativo": p["ativo"],
            "Coef.": p["coef"],
            "Força": p["forca"],
            "Observado": p["sinal_observado"],
            "Esperado": p["sentido_esperado"],
            "Estado": f"{_emoji(p['estado'])} {p['estado']}",
        })
    st.dataframe(linhas, use_container_width=True, hide_index=True)

    # ── Avisos de descolagem ─────────────────────────────────────────
    descolados = [p for p in res.pares if p["estado"] == "DESCOLADO"]
    if descolados:
        st.markdown("### ⚠️ Descolagens")
        for p in descolados:
            st.warning(
                f"**{p['ativo']}**: a ficha esperava *{p['sentido_esperado']}*, "
                f"observa-se *{p['sinal_observado']}* (coef {p['coef']:+.2f}). "
                f"Possível mudança de regime."
            )
    else:
        st.caption("Sem descolagens — todas as relações com referência estão alinhadas com a ficha.")