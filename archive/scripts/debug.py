"""
Debug — verifica dados e sinais EP
Corre: python debug.py
"""
import sys
sys.path.insert(0, ".")

from engine.data_feed import DataFeed
from engine.strategies.ep_strategy import EpisodicPivotStrategy
from config import POLYGON_API_KEY

feed     = DataFeed(polygon_key=POLYGON_API_KEY)
strategy = EpisodicPivotStrategy()

# ── 1. Verificar dados ────────────────────────────────────────────────────────
print("\n[1] A verificar dados...")
for ticker in ["AAPL", "NVDA", "HIMS"]:
    df = feed.get_bars(ticker, days=30)
    if df.empty:
        print(f"  {ticker}: SEM DADOS")
    else:
        last = df.iloc[-1]
        print(f"  {ticker}: {len(df)} barras | último close: ${last['close']:.2f} | vol: {int(last['volume']):,}")

# ── 2. Verificar critérios EP nos últimos 365 dias ────────────────────────────
print("\n[2] A procurar dias com gap >= 5% no último ano...")

tickers_ep = ["HIMS", "RXRX", "RKLB", "ASTS", "IONQ", "SOUN", "BBAI", "ACHR"]

for ticker in tickers_ep:
    df = feed.get_bars(ticker, days=365)
    if df.empty or len(df) < 22:
        print(f"  {ticker}: sem dados suficientes")
        continue

    sinais = 0
    for i in range(21, len(df)):
        dfsf = df.iloc[:i+1]
        last = dfsf.iloc[-1]
        prev = dfsf.iloc[-2]
        gap  = (last["open"] - prev["close"]) / prev["close"] * 100
        avg_vol = dfsf["volume"].iloc[-21:-1].mean()
        vol_ratio = last["volume"] / avg_vol if avg_vol > 0 else 0

        if gap >= 5.0 and vol_ratio >= 2.5:
            sinais += 1
            score = strategy._calculate_score(dfsf, gap, vol_ratio)
            if sinais <= 3:  # mostra só os 3 primeiros
                print(f"  {ticker} [{dfsf.index[-1].strftime('%Y-%m-%d')}] "
                      f"gap={gap:.1f}% vol={vol_ratio:.1f}x score={score:.0f}")

    if sinais == 0:
        print(f"  {ticker}: 0 sinais EP no ano")
    elif sinais > 3:
        print(f"  {ticker}: {sinais} sinais EP no total")

print("\n[3] Resumo de scores mínimos actuais:")
print(f"  Min gap:        {strategy.MIN_GAP_PCT}%")
print(f"  Min vol ratio:  {strategy.MIN_VOLUME_RATIO}x")
print(f"  Min score:      {strategy.min_score}")
print(f"  Min price:      ${strategy.MIN_PRICE}")
