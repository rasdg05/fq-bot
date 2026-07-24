# -*- coding: utf-8 -*-
"""regime_timeline: clasificación de régimen con la irreversibilidad KL validada,
construcción sin mirar el futuro y búsqueda as-of. (numpy; se salta si no está)."""
import os
import sys
from datetime import datetime, timedelta

import pytest

np = pytest.importorskip("numpy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import regime_timeline as rt


def test_classify_devuelve_label_valido_o_none():
    rng = np.random.default_rng(0)
    closes = list(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 200))))
    lab = rt.classify(closes)
    assert lab in rt.LABELS
    assert rt.classify([1, 2, 3]) is None            # sin historia suficiente -> None


def test_build_timeline_es_causal_y_ordenado():
    rng = np.random.default_rng(1)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 180)))
    t0 = datetime(2026, 1, 1)
    bars = [(t0 + timedelta(hours=i), float(c)) for i, c in enumerate(closes)]
    tl = rt.build_timeline(bars, warmup=64)
    assert tl and all(lab in rt.LABELS for _, lab in tl)
    times = [t for t, _ in tl]
    assert times == sorted(times)                    # ascendente
    assert times[0] >= bars[64][0]                   # respeta el warmup (no mira el futuro)


def test_regime_at_bisect():
    tl = [(datetime(2026, 1, 1), rt.FRIO_DIR),
          (datetime(2026, 1, 5), rt.CALIENTE_SINDIR)]
    assert rt.regime_at(tl, datetime(2025, 12, 1)) is None
    assert rt.regime_at(tl, datetime(2026, 1, 3)) == rt.FRIO_DIR
    assert rt.regime_at(tl, datetime(2026, 1, 9)) == rt.CALIENTE_SINDIR
    assert rt.regime_at([], datetime(2026, 1, 1)) is None


def test_timeline_from_ohlcv_ms_epoch():
    import pandas as pd
    rng = np.random.default_rng(2)
    n = 160
    ts = 1_700_000_000_000 + np.arange(n) * 3_600_000     # ms, horario
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    df = pd.DataFrame({"timestamp": ts, "close": close})
    tl = rt.timeline_from_ohlcv(df, warmup=64)
    assert tl and all(lab in rt.LABELS for _, lab in tl)
