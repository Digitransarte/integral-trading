"""
Integral Trading — Backtest CLI
Uso:
    python run_backtest.py
    python run_backtest.py --tickers AAPL MSFT NVDA --days 365 --verbose
    python run_backtest.py --universe small_cap --days 180
"""
import argparse, sys
from datetime import datetime, timedelta
sys.path.insert(0, ".")

from engine.data_feed import DataFeed
from engine.backtester import Backtester, BacktestConfig
from engine.strategies.ep_strategy import EpisodicPivotStrategy
from engine.database import save_backtest
from config import POLYGON_API_KEY

STRATEGIES = {"ep": EpisodicPivotStrategy}
UNIVERSES  = {
    "sp500_sample":  ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AMD",
                      "ORCL","NFLX","ADBE","CRM","UBER","ABNB","SHOP","SNOW"],
    "small_cap":     ["RXRX","HIMS","ACHR","JOBY","RKLB","ASTS","LUNR","SOUN","BBAI","IONQ"],
    "etf":           ["SPY","QQQ","IWM","XLK","XLV","XLE","XLF","XBI","SMH"],
}


def run(strategy_name, tickers, days, capital, verbose=False, save=True):
    print(f"\n{'='*55}")
    print(f"  INTEGRAL TRADING — Backtest")
    print(f"{'='*55}")
    print(f"  Estratégia : {strategy_name.upper()}")
    print(f"  Tickers    : {len(tickers)} ({', '.join(tickers[:4])}{'...' if len(tickers)>4 else ''})")
    print(f"  Período    : últimos {days} dias")
    print(f"  Capital    : ${capital:,.0f}")
    print(f"{'='*55}\n")

    feed     = DataFeed(polygon_key=POLYGON_API_KEY)
    strategy = STRATEGIES.get(strategy_name.lower(), EpisodicPivotStrategy)()
    config   = BacktestConfig(
        tickers=tickers,
        start_date=datetime.today() - timedelta(days=days),
        end_date=datetime.today(),
        initial_capital=capital,
    )
    summary = Backtester(feed, strategy).run(config)
    s = summary.to_dict()

    print(f"  Total trades   : {s['total_trades']}")
    print(f"  Win rate       : {s['win_rate']}%")
    print(f"  Profit factor  : {s['profit_factor']}")
    print(f"  Retorno total  : {s['total_return_pct']}%")
    print(f"  Max drawdown   : {s['max_drawdown_pct']}%")
    print(f"  Avg win        : {s['avg_win_pct']}%")
    print(f"  Avg loss       : {s['avg_loss_pct']}%")
    print(f"  Avg hold (d)   : {s['avg_hold_days']}")

    if summary.equity_curve:
        ini, fin = summary.equity_curve[0], summary.equity_curve[-1]
        print(f"\n  Capital final  : ${fin:,.2f}  ({fin-ini:+,.2f})")

    if summary.errors:
        print(f"\n  ⚠ Erros ({len(summary.errors)}):")
        for e in summary.errors:
            print(f"    - {e}")

    if save and summary.total_trades > 0:
        run_id = save_backtest(summary)
        print(f"\n  💾 Guardado no histórico (ID #{run_id})")

    if verbose and summary.trades:
        print(f"\n  {'Ticker':<8} {'Entrada':<12} {'Saída':<12} {'P&L':>8} {'Dias':>5} {'Razão'}")
        print(f"  {'─'*7} {'─'*11} {'─'*11} {'─'*8} {'─'*5} {'─'*10}")
        for t in sorted(summary.trades, key=lambda x: x.pnl_pct, reverse=True):
            en = t.entry_date.strftime("%Y-%m-%d") if t.entry_date else "—"
            ex = t.exit_date.strftime("%Y-%m-%d")  if t.exit_date  else "open"
            print(f"  {t.ticker:<8} {en:<12} {ex:<12} {t.pnl_pct:>+7.1f}% {t.days_held:>5} {t.exit_reason}")

    print(f"\n{'='*55}\n")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--strategy",  default="ep")
    p.add_argument("--tickers",   nargs="+")
    p.add_argument("--universe",  default=None)
    p.add_argument("--days",      type=int,   default=365)
    p.add_argument("--capital",   type=float, default=10_000.0)
    p.add_argument("--verbose",   "-v", action="store_true")
    p.add_argument("--no-save",   action="store_true", help="Não guardar na DB")
    args = p.parse_args()

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.universe:
        tickers = UNIVERSES.get(args.universe, [])
        if not tickers:
            print(f"Universo desconhecido. Disponíveis: {list(UNIVERSES.keys())}")
            sys.exit(1)
    else:
        tickers = UNIVERSES["sp500_sample"]
        print("A usar universo padrão: sp500_sample")

    run(args.strategy, tickers, args.days, args.capital,
        verbose=args.verbose, save=not args.no_save)
