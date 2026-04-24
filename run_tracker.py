"""
Integral Trading — Tracker CLI
================================
Actualiza posições abertas e mostra o estado do portfolio.

Uso:
    python run_tracker.py              # actualizar todas as posições
    python run_tracker.py --status     # ver posições sem actualizar
    python run_tracker.py --open HIMS 31.50 29.00 36.00 41.00 EP
    python run_tracker.py --close 3    # fechar posição ID #3
"""
import argparse, sys
from datetime import datetime
sys.path.insert(0, ".")

from engine.data_feed import DataFeed
from engine.forward_tracker import ForwardTracker
from config import POLYGON_API_KEY


def print_open_positions(positions):
    if not positions:
        print("\n  Nenhuma posição aberta.")
        return

    print("\n  POSIÇÕES ABERTAS (" + str(len(positions)) + ")")
    print("  {:<4} {:<6} {:<10} {:>7} {:>7} {:>7} {:>7} {:>7} {:>8} {:>5} {:<8}".format(
        "ID", "Ticker", "Estrategia", "Entrada", "Actual", "Stop",
        "T1", "P&L%", "Stop Dst", "Dias", "Status"))
    print("  " + "-"*100)

    for p in positions:
        stop_dist = p.distance_to_stop
        pnl_str   = "{:+.1f}%".format(p.pnl_pct)
        stop_str  = "{:.1f}%".format(stop_dist)

        # Indicador visual
        if p.pnl_pct >= 10:
            icon = "🟢"
        elif p.pnl_pct >= 0:
            icon = "🟡"
        else:
            icon = "🔴"

        print("  {:<4} {} {:<6} {:<10} {:>7.2f} {:>7.2f} {:>7.2f} {:>7.2f} {:>7} {:>8} {:>5}".format(
            p.id, icon, p.ticker, p.strategy_name[:10],
            p.entry_price, p.current_price, p.stop_price, p.target_1,
            pnl_str, stop_str, p.days_held,
        ))


def print_closed_positions(positions, limit=10):
    if not positions:
        return
    recent = positions[:limit]
    print("\n  ÚLTIMAS " + str(len(recent)) + " POSIÇÕES FECHADAS")
    print("  {:<4} {:<6} {:>7} {:>7} {:>8} {:>5} {:<12}".format(
        "ID", "Ticker", "Entrada", "Saida", "P&L%", "Dias", "Razao"))
    print("  " + "-"*55)
    for p in recent:
        icon = "✅" if p.pnl_pct > 0 else "❌"
        print("  {:<4} {} {:<6} {:>7.2f} {:>7.2f} {:>+7.1f}% {:>5} {:<12}".format(
            p.id, icon, p.ticker,
            p.entry_price, p.exit_price or 0,
            p.pnl_pct, p.days_held, p.exit_reason,
        ))


def print_stats(stats):
    print("\n  PERFORMANCE GERAL")
    print("  Posições fechadas : " + str(stats["total_closed"]))
    print("  Win rate          : " + str(stats["win_rate"]) + "%")
    print("  Avg win           : " + str(stats["avg_win"]) + "%")
    print("  Avg loss          : " + str(stats["avg_loss"]) + "%")
    print("  Profit factor     : " + str(stats["profit_factor"]))
    print("  P&L total         : " + str(stats["total_pnl"]) + "%")


def main():
    p = argparse.ArgumentParser(description="Forward Tracker")
    p.add_argument("--status",  action="store_true",
                   help="Ver posições sem actualizar preços")
    p.add_argument("--update",  action="store_true",
                   help="Actualizar todas as posições (default)")
    p.add_argument("--open",    nargs=6,
                   metavar=("TICKER", "ENTRY", "STOP", "T1", "T2", "STRATEGY"),
                   help="Abrir posição: HIMS 31.50 29.00 36.00 41.00 EP")
    p.add_argument("--close",   type=int, metavar="ID",
                   help="Fechar posição por ID")
    p.add_argument("--catalyst", default="",
                   help="Catalyst para nova posição (opcional)")
    args = p.parse_args()

    feed    = DataFeed(polygon_key=POLYGON_API_KEY)
    tracker = ForwardTracker(feed)

    print("\n" + "="*65)
    print("  INTEGRAL TRADING — Forward Tracker")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("="*65)

    # ── Abrir posição ─────────────────────────────────────────────────────────
    if args.open:
        ticker, entry, stop, t1, t2, strategy = args.open
        pos_id = tracker.open_position(
            ticker=ticker,
            strategy=strategy,
            entry_price=float(entry),
            stop_price=float(stop),
            target_1=float(t1),
            target_2=float(t2),
            catalyst=args.catalyst,
        )
        print("\n  ✅ Posição aberta: " + ticker.upper() +
              " @ $" + entry + " (ID #" + str(pos_id) + ")")

    # ── Fechar posição ────────────────────────────────────────────────────────
    elif args.close:
        ok = tracker.close_position(args.close, reason="manual")
        if ok:
            print("\n  ✅ Posição #" + str(args.close) + " fechada.")
        else:
            print("\n  ❌ Posição #" + str(args.close) + " não encontrada ou já fechada.")

    # ── Actualizar posições ───────────────────────────────────────────────────
    elif not args.status:
        open_positions = tracker.get_open_positions()
        if open_positions:
            print("\n  A actualizar " + str(len(open_positions)) + " posições...")
            summary = tracker.update_all()
            print("  Actualizadas : " + str(summary.updated))
            print("  Stops atingidos: " + str(summary.stopped_out))
            print("  Targets atingidos: " + str(summary.target_hit))
            if summary.errors:
                print("  Erros: " + str(summary.errors))
            if summary.closed_positions:
                print("\n  Fechadas nesta actualização:")
                for c in summary.closed_positions:
                    icon = "✅" if c["pnl_pct"] > 0 else "❌"
                    print("  " + icon + " " + c["ticker"] +
                          " | " + c["reason"] +
                          " | " + str(c["pnl_pct"]) + "%")

    # ── Mostrar estado ────────────────────────────────────────────────────────
    open_pos   = tracker.get_open_positions()
    closed_pos = tracker.get_closed_positions(limit=10)
    stats      = tracker.get_stats()

    print_open_positions(open_pos)
    print_closed_positions(closed_pos)
    print_stats(stats)

    print("\n" + "="*65)
    print("  Comandos úteis:")
    print("  Abrir  : python run_tracker.py --open HIMS 31.50 29.00 36.00 41.00 EP")
    print("  Fechar : python run_tracker.py --close <ID>")
    print("  Estado : python run_tracker.py --status")
    print("="*65 + "\n")


if __name__ == "__main__":
    main()
