#!/usr/bin/env python3
"""numerai_signals_features — reframea los features VALIDADOS de FQ a una submission de
Numerai Signals (acciones). El adapt-to-compete de MENOR esfuerzo (deep-research 2026-06).

Numerai Signals pide un ranking en [0,1] por ticker sobre el universo (~5000 acciones):
mayor = mayor retorno esperado. Los features de FQ que TRANSFIEREN (puro precio, corren
en acciones igual que en cripto):
  - KL-irreversibilidad (régimen): el edge vive en irrev-BAJO (mean-reverting) — DSR ✓ cube.
  - POC-distance: distancia al POC del perfil de volumen del día previo (far>near, gate ✓).
  - momentum reciente: base direccional cross-sectional.
NO transfiere: CVD / F2-order-flow (son del libro del venue cripto) — se omiten a propósito.

`raw_score` es una HIPÓTESIS de traducción (combinar la base direccional con el régimen),
NO validada en acciones — el juez es el OOS EN VIVO de Numerai (submit sin stake, mide,
itera). Reusa el MISMO `irreversibility` y `volume_profile` que validan en producción.

  python tools/numerai_signals_features.py --self-test     # corre con data sintética
  # producción: build_submission({ticker: ohlcv_df, ...}) -> DataFrame[ticker, signal]
"""
import argparse
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
from validate_regime_irreversibility import irreversibility  # noqa: E402
import volume_profile as vp  # noqa: E402


def feature_row(df, *, kl_lookback=64, mom_lookback=20):
    """Features TRANSFERIBLES de FQ sobre la OHLCV de UN ticker (columnas
    open/high/low/close/volume [+ timestamp para el perfil del día previo])."""
    close = pd.to_numeric(df["close"], errors="coerce").to_numpy(float)
    close = close[np.isfinite(close)]
    out = {"kl_irrev": np.nan, "poc_dist": np.nan, "mom": np.nan}
    if len(close) >= 16:
        out["kl_irrev"] = float(irreversibility(close[-kl_lookback:]))
    prof = vp.prior_day_profile(df)
    if prof is not None and len(close):
        half = max((prof.vah - prof.val) / 2.0, 1e-9)
        out["poc_dist"] = abs(float(close[-1]) - prof.poc) / half
    if len(close) > mom_lookback and close[-mom_lookback] > 0:
        out["mom"] = float(close[-1] / close[-mom_lookback] - 1.0)
    return out


def raw_score(feats, *, kl_thr=0.34):
    """Combinación DEFAULT — hipótesis a tunear con el OOS de Numerai (NO validada en
    acciones). Base = reversión de momento (−mom), gateada por régimen reversible (KL-bajo,
    donde el edge paga) y tilteada por POC-distance (lejos del valor previo pesa más).
    None si falta algún feature."""
    if any(feats.get(k) is None or np.isnan(feats.get(k, np.nan))
           for k in ("kl_irrev", "poc_dist", "mom")):
        return np.nan
    kl_low = 1.0 if feats["kl_irrev"] < kl_thr else 0.3   # reversible = donde vive el edge
    far = feats["poc_dist"]                                # lejos del POC del día previo
    return kl_low * (-feats["mom"]) * (1.0 + far)


def build_submission(panel, *, kl_lookback=64, mom_lookback=20, kl_thr=0.34):
    """panel: dict {ticker: ohlcv_df}. Devuelve DataFrame[ticker, signal] con `signal`
    rankeado en [0,1] cross-sectional (formato Numerai Signals)."""
    rows = []
    for ticker, df in panel.items():
        s = raw_score(feature_row(df, kl_lookback=kl_lookback, mom_lookback=mom_lookback),
                      kl_thr=kl_thr)
        rows.append((ticker, s))
    out = pd.DataFrame(rows, columns=["ticker", "raw"]).dropna(subset=["raw"])
    if out.empty:
        return out.assign(signal=[]).drop(columns=["raw"])
    out["signal"] = out["raw"].rank(pct=True)             # [0,1] cross-sectional
    return out[["ticker", "signal"]].reset_index(drop=True)


def _synthetic_panel(n_tickers=40, n_bars=400, seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2024-01-01", periods=n_bars, freq="D", tz="UTC")
    panel = {}
    for i in range(n_tickers):
        ret = rng.normal(0, 0.02, n_bars)
        close = 100 * np.exp(np.cumsum(ret))
        panel["T%03d" % i] = pd.DataFrame({
            "timestamp": ts, "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": rng.uniform(1e3, 1e4, n_bars)})
    return panel


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)
    if a.self_test:
        sub = build_submission(_synthetic_panel())
        assert list(sub.columns) == ["ticker", "signal"]
        assert sub.signal.between(0, 1).all() and len(sub) > 0
        print("self-test OK — submission de ejemplo:")
        print(sub.head(8).to_string(index=False))
        print("... %d tickers, signal en [%.3f, %.3f]" % (len(sub), sub.signal.min(), sub.signal.max()))
        return 0
    print("usa --self-test, o importa build_submission({ticker: ohlcv_df, ...})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
