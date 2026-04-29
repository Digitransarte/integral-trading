"""
Integral Trading — Universos de Tickers
=========================================
Fonte única de verdade para todos os universos.
Sem duplicados. Sem tickers delisted.
Cada ticker pertence a UM só sector activo.
"""

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

REFERENCE = {
    "sp500_sample": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
        "ORCL", "NFLX", "ADBE", "CRM", "UBER", "ABNB", "SHOP", "SNOW",
    ],
    "etf": [
        "SPY", "QQQ", "IWM", "XLK", "XLV", "XLE", "XLF", "XBI", "SMH",
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

MAIN_UNIVERSE = sorted(set(
    t for sector in SECTORS.values() for t in sector
))

FULL_UNIVERSE = sorted(set(
    MAIN_UNIVERSE +
    [t for sector in REFERENCE.values() for t in sector]
))

DASHBOARD_UNIVERSES = {
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
}


def get_universe(name: str) -> list:
    return DASHBOARD_UNIVERSES.get(name, [])


def list_universes() -> list:
    return [
        {"name": k, "count": len(v)}
        for k, v in DASHBOARD_UNIVERSES.items()
        if k != "Personalizado"
    ]


if __name__ == "__main__":
    print("Universo Principal: " + str(len(MAIN_UNIVERSE)) + " tickers")
    print("Universo Completo:  " + str(len(FULL_UNIVERSE)) + " tickers")

    all_tickers = [t for s in SECTORS.values() for t in s]
    duplicates  = [t for t in set(all_tickers) if all_tickers.count(t) > 1]
    if duplicates:
        print("AVISO — Duplicados: " + str(duplicates))
    else:
        print("OK — Sem duplicados")

    print()
    for name, tickers in SECTORS.items():
        print("  " + name + ": " + str(len(tickers)) + " tickers")
