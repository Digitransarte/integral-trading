"""
Integral Trading — Relatório Matinal
======================================
Junta as camadas (regime, notícias, NCI) numa síntese de convergência.
Determinístico (sem IA por agora). Cada camada vota numa direção; a
convicção mede o grau de concordância entre votos.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from engine.knowledge import load_commodity
from engine.correlations import analyze_correlations, detectar_regime
from engine.news_store import ler as ler_noticias

from engine.data_feed import DataFeed
from engine.nci_engine import avaliar_setup

logger = logging.getLogger(__name__)


@dataclass
class Voto:
    camada: str          # "Regime" / "Notícias" / "NCI"
    direcao: str         # "alta" / "baixa" / "neutro"
    detalhe: str         # explicação curta


@dataclass
class MorningReport:
    commodity: str
    nome: str
    gerado_em: str
    regime: dict = field(default_factory=dict)
    noticias: list = field(default_factory=list)
    nci: dict = field(default_factory=dict)
    votos: list = field(default_factory=list)
    conviccao: str = ""          # "alta" / "média" / "baixa"
    direcao_sintese: str = ""    # "alta" / "baixa" / "mista"
    leitura: str = ""            # frase de síntese


# ── Tradução de cada camada num voto ────────────────────────────────────

def _voto_regime(reg: dict) -> Voto:
    nome = reg.get("regime", "indefinido")
    # mapeamento simples: que regimes empurram o ouro para onde
    baixistas = ("Macro / taxas",)
    altistas = ("Risk-off / refúgio", "Estrutural / desdolarização")
    if nome in baixistas:
        return Voto("Regime", "baixa", f"{nome} — dólar/yields a pesar")
    if nome in altistas:
        return Voto("Regime", "alta", f"{nome} — favorável ao ouro")
    return Voto("Regime", "neutro", f"{nome}")


def _voto_noticias(noticias: list) -> Voto:
    if not noticias:
        return Voto("Notícias", "neutro", "sem notícias materiais")
    # soma ponderada pela relevância ajustada
    score = 0.0
    for n in noticias:
        peso = n.get("relevancia_ajustada", n.get("relevancia", 0))
        if n.get("sentido") == "alta":
            score += peso
        elif n.get("sentido") == "baixa":
            score -= peso
    altas = sum(1 for n in noticias if n.get("sentido") == "alta")
    baixas = sum(1 for n in noticias if n.get("sentido") == "baixa")
    detalhe = f"{altas} alta / {baixas} baixa (saldo ponderado {score:+.1f})"
    if score > 1:
        return Voto("Notícias", "alta", detalhe)
    if score < -1:
        return Voto("Notícias", "baixa", detalhe)
    return Voto("Notícias", "neutro", detalhe)


def _voto_nci(nci: dict) -> Voto:
    d = nci.get("direcao")  # "LONG" / "SHORT" / None
    rotulo = nci.get("rotulo", "")
    if d == "LONG":
        return Voto("NCI", "alta", f"setup LONG ({rotulo})")
    if d == "SHORT":
        return Voto("NCI", "baixa", f"setup SHORT ({rotulo})")
    return Voto("NCI", "neutro", nci.get("nota", "sem setup claro"))


# ── Síntese de convergência ─────────────────────────────────────────────

def _sintetizar(votos: list) -> tuple[str, str, str]:
    dirs = [v.direcao for v in votos if v.direcao != "neutro"]
    altas = dirs.count("alta")
    baixas = dirs.count("baixa")
    neutros = sum(1 for v in votos if v.direcao == "neutro")

    if not dirs:
        return "baixa", "mista", "Todas as camadas neutras — sem direção clara hoje."

    if altas > 0 and baixas == 0:
        conv = "alta" if neutros == 0 else "média"
        return conv, "alta", "As camadas convergem para ALTA" + (
            "." if neutros == 0 else " (com alguma camada neutra).")
    if baixas > 0 and altas == 0:
        conv = "alta" if neutros == 0 else "média"
        return conv, "baixa", "As camadas convergem para BAIXA" + (
            "." if neutros == 0 else " (com alguma camada neutra).")

    # há alta E baixa → divergência
    discordante = "alta" if altas < baixas else "baixa"
    dominante = "baixa" if altas < baixas else "alta"
    return "baixa", "mista", (
        f"Sinais MISTOS — predominância {dominante}, mas há divergência. Cautela.")


# ── Construção do relatório ─────────────────────────────────────────────

def gerar_relatorio(commodity_id: str, nci_resultado: dict | None = None) -> MorningReport:
    """
    Gera o relatório matinal. `nci_resultado` é opcional (dict com 'direcao',
    'rotulo', 'nota') — se None, a secção NCI fica neutra.
    """
    ficha = load_commodity(commodity_id)

    # Regime (do motor de correlações)
    corr = analyze_correlations(commodity_id)
    reg = detectar_regime(corr, ficha)

    # Notícias materiais recentes
    noticias = ler_noticias(commodity_id, dias=7, min_relevancia=4)

    ## NCI — calcula o setup real (LTF H1, HTF Daily) se não vier de fora
    if nci_resultado is not None:
        nci = nci_resultado
    else:
        try:
            feed = DataFeed()
            ticker = ficha.ticker_dados or ficha.simbolo_spot
            ltf = feed.get_bars(ticker, days=30, interval="1h")
            htf = feed.get_bars(ticker, days=180, interval="1d")
            setup = avaliar_setup(ltf, htf)
            nci = {
                "direcao": setup["direcao"],
                "rotulo": setup["rotulo"],
                "nota": setup["nota"],
            }
        except Exception as e:
            logger.error("Erro a avaliar NCI: %s", e)
            nci = {"direcao": None, "nota": "erro ao avaliar"}

    # Votos
    votos = [_voto_regime(reg), _voto_noticias(noticias), _voto_nci(nci)]
    conv, direcao, leitura = _sintetizar(votos)

    return MorningReport(
        commodity=commodity_id,
        nome=ficha.nome,
        gerado_em=datetime.now().strftime("%Y-%m-%d %H:%M"),
        regime=reg,
        noticias=noticias,
        nci=nci,
        votos=votos,
        conviccao=conv,
        direcao_sintese=direcao,
        leitura=leitura,
    )

# ── Persistência de relatórios ──────────────────────────────────────────

import json as _json
from engine.database import get_conn, init_db


def _report_to_dict(r: MorningReport) -> dict:
    return {
        "commodity": r.commodity, "nome": r.nome, "gerado_em": r.gerado_em,
        "regime": r.regime, "noticias": r.noticias, "nci": r.nci,
        "votos": [{"camada": v.camada, "direcao": v.direcao, "detalhe": v.detalhe}
                  for v in r.votos],
        "conviccao": r.conviccao, "direcao_sintese": r.direcao_sintese,
        "leitura": r.leitura,
    }


def guardar_relatorio(r: MorningReport) -> None:
    """Guarda o relatório (um por commodity por dia; atualiza se já existir)."""
    init_db()
    data = r.gerado_em.split(" ")[0]  # só a data, sem hora
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO relatorios (commodity, data, conviccao, direcao, leitura, payload)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(commodity, data) DO UPDATE SET
                conviccao=excluded.conviccao, direcao=excluded.direcao,
                leitura=excluded.leitura, payload=excluded.payload
        """, (r.commodity, data, r.conviccao, r.direcao_sintese,
              r.leitura, _json.dumps(_report_to_dict(r), ensure_ascii=False)))


def ler_relatorio(commodity_id: str, data: str | None = None) -> dict | None:
    """Lê o relatório guardado de um dia (ou o mais recente se data=None)."""
    init_db()
    with get_conn() as conn:
        if data:
            row = conn.execute(
                "SELECT payload FROM relatorios WHERE commodity=? AND data=?",
                (commodity_id, data)).fetchone()
        else:
            row = conn.execute(
                "SELECT payload FROM relatorios WHERE commodity=? "
                "ORDER BY data DESC LIMIT 1", (commodity_id,)).fetchone()
    return _json.loads(row["payload"]) if row else None

if __name__ == "__main__":
    # Teste: python -m engine.morning_report
    r = gerar_relatorio("ouro")
    print(f"\n{'='*60}")
    print(f"RELATÓRIO MATINAL — {r.nome.upper()}  ({r.gerado_em})")
    print(f"{'='*60}\n")
    print(f"REGIME: {r.regime.get('regime')} ({r.regime.get('confianca',0):.0%})")
    print(f"  {r.regime.get('justificacao','')}\n")
    print(f"NOTÍCIAS: {len(r.noticias)} materiais\n")
    print("VOTOS DAS CAMADAS:")
    for v in r.votos:
        print(f"  · {v.camada:10} → {v.direcao:7} | {v.detalhe}")
    print(f"\nSÍNTESE: {r.direcao_sintese.upper()} · convicção {r.conviccao.upper()}")
    print(f"  → {r.leitura}\n")