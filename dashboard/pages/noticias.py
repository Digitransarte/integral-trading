"""
Integral Trading — Página Notícias
====================================
Mostra as notícias destiladas (agrupadas por driver), lidas da base de dados.
Botão para atualizar (recolhe + destila + guarda) — única ação que gasta API.
"""
import streamlit as st

from engine.knowledge import load_commodity, list_commodities
from engine.news_store import ler, guardar


def _emoji_sentido(s: str) -> str:
    return {"alta": "🟢 alta", "baixa": "🔴 baixa", "neutro": "⚪ neutro"}.get(s, s)


def render():
    st.markdown("# ◈ Notícias")
    st.caption("Notícias destiladas por IA e agrupadas por driver. O horizonte imediato.")

    commodities = list_commodities()
    if not commodities:
        st.warning("Nenhuma ficha encontrada em knowledge/commodities/.")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        cid = st.selectbox("Matéria-prima", commodities,
                           format_func=lambda c: c.capitalize())
    with col2:
        st.write("")
        atualizar = st.button("🔄 Atualizar notícias", use_container_width=True)

    ficha = load_commodity(cid)

    # Atualização (gasta API) — só quando o utilizador carrega
    if atualizar:
        with st.spinner("A recolher e destilar notícias (pode demorar)..."):
            from engine.news_feed import recolher_finnhub
            from engine.news_distiller import destilar_lote
            # keywords a partir do nome + termos macro genéricos
            kws = [ficha.nome.lower(), "gold", "dollar", "fed", "rate",
                   "inflation", "treasury", "yields"]
            brutas = recolher_finnhub(kws, dias=4)
            destiladas = destilar_lote(brutas, cid)
            novas = guardar(cid, destiladas)
        st.success(f"{novas} notícias novas guardadas "
                   f"({len(destiladas)} materiais, resto descartado como ruído).")

    # Leitura (barata, da base de dados)
    noticias = ler(cid, dias=14)

    if not noticias:
        st.info("Ainda não há notícias guardadas. Carrega em **Atualizar notícias**.")
        return

    # Resumo no topo: balanço de sentido
    altas = sum(1 for n in noticias if n["sentido"] == "alta")
    baixas = sum(1 for n in noticias if n["sentido"] == "baixa")
    st.markdown(f"**{len(noticias)} notícias** · 🟢 {altas} alta · 🔴 {baixas} baixa  "
                f"<span style='color:gray'>(relevância já ajustada pelo tempo)</span>",
                unsafe_allow_html=True)

    # Agrupar por driver
    por_driver: dict[str, list] = {}
    for n in noticias:
        por_driver.setdefault(n["driver_nome"], []).append(n)

    # Ordenar drivers pela relevância ajustada máxima de cada grupo
    drivers_ordenados = sorted(
        por_driver.items(),
        key=lambda kv: max(x["relevancia_ajustada"] for x in kv[1]),
        reverse=True,
    )

    for driver_nome, items in drivers_ordenados:
        st.markdown(f"### {driver_nome}")
        for n in items:
            with st.container(border=True):
                linha = (f"**[{n['relevancia_ajustada']}]** "
                         f"{_emoji_sentido(n['sentido'])} · "
                         f"<span style='color:gray'>{n['fonte']} · {n['data']}</span>")
                st.markdown(linha, unsafe_allow_html=True)
                st.write(n["resumo"])
                if n.get("impacto"):
                    st.caption(f"→ {n['impacto']}")
                if n.get("url"):
                    st.caption(f"[ler fonte]({n['url']})")