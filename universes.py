"""
Integral Trading — Universos de Tickers
=========================================
Fonte única de verdade para todos os universos.
Sem duplicados. Sem tickers delisted.
Cada ticker pertence a UM só sector activo.

Tickers por classe de activo:
  SECTORS       — acções por sector (EP scanner)
  COMMODITIES   — matérias-primas (NCI analyzer)
  FOREX         — pares forex (NCI analyzer)
  REFERENCE     — índices e ETFs de referência
  WATCHLIST_ONLY — watchlists manuais
"""

# ─────────────────────────────────────────────────────────────────────────────
# ACÇÕES
# ─────────────────────────────────────────────────────────────────────────────

SECTORS = {
    "small_growth": [
        "HIMS", "RXRX", "ACHR", "JOBY", "RKLB", "ASTS", "LUNR",
        "SOUN", "BBAI", "IONQ", "CELH", "DUOL", "MNDY", "GLBE",
        "INSP", "IRTC", "NVCR", "AXSM", "PRAX", "TMDX",
    ],
    "space_defense": [
        "MNTS", "RDW", "KTOS", "RCAT", "AVAV", "PLTR", "SPCE",
    ],
    "ai_tech": [
        "QBTS", "RGTI", "QUBT", "ARQQ",
        "IREN", "CORZ", "BTDR", "CIFR", "WULF",
        "SMCI", "NVTS", "ALAB", "MRVL", "ARM",
    ],
    "mid_cap_momentum": [
        "AXON", "CAVA", "BROS", "ELF", "APP",
        "IBKR", "CASY", "FTDR",
    ],
    "healthcare_devices": [
        "OFIX", "ATRC", "MMSI", "LMAT", "NVST",
    ],
    "ep_opportunity": [
        # Tier 1 — SaaS/Cloud com earnings surprises consistentes
        "PSTG", "CRWD", "MDB", "DDOG", "DOCU",
        # Tier 2 — Cybersecurity com padrão EP validado
        "FTNT", "OKTA", "ZS",
        # Tier 3 — Edge/devices com earnings consistency
        "NET", "ALGN", "NOW",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# COMMODITIES
# Tickers yfinance para análise diária (spot/futuros)
# Para intraday, o data_feed mapeia automaticamente para futuros
# ─────────────────────────────────────────────────────────────────────────────

COMMODITIES = {
    # Metais preciosos — safe haven + inflação
    "metais_preciosos": {
        "XAUUSD=X": "Ouro (spot)",
        "XAGUSD=X": "Prata (spot)",
        "XPTUSD=X": "Platina (spot)",
        "XPDUSD=X": "Paládio (spot)",
    },
    # Energia — petróleo e gás
    "energia": {
        "CL=F":  "Petróleo WTI (futuros)",
        "BZ=F":  "Petróleo Brent (futuros)",
        "NG=F":  "Gás Natural (futuros)",
        "HO=F":  "Heating Oil (futuros)",
        "RB=F":  "Gasolina RBOB (futuros)",
    },
    # Agrícolas — correlação fertilizantes/energia
    "agricolas": {
        "ZW=F": "Trigo (futuros)",
        "ZC=F": "Milho (futuros)",
        "ZS=F": "Soja (futuros)",
        "KC=F": "Café (futuros)",
        "CT=F": "Algodão (futuros)",
        "SB=F": "Açúcar (futuros)",
    },
    # Metais industriais — leading indicator económico
    "metais_industriais": {
        "HG=F":  "Cobre (futuros) — Dr. Copper",
        "ALI=F": "Alumínio (futuros)",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# FOREX
# Todos os tickers forex funcionam nativamente no yfinance (diário + intraday)
# ─────────────────────────────────────────────────────────────────────────────

FOREX = {
    # Majors — alta liquidez, spread baixo
    "majors": {
        "EURUSD=X": "EUR/USD — base de tudo",
        "GBPUSD=X": "GBP/USD — sensível a geopolítica UK",
        "USDJPY=X": "USD/JPY — safe haven (JPY)",
        "USDCHF=X": "USD/CHF — safe haven (CHF)",
        "AUDUSD=X": "AUD/USD — proxy commodities/China",
        "USDCAD=X": "USD/CAD — proxy petróleo",
        "NZDUSD=X": "NZD/USD — proxy agrícolas/China",
    },
    # Crosses relevantes — risk appetite
    "crosses": {
        "EURJPY=X": "EUR/JPY — risk appetite indicator",
        "GBPJPY=X": "GBP/JPY — alta volatilidade",
        "AUDJPY=X": "AUD/JPY — melhor proxy risk-on/off",
        "CADJPY=X": "CAD/JPY — proxy petróleo vs safe haven",
    },
    # Exóticos seleccionados — correlações commodity
    "exoticos": {
        "USDNOK=X": "USD/NOK — proxy Brent",
        "USDZAR=X": "USD/ZAR — proxy ouro/platina",
        "USDBRL=X": "USD/BRL — proxy soja/commodities Brazil",
        "USDMXN=X": "USD/MXN — proxy petróleo México",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# REFERÊNCIA
# ─────────────────────────────────────────────────────────────────────────────

REFERENCE = {
    "sp500_sample": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
        "ORCL", "NFLX", "ADBE", "CRM", "UBER", "ABNB", "SHOP", "SNOW",
    ],
    "etf": [
        "SPY", "QQQ", "IWM", "XLK", "XLV", "XLE", "XLF", "XBI", "SMH",
    ],
    # Macro reference — usados pelo regime detector e macro analyzer
    "macro": [
        "SPY", "QQQ", "^VIX", "TLT",
        "DX-Y.NYB",   # DXY Index
        "GLD", "SLV", # ETF proxies para correlações
        "CL=F",        # Petróleo como leading indicator de inflação
        "HG=F",        # Cobre como leading indicator económico
    ],
}

WATCHLIST_ONLY = {
    "biotech_watchlist": [
        "ACAD", "ARWR", "BEAM", "CRSP", "EDIT", "NTLA",
        "VERA", "GILD", "REGN", "BMRN", "SRPT", "FOLD", "RARE",
        "KRYS", "PTGX", "ALKS", "INCY",
    ],
    "crypto_watchlist": [
        "COIN", "MSTR", "MARA", "RIOT", "CLSK", "HUT",
        "HOOD", "AFRM", "UPST", "LC", "SOFI",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Universos computados — acções
# ─────────────────────────────────────────────────────────────────────────────

MAIN_UNIVERSE = sorted(set(
    t for sector in SECTORS.values() for t in sector
))

FULL_UNIVERSE = sorted(set(
    MAIN_UNIVERSE +
    [t for sector in REFERENCE.values() for t in sector
     if not t.startswith("^") and "=" not in t]
))

# ─────────────────────────────────────────────────────────────────────────────
# Universos computados — commodities e forex (listas planas)
# ─────────────────────────────────────────────────────────────────────────────

COMMODITIES_UNIVERSE = sorted(set(
    ticker
    for group in COMMODITIES.values()
    for ticker in group.keys()
))

FOREX_UNIVERSE = sorted(set(
    ticker
    for group in FOREX.values()
    for ticker in group.keys()
))

FOREX_MAJORS = list(FOREX["majors"].keys())
FOREX_CROSSES = list(FOREX["crosses"].keys())

METAIS_UNIVERSE = list(COMMODITIES["metais_preciosos"].keys())
ENERGIA_UNIVERSE = list(COMMODITIES["energia"].keys())
AGRICOLAS_UNIVERSE = list(COMMODITIES["agricolas"].keys())

# ─────────────────────────────────────────────────────────────────────────────
# Dashboard — todos os universos visíveis na UI
# ─────────────────────────────────────────────────────────────────────────────

DASHBOARD_UNIVERSES = {
    # Acções
    "Personalizado":              [],
    "Small Cap Growth":           SECTORS["small_growth"],
    "Space & Defense":            SECTORS["space_defense"],
    "AI & Tech":                  SECTORS["ai_tech"],
    "Mid Cap Momentum":           SECTORS["mid_cap_momentum"],
    "Healthcare Devices":         SECTORS["healthcare_devices"],
    "EP Opportunity (11)":        SECTORS["ep_opportunity"],
    "S&P 500 Sample (16)":        REFERENCE["sp500_sample"],
    "ETFs (9)":                   REFERENCE["etf"],
    "Universo Principal":         MAIN_UNIVERSE,
    "Universo Completo":          FULL_UNIVERSE,
    "Biotech [watchlist]":        WATCHLIST_ONLY["biotech_watchlist"],
    "Crypto [watchlist]":         WATCHLIST_ONLY["crypto_watchlist"],
    # Commodities
    "Metais Preciosos":           METAIS_UNIVERSE,
    "Energia":                    ENERGIA_UNIVERSE,
    "Agrícolas":                  AGRICOLAS_UNIVERSE,
    "Commodities (todas)":        COMMODITIES_UNIVERSE,
    # Forex
    "Forex Majors":               FOREX_MAJORS,
    "Forex Crosses":              FOREX_CROSSES,
    "Forex (todos)":              FOREX_UNIVERSE,
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_universe(name: str) -> list:
    return DASHBOARD_UNIVERSES.get(name, [])


def list_universes() -> list:
    return [
        {"name": k, "count": len(v)}
        for k, v in DASHBOARD_UNIVERSES.items()
        if k != "Personalizado"
    ]


def get_asset_class(ticker: str) -> str:
    """Determina a classe de activo de um ticker."""
    if ticker in COMMODITIES_UNIVERSE:
        return "commodity"
    if ticker in FOREX_UNIVERSE:
        return "forex"
    if ticker.startswith("^"):
        return "index"
    return "stock"


def get_commodity_name(ticker: str) -> str:
    """Retorna o nome legível de uma commodity."""
    for group in COMMODITIES.values():
        if ticker in group:
            return group[ticker]
    return ticker


def get_forex_name(ticker: str) -> str:
    """Retorna o nome legível de um par forex."""
    for group in FOREX.values():
        if ticker in group:
            return group[ticker]
    return ticker


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Acções ===")
    print("Universo Principal: " + str(len(MAIN_UNIVERSE)) + " tickers")
    print("Universo Completo:  " + str(len(FULL_UNIVERSE)) + " tickers")

    all_tickers = [t for s in SECTORS.values() for t in s]
    duplicates  = [t for t in set(all_tickers) if all_tickers.count(t) > 1]
    if duplicates:
        print("AVISO — Duplicados: " + str(duplicates))
    else:
        print("OK — Sem duplicados em SECTORS")

    print()
    print("=== Commodities ===")
    print("Total: " + str(len(COMMODITIES_UNIVERSE)) + " tickers")
    for group, tickers in COMMODITIES.items():
        print("  " + group + ": " + str(len(tickers)))

    print()
    print("=== Forex ===")
    print("Total: " + str(len(FOREX_UNIVERSE)) + " tickers")
    for group, tickers in FOREX.items():
        print("  " + group + ": " + str(len(tickers)))

    print()
    for name, tickers in SECTORS.items():
        print("  " + name + ": " + str(len(tickers)) + " tickers")
