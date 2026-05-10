"""
Integral Trading — Scanner CLI
================================
Detecta sinais EP nos mercados actuais.

Uso:
    python run_scanner.py
    python run_scanner.py --universe small_growth
    python run_scanner.py --universe main --top 20
    python run_scanner.py --tickers HIMS IONQ RKLB ASTS
"""
import argparse, sys
from datetime import datetime
sys.path.insert(0, ".")

from engine.data_feed import DataFeed
from engine.scanner import Scanner
from engine.strategies.ep_strategy import EpisodicPivotStrategy
from universes import SECTORS, MAIN_UNIVERSE, DASHBOARD_UNIVERSES
from config import POLYGON_API_KEY


UNIVERSE_MAP = {
    "small_growth":       SECTORS["small_growth"],
    "space_defense":      SECTORS["space_defense"],
    "ai_tech":            SECTORS["ai_tech"],
    "mid_cap_momentum":   SECTORS["mid_cap_momentum"],
    "healthcare_devices": SECTORS["healthcare_devices"],
    "main":               MAIN_UNIVERSE,
}


def print_candidates(result, top_n):
    candidates = result.top(top_n)

    print("\n" + "="*75)
    print("  INTEGRAL TRADING — Scanner EP")
    print("="*75)
    print("  Data     : " + result.scan_date.strftime("%Y-%m-%d %H:%M UTC"))
    print("  Scanned  : " + str(result.tickers_scanned) + " tickers")
    print("  Tempo    : " + str(round(result.duration_seconds, 1)) + "s")
    print("  Candidatos: " + str(result.total_candidates))
    print("="*75)

    if not candidates:
        print("\n  Nenhum candidato EP encontrado hoje.")
        if result.errors:
            print("\n  Erros (" + str(len(result.errors)) + "):")
            for e in result.errors[:5]:
                print("  - " + e)
        print()
        return

    # Tabela de candidatos
    print("\n  {:<6} {:<8} {:>7} {:>7} {:>6} {:>7} {:>8} {:>8} {:<8}".format(
        "Score", "Ticker", "Preco", "Gap%", "Vol x",
        "Stop", "T1", "T2", "Janela"))
    print("  " + "-"*6 + " " + "-"*8 + " " + "-"*7 + " " + "-"*7 +
          " " + "-"*6 + " " + "-"*7 + " " + "-"*8 + " " + "-"*8 + " " + "-"*8)

    for c in candidates:
        window_icon = {"PRIME": "🟢", "OPEN": "🟡", "LATE": "🔴"}.get(c.entry_window, " ")
        print("  {:>5.0f}  {:<8} {:>7.2f} {:>+6.1f}% {:>5.1f}x {:>7.2f} {:>8.2f} {:>8.2f} {} {}".format(
            c.score, c.ticker, c.current_price, c.gap_pct,
            c.vol_ratio, c.stop_loss, c.target_1, c.target_2,
            window_icon, c.entry_window
        ))

    # Detalhe dos top candidatos
    print("\n" + "-"*75)
    print("  DETALHE — TOP " + str(min(3, len(candidates))))
    print("-"*75)
    for c in candidates[:3]:
        print("\n  " + c.ticker + " — Score: " + str(round(c.score, 0)))
        print("  Preco actual : $" + str(round(c.current_price, 2)))
        print("  Gap          : " + str(round(c.gap_pct, 1)) + "% | Vol: " +
              str(round(c.vol_ratio, 1)) + "x média")
        print("  Entrada      : $" + str(round(c.current_price, 2)) +
              "  Stop: $" + str(round(c.stop_loss, 2)) +
              "  T1: $" + str(round(c.target_1, 2)) +
              "  T2: $" + str(round(c.target_2, 2)))
        print("  Risco/Reward : -" + str(round(c.risk_pct, 1)) +
              "% / +" + str(round(c.reward_pct, 1)) + "%")
        print("  Janela       : " + c.entry_window +
              " (" + str(c.days_since_gap) + " dias desde o gap)")
        if c.signal.notes:
            print("  Notas        : " + c.signal.notes)

    if result.errors:
        print("\n  Avisos (" + str(len(result.errors)) + " tickers com problemas):")
        for e in result.errors[:3]:
            print("  - " + e)

    print("\n" + "="*75 + "\n")


def main():
    p = argparse.ArgumentParser(description="Scanner EP em tempo real")
    p.add_argument("--universe", default="main",
                   help="Universo: " + ", ".join(UNIVERSE_MAP.keys()))
    p.add_argument("--tickers",  nargs="+",
                   help="Tickers específicos em vez de universo")
    p.add_argument("--top",      type=int, default=10,
                   help="Número de candidatos a mostrar")
    p.add_argument("--lookback", type=int, default=60,
                   help="Dias de histórico para calcular médias")
    args = p.parse_args()

    # Resolver tickers
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = UNIVERSE_MAP.get(args.universe, MAIN_UNIVERSE)
        if not tickers:
            print("Universo desconhecido. Disponíveis: " + ", ".join(UNIVERSE_MAP.keys()))
            sys.exit(1)

    print("\nA iniciar scanner EP...")
    print("Universo: " + str(len(tickers)) + " tickers")

    feed     = DataFeed(polygon_key=POLYGON_API_KEY)
    strategy = EpisodicPivotStrategy()
    scanner  = Scanner(feed, strategy)
    result   = scanner.run(tickers, lookback_days=args.lookback)

    print_candidates(result, args.top)


if __name__ == "__main__":
    main()
