#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI para descargar histgrico OHLCV a Parquet usando bt_data.

Etapa 1 del harness de research. Descarga el mismo simbolo desde uno o varios
exchanges (por defecto Binance + Bybit) para poder validar robustez cross-venue
ante un fondo (no sobreajuste a un solo exchange).

Ejemplos:
    # SOL perp, 2 anos, 1m, Binance + Bybit -> data/<exchange>/SOL-USDT_1m.parquet
    python tools/build_dataset.py --symbol SOL/USDT --timeframe 1m \\
        --market swap --years 2 --exchanges binance,bybit

    # Rango explicito
    python tools/build_dataset.py --symbol SOL/USDT --timeframe 15m \\
        --since 2023-01-01 --until 2024-01-01

Requiere ccxt instalado y red. Los Parquet caen bajo data/ (gitignored).
"""
import argparse
import logging
import sys
from datetime import datetime, timezone, timedelta

# Permite ejecutar desde la raiz del repo sin instalar.
sys.path.insert(0, ".")
import bt_data as bt


def _to_ms(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def main(argv=None):
    p = argparse.ArgumentParser(description="Descarga OHLCV historico a Parquet")
    p.add_argument("--symbol", default="SOL/USDT")
    p.add_argument("--timeframe", default="1m")
    p.add_argument("--market", default="swap",
                   choices=["spot", "swap", "future"],
                   help="spot o swap (perpetuo)")
    p.add_argument("--exchanges", default="binance,bybit",
                   help="CSV de ids ccxt")
    p.add_argument("--since", help="YYYY-MM-DD (UTC)")
    p.add_argument("--until", help="YYYY-MM-DD (UTC); default ahora")
    p.add_argument("--years", type=float,
                   help="atajo: ultimos N anos (ignora --since)")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--page-limit", type=int, default=1000)
    p.add_argument("--sleep", type=float, default=0.0,
                   help="pausa entre paginas (s); usa rate-limit de ccxt si 0")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    until_ms = _to_ms(args.until) if args.until else now_ms
    if args.years:
        until_ms = now_ms
        since_ms = int(
            (datetime.now(timezone.utc) - timedelta(days=365 * args.years))
            .timestamp() * 1000
        )
    elif args.since:
        since_ms = _to_ms(args.since)
    else:
        p.error("indica --since YYYY-MM-DD o --years N")

    for name in [e.strip() for e in args.exchanges.split(",") if e.strip()]:
        print(f"\n=== {name} {args.symbol} {args.timeframe} ({args.market}) ===")
        ex = bt.make_exchange(name, market_type=args.market)
        _df, rep = bt.build_dataset(
            ex, args.symbol, args.timeframe, since_ms, until_ms,
            exchange_name=name, data_dir=args.data_dir,
            page_limit=args.page_limit, sleep_s=args.sleep,
        )
        print(
            f"n={rep['n']} completeness={rep['completeness']:.4f} "
            f"gaps={len(rep['gaps'])} missing_bars={rep['missing_bars']} "
            f"-> {rep['saved_to']}"
        )
        if rep["gaps"]:
            print("  primeros gaps:")
            for ts0, ts1, miss in rep["gaps"][:5]:
                print(f"    {ts0} -> {ts1}  ({miss} barras)")


if __name__ == "__main__":
    main()
