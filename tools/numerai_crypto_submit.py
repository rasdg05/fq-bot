#!/usr/bin/env python3
"""numerai_crypto_submit — runner DIARIO de submission a Numerai Crypto (crypto.numer.ai).
Orquesta el pipeline ya construido para correr en cron una vez al día:

  universo Numerai (live_universe)  ->  klines Binance Vision  ->  build_submission  ->  CSV
        (numerapi, opcional)             (fetcher de producción)   (KL+POC+momentum)   (+ upload opcional)

Numerai Crypto pide >=100 SÍMBOLOS de tokens, valor 0-1 (`symbol,signal`). El universo (~300
tokens, dinámico) se baja con `numerapi`; cada token se mapea a su perp USDT de Binance
(TOKEN+USDT por defecto) y se baja su OHLCV; los tokens sin perp en Binance Vision se OMITEN
(se loguea la cobertura — NADA de truncado silencioso). El edge usa solo precio (KL/POC/mom),
así que sirve aunque no tengamos order-flow de cada token.

Credenciales (solo para el upload real, vía env): NUMERAI_PUBLIC_ID, NUMERAI_SECRET_KEY,
NUMERAI_MODEL_ID. SIN ellas, produce el CSV y NO sube. **OJO (medido 2026-06-30): una
submission SIN stake se puntúa pero NO paga — es paper. El ingreso real EXIGE stakear NMR.**

  python tools/numerai_crypto_submit.py --self-test                    # offline, sin red/creds
  python tools/numerai_crypto_submit.py --start 2024-01-01 --end 2026-06-29 --out sub.csv
  python tools/numerai_crypto_submit.py --start ... --end ... --upload  # requiere numerapi + creds
"""
import argparse
import os
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import numerai_crypto_pipeline as ncp  # noqa: E402

MIN_SYMBOLS = 100   # piso de Numerai Crypto por submission


def live_universe(*, universe_file=None, data_dir="."):
    """Lista de tokens del universo. De un archivo local (una línea/símbolo, testable) o, si no,
    de `numerapi` (lazy import). Devuelve símbolos en MAYÚSCULAS, sin duplicados."""
    if universe_file and os.path.exists(universe_file):
        with open(universe_file) as fh:
            toks = [ln.strip().upper() for ln in fh if ln.strip() and not ln.startswith("#")]
        return sorted(set(toks))
    try:
        import numerapi  # noqa: F401
    except ImportError:
        raise SystemExit("numerapi no instalado y sin --universe-file. "
                         "pip install numerapi, o pasa un archivo de universo.")
    napi = _napi()
    path = napi.download_dataset("crypto/v1.0/live_universe.parquet",
                                 os.path.join(data_dir, "live_universe.parquet"))
    import pandas as pd
    col = "symbol"
    df = pd.read_parquet(path)
    if col not in df.columns:
        col = df.columns[0]
    return sorted(set(df[col].astype(str).str.upper().tolist()))


def to_binance(symbols):
    """token -> perp USDT de Binance (TOKEN+USDT por defecto). El fetcher salta los que no
    existan en Binance Vision, así que sobre-mapear es seguro."""
    return {tok: "%sUSDT" % tok for tok in symbols}


def _napi():
    import numerapi
    return numerapi.NumerAPI(os.environ.get("NUMERAI_PUBLIC_ID"),
                             os.environ.get("NUMERAI_SECRET_KEY"))


def _upload(csv_path):
    """Sube el CSV a Numerai (lazy). Requiere creds en env. El método/firma EXACTOS del API
    de cripto se CONFIRMAN contra la versión de numerapi al integrar (aquí el camino documentado)."""
    model_id = os.environ.get("NUMERAI_MODEL_ID")
    if not (os.environ.get("NUMERAI_PUBLIC_ID") and os.environ.get("NUMERAI_SECRET_KEY")):
        raise SystemExit("upload pide NUMERAI_PUBLIC_ID + NUMERAI_SECRET_KEY en el entorno.")
    napi = _napi()
    # numerapi: upload_predictions(file_path, model_id=...) — confirmar el endpoint de CRYPTO
    # según la versión instalada (puede requerir tournament/model especifico de cripto).
    napi.upload_predictions(csv_path, model_id=model_id)
    print("upload OK -> modelo %s" % model_id)


def run(start, end, *, out_csv, data_dir, universe_file=None, upload=False):
    toks = live_universe(universe_file=universe_file, data_dir=data_dir)
    mapping = to_binance(toks)
    ncp.fetch_universe(mapping, start, end, data_dir)
    sub = ncp.build_panel_csv(mapping, data_dir, out_csv)
    cov = len(sub)
    print("cobertura: %d/%d tokens con señal computable -> %s" % (cov, len(toks), out_csv))
    if cov < MIN_SYMBOLS:
        print("AVISO: %d < %d (piso de Numerai Crypto). Faltan tokens con perp/data — "
              "el submit real necesita >=%d." % (cov, MIN_SYMBOLS, MIN_SYMBOLS))
    if upload:
        _upload(out_csv)
    return sub


def _self_test():
    """Offline, sin red ni creds: universo de archivo + parquets sintéticos -> CSV válido."""
    import tempfile
    import numpy as np
    import pandas as pd
    d = tempfile.mkdtemp()
    n = 300
    ts = 1_700_000_000_000 + np.arange(n) * 86_400_000
    toks = ["TK%03d" % i for i in range(8)]
    uf = os.path.join(d, "universe.txt")
    with open(uf, "w") as fh:
        fh.write("\n".join(toks))
    rng = np.random.default_rng(0)
    for tok in toks:
        c = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
        df = pd.DataFrame({"ts": ts, "open": c, "high": c * 1.01, "low": c * 0.99,
                           "close": c, "volume": rng.uniform(1e3, 1e4, n)})
        ncp._write_klines(df, ncp._kl_path(d, "%sUSDT" % tok))
    # con los parquets ya puestos, build sin fetch (red) — replica run() sin la parte de red.
    mapping = to_binance(live_universe(universe_file=uf, data_dir=d))
    sub = ncp.build_panel_csv(mapping, d, os.path.join(d, "sub.csv"))
    assert list(sub.columns) == ["symbol", "signal"]
    assert len(sub) == 8 and sub.signal.between(0, 1).all()
    print("self-test OK — submission de %d símbolos (universo de archivo, sin red):" % len(sub))
    print(sub.head(6).to_string(index=False))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--out", default="numerai_crypto_submission.csv")
    p.add_argument("--data-dir", default=os.environ.get("FQ_CVD_DIR", "data/okx"))
    p.add_argument("--universe-file", help="archivo local de universo (1 símbolo/línea); si no, numerapi")
    p.add_argument("--upload", action="store_true", help="sube vía numerapi (requiere creds en env)")
    a = p.parse_args(argv)
    if a.self_test:
        return _self_test()
    if not (a.start and a.end):
        print("usa --self-test, o --start/--end [--out --data-dir --universe-file --upload]")
        return 0
    run(a.start, a.end, out_csv=a.out, data_dir=a.data_dir,
        universe_file=a.universe_file, upload=a.upload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
