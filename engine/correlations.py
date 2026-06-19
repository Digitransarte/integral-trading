"""
Integral Trading — Motor de Correlações
=========================================
Calcula correlações móveis entre uma matéria-prima e os seus ativos
relacionados (definidos na ficha de conhecimento), e compara o sinal
observado com o sentido esperado pela ficha.

O "descolado" (observado contradiz o esperado) é o sinal mais valioso:
indica possível mudança de regime.

Uso:
    from engine.correlations import analyze_correlations
    resultado = analyze_correlations("ouro")
    for r in resultado.pares:
        print(r["ativo"], r["coef"], r["estado"])
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from engine.data_feed import DataFeed
from engine.knowledge import load_commodity, Commodity

logger = logging.getLogger(__name__)

# Limiares de classificação da força (valor absoluto do coeficiente)
_FORTE = 0.6
_MEDIA = 0.3


def _classificar_forca(coef: float) -> str:
    a = abs(coef)
    if a >= _FORTE:
        return "forte"
    if a >= _MEDIA:
        return "média"
    return "fraca"


def _sinal(coef: float) -> str:
    if coef > 0.05:
        return "direto"
    if coef < -0.05:
        return "inverso"
    return "nulo"


def _comparar_esperado(observado: str, esperado: str) -> str:
    """Compara o sinal observado com o que a ficha esperava."""
    if not esperado:
        return "sem_referência"
    # Normaliza valores esperados da ficha que não são +/-
    if esperado in ("quase_nulo", "variavel", "inverso_em_crise"):
        return "contextual"
    if observado == "nulo":
        return "neutro"
    return "alinhado" if observado == esperado else "DESCOLADO"


@dataclass
class CorrelationResult:
    commodity: str
    janela: int
    pares: list = field(default_factory=list)
    avisos: list = field(default_factory=list)


def analyze_correlations(commodity_id: str, janela: int = 60,
                         feed: DataFeed | None = None) -> CorrelationResult:
    """
    Calcula a correlação dos retornos diários do ativo principal com cada
    ativo relacionado, na janela dada, e compara com a ficha.
    """
    ficha: Commodity = load_commodity(commodity_id)
    feed = feed or DataFeed()

    # Série do ativo principal (usa o ticker de dados da ficha)
    principal_ticker = ficha.ticker_dados
    # margem de dias para garantir 'janela' retornos válidos
    dias = janela + 40

    base = feed.get_bars(principal_ticker, days=dias, interval="1d")
    if base is None or base.empty:
        return CorrelationResult(commodity_id, janela, [],
                                 [f"Sem dados para o ativo principal {principal_ticker}"])

    base_ret = base["close"].pct_change().dropna()

    resultado = CorrelationResult(commodity_id, janela)

    for rel in ficha.relacoes:
        ticker = rel.get("ticker")
        if not ticker:
            continue
        df = feed.get_bars(ticker, days=dias, interval="1d")
        if df is None or df.empty:
            resultado.avisos.append(f"Sem dados para {ticker} ({rel.get('ativo')})")
            continue

        rel_ret = df["close"].pct_change().dropna()

        # Alinhar pelas datas comuns e usar a janela
        juntos = pd.concat([base_ret, rel_ret], axis=1, join="inner").dropna()
        juntos = juntos.tail(janela)
        if len(juntos) < janela // 2:
            resultado.avisos.append(f"Poucos dados comuns para {ticker} ({len(juntos)})")
            continue

        coef = float(juntos.iloc[:, 0].corr(juntos.iloc[:, 1]))
        observado = _sinal(coef)
        esperado = rel.get("sentido_esperado", "")
        estado = _comparar_esperado(observado, esperado)

        par = {
            "ativo": rel.get("ativo"),
            "ticker": ticker,
            "coef": round(coef, 3),
            "forca": _classificar_forca(coef),
            "sinal_observado": observado,
            "sentido_esperado": esperado,
            "estado": estado,
            "n_dias": len(juntos),
        }
        resultado.pares.append(par)

        if estado == "DESCOLADO":
            resultado.avisos.append(
                f"⚠ {rel.get('ativo')}: esperado {esperado}, observado {observado} "
                f"(coef {coef:+.2f}) — possível mudança de regime"
            )

    return resultado


if __name__ == "__main__":
    # Teste: python -m engine.correlations
    res = analyze_correlations("ouro")
    print(f"\nCORRELAÇÕES — {res.commodity.upper()} (janela {res.janela}d)\n")
    print(f"  {'Ativo':<28} {'Coef':>7} {'Força':>8} {'Observado':>10} {'Esperado':>14} {'Estado':>12}")
    print("  " + "-" * 88)
    for p in res.pares:
        print(f"  {p['ativo']:<28} {p['coef']:>7.2f} {p['forca']:>8} "
              f"{p['sinal_observado']:>10} {p['sentido_esperado']:>14} {p['estado']:>12}")
    if res.avisos:
        print("\n  AVISOS:")
        for a in res.avisos:
            print("   ", a)
    print()