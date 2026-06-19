"""
Integral Trading — Knowledge Loader
=====================================
Carrega as fichas de conhecimento das matérias-primas
(knowledge/commodities/<id>.json) e expõe-nas de forma organizada.

Uso:
    from engine.knowledge import load_commodity, list_commodities

    ficha = load_commodity("ouro")
    ficha.drivers          # lista de drivers
    ficha.tickers_relacao  # tickers dos ativos relacionados (p/ correlações)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# knowledge/commodities/ fica ao lado de engine/
_BASE = Path(__file__).parent.parent / "knowledge" / "commodities"


@dataclass
class Commodity:
    """Ficha de conhecimento de uma matéria-prima."""
    id: str
    nome: str
    simbolo_spot: str
    ticker_dados: str
    natureza: str
    resumo: str
    drivers: list = field(default_factory=list)
    relacoes: list = field(default_factory=list)
    regimes: list = field(default_factory=list)
    sazonalidade: dict = field(default_factory=dict)
    fontes: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def tickers_relacao(self) -> list[str]:
        """Tickers dos ativos relacionados — para o motor de correlações."""
        return [r["ticker"] for r in self.relacoes if r.get("ticker")]

    def driver(self, driver_id: str) -> dict | None:
        """Devolve um driver pelo id, ou None."""
        return next((d for d in self.drivers if d.get("id") == driver_id), None)


def load_commodity(commodity_id: str) -> Commodity:
    """Carrega uma ficha pelo id (ex: 'ouro'). Lança FileNotFoundError se não existir."""
    path = _BASE / f"{commodity_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Ficha não encontrada: {path}")

    # utf-8-sig tolera BOM do Windows
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    return Commodity(
        id=meta.get("id", commodity_id),
        nome=meta.get("nome", commodity_id),
        simbolo_spot=meta.get("simbolo_spot", ""),
        ticker_dados=meta.get("tickers_dados", {}).get("futuros", ""),
        natureza=meta.get("natureza", ""),
        resumo=data.get("resumo", ""),
        drivers=data.get("drivers", []),
        relacoes=data.get("relacoes_ativos", []),
        regimes=data.get("regimes", []),
        sazonalidade=data.get("sazonalidade", {}),
        fontes=data.get("fontes", []),
        raw=data,
    )


def list_commodities() -> list[str]:
    """Lista os ids de todas as fichas disponíveis."""
    if not _BASE.exists():
        return []
    return sorted(p.stem for p in _BASE.glob("*.json"))


if __name__ == "__main__":
    # Teste rápido: python -m engine.knowledge
    print("Fichas disponíveis:", list_commodities())
    for cid in list_commodities():
        c = load_commodity(cid)
        print(f"  {c.nome:10} | {len(c.drivers)} drivers | "
              f"{len(c.relacoes)} relações | tickers: {c.tickers_relacao}")