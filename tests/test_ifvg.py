# -*- coding: utf-8 -*-
"""
Tests de detect_ifvgs (Inverse Fair Value Gap, ict_smc).

Un FVG que el precio INVALIDA cerrando al otro lado del gap se 'invierte' y pasa
a actuar como S/R opuesto:
  - FVG bajista roto al alza   -> IFVG alcista (soporte / gatillo LONG)
  - FVG alcista roto a la baja  -> IFVG bajista (resistencia / gatillo SHORT)

NOTA: detect_ifvgs busca el FVG centrado en la vela i (prev=i-1, next=i+1) con
i>=2, asi que el gap se coloca en el indice 2 y la invalidacion despues.

Verifica:
  - inversion alcista (bearish FVG -> IFVG bullish) sirve sesgo LONG.
  - inversion bajista (bullish FVG -> IFVG bearish) sirve sesgo SHORT.
  - un FVG NO invalidado no produce IFVG.
  - re-invalidacion (precio vuelve a cerrar al lado original) descarta el IFVG.
  - el tag 'ifvg_<dir>' entra en build_confluence cuando el precio esta en zona.
"""
import sys

try:
    import pandas_ta  # noqa: F401
except ImportError:
    try:
        import pandas_ta_classic as _ta
        sys.modules["pandas_ta"] = _ta
    except ImportError:
        pass

import pandas as pd
import ict_smc


def _df(rows):
    """rows: lista de (open, high, low, close)."""
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c} for (o, h, l, c) in rows]
    )


def test_bearish_fvg_inverts_to_bullish_ifvg_long():
    # Bearish FVG en i=2: prev_low(100) > next_high(98) -> gap [98,100].
    # Luego el precio CIERRA por encima de 100 -> el FVG bajista se invalida
    # al alza -> IFVG alcista (soporte, LONG).
    rows = [
        (101, 103, 101, 102),     # 0: filler
        (102, 102, 100, 101),     # 1: prev (low=100)
        (100, 100, 97, 98.5),     # 2: vela del gap
        (98, 98, 96, 97),         # 3: next (high=98) -> bearish FVG [98,100]
        (97, 101, 97, 100.8),     # 4: CIERRA en 100.8 > 100 -> invalida al alza
        (101, 103, 100.5, 102),   # 5: sigue arriba, no re-invalida
    ]
    ifvgs = ict_smc.detect_ifvgs(_df(rows))
    assert any(x.direction == "bullish" and x.origin == "bearish" for x in ifvgs)


def test_bullish_fvg_inverts_to_bearish_ifvg_short():
    # Bullish FVG en i=2: prev_high(100) < next_low(102) -> gap [100,102].
    # Luego el precio CIERRA por debajo de 100 -> se invalida a la baja ->
    # IFVG bajista (resistencia, SHORT).
    rows = [
        (99, 100, 98, 99),        # 0: filler
        (99, 100, 98, 99.5),      # 1: prev (high=100)
        (100, 103, 100, 102.5),   # 2: vela del gap
        (102, 104, 102, 103),     # 3: next (low=102) -> bullish FVG [100,102]
        (102, 102.5, 99, 99.5),   # 4: CIERRA en 99.5 < 100 -> invalida a la baja
        (99, 100, 97, 98),        # 5: sigue abajo, no re-invalida
    ]
    ifvgs = ict_smc.detect_ifvgs(_df(rows))
    assert any(x.direction == "bearish" and x.origin == "bullish" for x in ifvgs)


def test_non_invalidated_fvg_yields_no_ifvg():
    # Bullish FVG en i=2 que NO se invalida (precio se mantiene sobre el gap).
    rows = [
        (99, 100, 98, 99),        # 0: filler
        (99, 100, 98, 99.5),      # 1: prev (high=100)
        (100, 103, 100, 102.5),   # 2: vela del gap
        (102, 104, 102, 103),     # 3: next (low=102) -> bullish FVG [100,102]
        (103, 105, 102.5, 104),   # 4: respeta el gap como soporte
        (104, 106, 103.5, 105),   # 5
    ]
    assert ict_smc.detect_ifvgs(_df(rows)) == []


def test_reinvalidation_discards_ifvg():
    # Bullish FVG -> invalida a la baja (IFVG bearish) -> pero luego CIERRA de
    # vuelta arriba del top -> re-invalidado -> se descarta.
    rows = [
        (99, 100, 98, 99),        # 0: filler
        (99, 100, 98, 99.5),      # 1: prev (high=100)
        (100, 103, 100, 102.5),   # 2: vela del gap
        (102, 104, 102, 103),     # 3: next (low=102) -> bullish FVG [100,102]
        (102, 102.5, 99, 99.5),   # 4: invalida a la baja (cierre 99.5 < 100)
        (100, 103, 99, 102.8),    # 5: re-invalida: cierre 102.8 > 102 (top)
    ]
    assert ict_smc.detect_ifvgs(_df(rows)) == []


def test_ifvg_enters_build_confluence():
    ifvg = ict_smc.IFVG(top=100.0, bottom=98.0, ts=0,
                        direction="bullish", origin="bearish")

    class _F:
        fib_levels = {}
        order_blocks = {"bullish": None, "bearish": None}
        fvgs = []
        ifvgs = [ifvg]
        recent_sweep = None
        choch = False
        pd_zone = "discount"

    conf = ict_smc.build_confluence(99.0, _F(), atr_proxy=1.0)
    assert "ifvg_bullish" in conf
