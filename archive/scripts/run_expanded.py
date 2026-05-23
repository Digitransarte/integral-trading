"""
Integral Trading — Backtest Expandido
=======================================
Corre: python run_expanded.py
       python run_expanded.py --sector small_growth --days 365 --verbose
       python run_expanded.py --all --days 365
       python run_expanded.py --universe main --days 730
"""
import argparse, sys
from datetime import datetime, timedelta
sys.path.insert(0, ".")

from engine.data_feed import DataFeed
from engine.backtester import Backtester, BacktestConfig
from engine.strategies.ep_strategy import EpisodicPivotStrategy
from engine.database import save_backtest
from universes import SECTORS, MAIN_UNIVERSE, FULL_UNIVERSE
from config import POLYGON_API_KEY


def run_sector(sector_name, tickers, days, capital, save):
    feed     = DataFeed(polygon_key=POLYGON_API_KEY)
    strategy = EpisodicPivotStrategy()
    config   = BacktestConfig(
        tickers=tickers,
        start_date=datetime.today() - timedelta(days=days),
        end_date=datetime.today(),
        initial_capital=capital,
    )
    summary = Backtester(feed, strategy).run(config)
    if save and summary.total_trades > 0:
        save_backtest(summary)
    return {
        "sector":        sector_name,
        "tickers":       len(tickers),
        "trades":        summary.total_trades,
        "win_rate":      summary.win_rate,
        "profit_factor": summary.profit_factor,
        "total_return":  summary.total_return_pct,
        "max_drawdown":  summary.max_drawdown_pct,
        "avg_hold":      summary.avg_hold_days,
        "errors":        len(summary.errors),
        "error_list":    summary.errors,
        "summary":       summary,
    }


def print_table(results):
    print("\n" + "="*72)
    print("  RESUMO POR SECTOR")
    print("="*72)
    print("  {:<22} {:>7} {:>6} {:>6} {:>5} {:>8} {:>7}".format(
        "Sector", "Tickers", "Trades", "Win%", "PF", "Retorno", "MaxDD"))
    print("  " + "-"*22 + " " + "-"*7 + " " + "-"*6 + " " +
          "-"*6 + " " + "-"*5 + " " + "-"*8 + " " + "-"*7)

    for r in sorted(results, key=lambda x: x["total_return"], reverse=True):
        print("  {:<22} {:>7} {:>6} {:>5.1f}% {:>5.2f} {:>+7.1f}% {:>6.1f}%".format(
            r["sector"], r["tickers"], r["trades"],
            r["win_rate"] * 100, r["profit_factor"],
            r["total_return"], r["max_drawdown"]))

    print("  " + "-"*22 + " " + "-"*7 + " " + "-"*6)
    print("  {:<22} {:>7} {:>6}".format(
        "TOTAL",
        sum(r["tickers"] for r in results),
        sum(r["trades"] for r in results)))
    print("="*72 + "\n")


def print_trades(results):
    all_trades = []
    for r in results:
        for t in r["summary"].trades:
            all_trades.append({
                "sector": r["sector"],
                "ticker": t.ticker,
                "entry":  t.entry_date.strftime("%Y-%m-%d") if t.entry_date else "-",
                "exit":   t.exit_date.strftime("%Y-%m-%d")  if t.exit_date  else "open",
                "pnl":    t.pnl_pct,
                "days":   t.days_held,
            })

    if not all_trades:
        print("  Nenhum trade gerado.")
        return

    all_trades.sort(key=lambda x: x["pnl"], reverse=True)
    print("\n  TODOS OS TRADES (" + str(len(all_trades)) + ")")
    print("  {:<18} {:<8} {:<12} {:<12} {:>8} {:>5}".format(
        "Sector", "Ticker", "Entrada", "Saida", "P&L", "Dias"))
    print("  " + "-"*18 + " " + "-"*7 + " " + "-"*11 + " " +
          "-"*11 + " " + "-"*8 + " " + "-"*5)
    for t in all_trades:
        print("  {:<18} {:<8} {:<12} {:<12} {:>+7.1f}% {:>5}".format(
            t["sector"], t["ticker"], t["entry"], t["exit"],
            t["pnl"], t["days"]))

    wins = [t for t in all_trades if t["pnl"] > 0]
    print("\n  Wins: {} | Losses: {} | Win rate: {:.1f}%".format(
        len(wins), len(all_trades) - len(wins),
        len(wins) / len(all_trades) * 100))


def print_errors(results):
    errors = [(r["sector"], e) for r in results for e in r["error_list"]]
    if not errors:
        print("  Sem erros de dados.")
        return
    print("\n  ERROS (" + str(len(errors)) + ") — tickers a verificar:")
    for sector, e in errors:
        print("  [" + sector + "] " + e)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sector",   default=None)
    p.add_argument("--all",      action="store_true")
    p.add_argument("--universe", default=None, choices=["main", "full"])
    p.add_argument("--days",     type=int,   default=365)
    p.add_argument("--capital",  type=float, default=10_000.0)
    p.add_argument("--verbose",  "-v", action="store_true")
    p.add_argument("--no-save",  action="store_true")
    args = p.parse_args()

    save = not args.no_save

    print("\n" + "="*72)
    print("  INTEGRAL TRADING — Backtest Expandido")
    print("="*72)
    print("  Periodo  : ultimos " + str(args.days) + " dias")
    print("  Capital  : $" + "{:,.0f}".format(args.capital))
    print("="*72 + "\n")

    results = []

    if args.sector:
        tickers = SECTORS.get(args.sector)
        if not tickers:
            print("Sector desconhecido. Disponíveis: " + ", ".join(SECTORS.keys()))
            sys.exit(1)
        print("  [" + args.sector + "] " + str(len(tickers)) + " tickers...",
              end=" ", flush=True)
        r = run_sector(args.sector, tickers, args.days, args.capital, save)
        print(str(r["trades"]) + " trades | " +
              "{:.0f}".format(r["win_rate"] * 100) + "% win | " +
              "{:+.1f}".format(r["total_return"]) + "%")
        results.append(r)

    elif args.universe == "main":
        print("  [main] " + str(len(MAIN_UNIVERSE)) + " tickers...",
              end=" ", flush=True)
        r = run_sector("main", MAIN_UNIVERSE, args.days, args.capital, save)
        print(str(r["trades"]) + " trades | " +
              "{:.0f}".format(r["win_rate"] * 100) + "% win | " +
              "{:+.1f}".format(r["total_return"]) + "%")
        results.append(r)

    elif args.universe == "full":
        print("  [full] " + str(len(FULL_UNIVERSE)) + " tickers...",
              end=" ", flush=True)
        r = run_sector("full", FULL_UNIVERSE, args.days, args.capital, save)
        print(str(r["trades"]) + " trades | " +
              "{:.0f}".format(r["win_rate"] * 100) + "% win | " +
              "{:+.1f}".format(r["total_return"]) + "%")
        results.append(r)

    else:
        sectors_to_run = SECTORS if args.all else {
            k: SECTORS[k] for k in [
                "small_growth", "space_defense", "ai_tech",
                "mid_cap_momentum", "healthcare_devices",
            ]
        }
        for sector_name, tickers in sectors_to_run.items():
            print("  [" + sector_name + "] " + str(len(tickers)) + " tickers...",
                  end=" ", flush=True)
            r = run_sector(sector_name, tickers, args.days, args.capital, save)
            print(str(r["trades"]) + " trades | " +
                  "{:.0f}".format(r["win_rate"] * 100) + "% win | " +
                  "{:+.1f}".format(r["total_return"]) + "%")
            results.append(r)

    if results:
        print_table(results)
        print_errors(results)
        if args.verbose:
            print_trades(results)

    print("  Guardado na DB: " + ("sim" if save else "nao") + "\n")


if __name__ == "__main__":
    main()
