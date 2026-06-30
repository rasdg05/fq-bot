#!/usr/bin/env python3
"""numerai_crypto_pipeline — arma una submission de Numerai Crypto (crypto.numer.ai)
DESDE los edges validados de FQ, reusando tooling de PRODUCCIÓN de punta a punta:

  data.binance.vision (klines 5m, GRATIS)  ->  build_submission (KL + POC + momentum)
     fetch_binance_vision_klines.fetch              numerai_signals_features

Numerai Crypto pide, por ronda, un ranking en [0,1] sobre >=100 SÍMBOLOS DE TOKENS
(mayor = mayor retorno esperado). Es la **ruta A** del adapt-to-compete (deep-research
2026-06): fit DIRECTO del bot, SIN reframe a acciones — los mismos features que validan
en producción (irreversibilidad KL + POC-distance + momentum) rankean tokens igual.

Pipeline (credential-free HASTA el CSV):
  1. universe : dict {numerai_symbol: binance_symbol}   (BTC -> BTCUSDT, ...)
  2. fetch    : kl_hist_<SYM>.parquet por token          (reusa el fetcher de producción)
  3. panel    : carga parquet, renombra ts->timestamp    (lo que pide prior_day_profile)
  4. signal   : build_submission(panel) -> [ticker, signal] cross-sectional en [0,1]
  5. formato  : -> CSV Numerai Crypto (columnas symbol,signal)

LA ÚLTIMA MILLA (con credenciales, NO aquí): descargar el universo REAL y SUBIR van con
`numerapi` + tu API key de Numerai. Esta herramienta PRODUCE el archivo; el upload se cablea
cuando exista la cuenta. Formato **CONFIRMADO** (deep-research 2026-06-30, docs.numer.ai/
numerai-crypto): columnas `symbol,signal`, valor 0-1 exclusivo, >=100 símbolos; universo en
`live_universe.parquet`. OJO: una submission SIN stake se puntúa pero **NO paga** (paper-trading);
el ingreso real EXIGE **stakear NMR** (un score negativo lo quema). Ruta A = construir track sin riesgo.

  python tools/numerai_crypto_pipeline.py --self-test                  # sintético, SIN red
  python tools/numerai_crypto_pipeline.py --start 2024-01-01 \
         --end 2026-06-27 --out sub.csv                                 # universo default
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import numerai_signals_features as nsf  # noqa: E402

# Universo DEFAULT mínimo: tokens con perp USDT en Binance que el bot ya conoce / puede
# bajar gratis. El universo REAL de Numerai Crypto (>=100) llega por numerapi
# (napi.download_dataset) y se mapea numerai_symbol -> binance_symbol aquí; los tokens sin
# perp en Binance Vision se OMITEN (mejor menos símbolos correctos que inventar señal).
DEFAULT_UNIVERSE = {
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "BCH": "BCHUSDT",
    "BNB": "BNBUSDT", "XRP": "XRPUSDT", "LTC": "LTCUSDT", "DOGE": "DOGEUSDT",
    "ADA": "ADAUSDT", "AVAX": "AVAXUSDT", "LINK": "LINKUSDT", "DOT": "DOTUSDT",
}

# CONFIRMADO (docs.numer.ai/numerai-crypto, deep-research 2026-06-30): symbol,signal; 0-1; >=100 símbolos.
NUMERAI_COLS = ["symbol", "signal"]


def _load_panel(universe, data_dir):
    """kl_hist_<binance>.parquet por token -> {numerai_symbol: ohlcv_df}. El fetcher
    escribe 'ts' (ms); prior_day_profile pide 'timestamp' -> se renombra."""
    panel = {}
    for nsym, bsym in universe.items():
        p = os.path.join(data_dir, "kl_hist_%s.parquet" % bsym)
        if not os.path.exists(p):
            continue
        df = pd.read_parquet(p)
        if "ts" in df.columns and "timestamp" not in df.columns:
            df = df.rename(columns={"ts": "timestamp"})
        panel[nsym] = df
    return panel


def build_panel_csv(universe, data_dir, out_csv):
    """panel -> submission Numerai Crypto (CSV symbol,signal). Devuelve el DataFrame."""
    panel = _load_panel(universe, data_dir)
    if not panel:
        raise SystemExit("sin parquets kl_hist_* en %s — corre el fetch primero" % data_dir)
    sub = nsf.build_submission(panel).rename(columns={"ticker": "symbol"})
    sub = sub[NUMERAI_COLS]
    sub.to_csv(out_csv, index=False)
    return sub


def fetch_universe(universe, start, end, data_dir):
    """Baja klines 5m por token (reusa el fetcher de producción, re-ejecutable)."""
    from datetime import date
    sys.path.insert(0, "tools")
    import fetch_binance_vision_klines as fbk
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    for bsym in universe.values():
        fbk.fetch(bsym, s, e, out_dir=data_dir)


def _self_test():
    """End-to-end SIN red: escribe parquets con el schema REAL del fetcher (ts en ms),
    recorre fetch->panel->signal->CSV y valida el formato de submission."""
    import tempfile
    rng = np.random.default_rng(0)
    d = tempfile.mkdtemp()
    n = 400
    base_ms = 1_700_000_000_000          # ms fijo (Date.now no se usa: reproducible)
    ts = base_ms + np.arange(n) * 86_400_000   # barras DIARIAS -> prior_day_profile OK
    uni = {}
    for i in range(12):
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
        df = pd.DataFrame({
            "ts": ts, "open": close, "high": close * 1.01, "low": close * 0.99,
            "close": close, "volume": rng.uniform(1e3, 1e4, n),
            "taker_buy_base": rng.uniform(1e2, 5e3, n)})
        bsym = "T%02dUSDT" % i
        df.to_parquet(os.path.join(d, "kl_hist_%s.parquet" % bsym), index=False)
        uni["TK%02d" % i] = bsym
    out = os.path.join(d, "sub.csv")
    sub = build_panel_csv(uni, d, out)
    assert list(sub.columns) == NUMERAI_COLS, sub.columns
    assert len(sub) > 0 and sub.signal.between(0, 1).all()
    assert os.path.exists(out)
    print("self-test OK — submission Numerai Crypto de ejemplo (%d símbolos):" % len(sub))
    print(sub.head(8).to_string(index=False))
    print("formato: columnas %s, signal en [%.3f, %.3f]"
          % (NUMERAI_COLS, sub.signal.min(), sub.signal.max()))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-test", action="store_true", help="end-to-end sintético, sin red")
    p.add_argument("--start", help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD")
    p.add_argument("--out", default="numerai_crypto_submission.csv")
    p.add_argument("--data-dir", default=os.environ.get("FQ_CVD_DIR", "data/okx"))
    p.add_argument("--no-fetch", action="store_true", help="usa los parquets ya bajados")
    a = p.parse_args(argv)
    if a.self_test:
        return _self_test()
    if not (a.start and a.end):
        print("usa --self-test, o --start/--end [--out --data-dir --no-fetch]")
        return 0
    if not a.no_fetch:
        fetch_universe(DEFAULT_UNIVERSE, a.start, a.end, a.data_dir)
    sub = build_panel_csv(DEFAULT_UNIVERSE, a.data_dir, a.out)
    print("submission -> %s  (%d símbolos, signal [%.3f, %.3f])"
          % (a.out, len(sub), sub.signal.min(), sub.signal.max()))
    print("ÚLTIMA MILLA: sube con numerapi + tu API key; confirma columnas vs "
          "docs.numer.ai/numerai-crypto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
