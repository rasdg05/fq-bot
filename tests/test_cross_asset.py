# -*- coding: utf-8 -*-
"""
CROSS-ASSET LEAD-LAG (BTC -> alt) — PRUEBA DE CAUSALIDAD (anti-leakage).

bt_features.cross_asset_features / attach_cross_asset_features alinean features
del activo LIDER (cruzado) a cada vela del primario. El punto que un fondo audita
es que NINGUNA feature en la vela primaria t pueda leer datos del cruzado
posteriores a t (de hecho, por shift_cross=1, ni siquiera el de t exacto: solo
<= t-1cross). Estos tests lo PRUEBAN sobre datos sinteticos, sin red ni motor:

  - un PICO afilado en el close del cruzado en t+1 NO aparece en la fila primaria
    t (causal);
  - una vela del cruzado fechada EXACTAMENTE en t NO se usa para el primario t
    (shift_cross=1 -> usa <= t-1); el contraste con shift_cross=0 lo deja a la
    vista;
  - attach_cross_asset_features casa por entry_index y tolera indices NaN /
    fuera de rango / negativos (rellena NaN, no revienta) preservando columnas;
  - todas las XBTC_FEATURE_COLUMNS estan presentes en la salida.
"""
import numpy as np
import pandas as pd

import bt_features as bf


def _flat_ohlcv(close, start="2024-01-01", freq="15min"):
    """OHLCV sintetico desde una serie de close (high/low = close +/- 1)."""
    close = np.asarray(close, dtype=float)
    n = len(close)
    ts = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame({
        "timestamp": ts, "open": close, "high": close + 1.0,
        "low": close - 1.0, "close": close, "volume": 100.0,
    })


def _aligned_pair(n=80, spike_bar=50, spike_val=200.0, base=100.0):
    """Primario PLANO + cruzado plano con un UNICO pico afilado en `spike_bar`.

    Timestamps IDENTICOS (mismo TF) -> merge_asof empareja vela-a-vela y el unico
    efecto temporal observable es el del pico, lo que aisla la prueba de
    causalidad (cualquier 'fuga' del futuro se veria como el pico apareciendo
    antes de tiempo).
    """
    flat = np.full(n, base)
    df_primary = _flat_ohlcv(flat)
    c_close = flat.copy()
    c_close[spike_bar] = spike_val
    df_cross = _flat_ohlcv(c_close)
    return df_primary, df_cross


def test_all_xbtc_columns_present():
    df_primary, df_cross = _aligned_pair()
    xf = bf.cross_asset_features(df_primary, df_cross)
    for col in bf.XBTC_FEATURE_COLUMNS:
        assert col in xf.columns, f"falta {col} en la salida"
    # una fila por vela primaria, mismo orden/longitud
    assert len(xf) == len(df_primary)


def test_spike_at_t_plus_1_not_visible_at_t():
    """Un pico en el close del cruzado en t+1 NO debe reflejarse en la fila
    primaria t (ni en t mismo: shift_cross=1). Solo aparece a partir de t+1
    primario, que lee el cruzado ya cerrado en t."""
    spike_bar = 50
    df_primary, df_cross = _aligned_pair(spike_bar=spike_bar)
    xf = bf.cross_asset_features(
        df_primary, df_cross, ret_bars=(3, 12, 48), atr_bars=14,
        trend_ma_bars=48, relstr_bars=12, shift_cross=1)

    # ret_N del cruzado es 0 mientras no se vea el pico (serie plana). En las filas
    # primarias <= spike_bar el pico (en cross-bar spike_bar) aun no es conocible.
    for k in (spike_bar - 2, spike_bar - 1, spike_bar):
        assert xf["xbtc_ret_3"].iloc[k] == 0.0, (
            f"fila primaria {k} ve el pico de cross t+1 (LEAKAGE): "
            f"ret_3={xf['xbtc_ret_3'].iloc[k]}")
        # trend tambien plano (close == MA) antes del pico
        assert xf["xbtc_trend"].iloc[k] == 0.0

    # PRIMERA fila que SI refleja el pico es spike_bar+1 (lee cross cerrado en
    # spike_bar). pct_change(3): (200-100)/100 = 1.0.
    assert xf["xbtc_ret_3"].iloc[spike_bar + 1] == 1.0
    assert xf["xbtc_trend"].iloc[spike_bar + 1] == 1.0
    # relstr = ret_primario - ret_cruzado; el primario sigue plano (0) -> -1.0.
    assert xf["xbtc_relstr"].iloc[spike_bar + 1] == -1.0


def test_shift_cross_excludes_same_stamped_cross_bar():
    """Una vela del cruzado fechada EXACTAMENTE en t NO se usa para el primario t
    cuando shift_cross=1 (usa <= t-1). El contraste con shift_cross=0 (que SI la
    usaria) demuestra que el desplazamiento es el que aporta la causalidad
    conservadora, no el merge_asof por si solo."""
    spike_bar = 50
    df_primary, df_cross = _aligned_pair(spike_bar=spike_bar)

    # shift_cross=0: la vela del cruzado en spike_bar (timestamp == t) SE usa para
    # el primario en spike_bar -> el pico es visible la MISMA vela.
    xf0 = bf.cross_asset_features(df_primary, df_cross, shift_cross=0)
    assert xf0["xbtc_ret_3"].iloc[spike_bar] == 1.0, (
        "con shift_cross=0 el cruzado fechado en t deberia verse en t")

    # shift_cross=1 (conservador, default): esa MISMA vela NO se usa en spike_bar.
    xf1 = bf.cross_asset_features(df_primary, df_cross, shift_cross=1)
    assert xf1["xbtc_ret_3"].iloc[spike_bar] == 0.0, (
        "con shift_cross=1 el cruzado fechado en t NO debe usarse en t (<= t-1)")
    # y se desplaza exactamente UNA vela: aparece en spike_bar+1.
    assert xf1["xbtc_ret_3"].iloc[spike_bar + 1] == 1.0


def test_merge_asof_backward_uses_only_past_cross():
    """Cuando el cruzado va RETRASADO respecto al primario (su ultima vela cierra
    antes que t), merge_asof backward toma esa ultima vela <= t y JAMAS rellena
    desde el futuro. Se prueba truncando el cruzado: las filas primarias mas alla
    del fin del cruzado reusan el ultimo valor pasado (no NaN por 'futuro')."""
    n = 80
    df_primary, df_cross_full = _aligned_pair(n=n, spike_bar=50)
    # cruzado que TERMINA en la vela 60: para primarias 61..79 no hay 'futuro' del
    # cruzado; backward debe reusar la vela 60 (la mas reciente <= t), nunca mirar
    # hacia adelante (no hay nada) ni inventar.
    df_cross = df_cross_full.iloc[:61].reset_index(drop=True)
    xf = bf.cross_asset_features(df_primary, df_cross, shift_cross=1)
    # el pico (cross-bar 50) ya quedo absorbido y la serie es plana de nuevo; las
    # filas finales reflejan el estado pasado (ret_3 == 0.0), no NaN ni un salto.
    assert not np.isnan(xf["xbtc_ret_3"].iloc[70])
    assert xf["xbtc_ret_3"].iloc[70] == 0.0
    assert xf["xbtc_ret_3"].iloc[n - 1] == 0.0


def test_attach_maps_by_entry_index_and_tolerates_bad_index():
    """attach_cross_asset_features casa cada fila por su entry_index (posicion en
    df_primary) y tolera entry_index NaN / fuera de rango / negativo: rellena NaN
    en esas filas, no revienta, y preserva las columnas originales del evento."""
    n = 80
    spike_bar = 50
    df_primary, df_cross = _aligned_pair(n=n, spike_bar=spike_bar)

    events = pd.DataFrame({
        # mezcla de indices validos y patologicos
        "entry_index": [10, spike_bar + 1, np.nan, -5, n + 100, spike_bar - 1],
        "foo": [1, 2, 3, 4, 5, 6],
        "entry_ts": pd.to_datetime("2024-01-01"),
    })
    out = bf.attach_cross_asset_features(events, df_primary, df_cross, shift_cross=1)

    # columnas originales intactas + todas las xbtc_ presentes
    assert "foo" in out.columns and "entry_index" in out.columns
    for col in bf.XBTC_FEATURE_COLUMNS:
        assert col in out.columns
    assert len(out) == len(events)

    # mapeo correcto por entry_index: la fila con entry_index=spike_bar+1 ve el
    # pico (ret_3 == 1.0); la de spike_bar-1 sigue plana (0.0).
    r_spike = out.loc[out["entry_index"] == spike_bar + 1].iloc[0]
    assert r_spike["xbtc_ret_3"] == 1.0
    r_pre = out.loc[out["entry_index"] == spike_bar - 1].iloc[0]
    assert r_pre["xbtc_ret_3"] == 0.0

    # indices patologicos (posiciones 2,3,4: NaN, -5, n+100) -> NaN, sin crash
    bad = out.iloc[[2, 3, 4]]
    assert bad["xbtc_ret_3"].isna().all()
    # los validos (posiciones 0,1,5) NO son NaN
    good = out.iloc[[0, 1, 5]]
    assert good["xbtc_ret_3"].notna().all()


def test_attach_empty_and_none_cross_are_safe():
    """Casos borde: eventos vacios y cruzado ausente devuelven columnas xbtc_
    (NaN) sin romper -- el harness debe poder correr aunque no haya cross-asset."""
    n = 40
    df_primary, df_cross = _aligned_pair(n=n, spike_bar=20)

    empty = bf.attach_cross_asset_features(
        pd.DataFrame({"entry_index": []}), df_primary, df_cross)
    assert all(c in empty.columns for c in bf.XBTC_FEATURE_COLUMNS)
    assert len(empty) == 0

    # cruzado None -> todo NaN, longitud == primario
    none_cross = bf.cross_asset_features(df_primary, None)
    assert len(none_cross) == n
    assert none_cross["xbtc_ret_3"].isna().all()

    events = pd.DataFrame({"entry_index": [1, 2, 3], "foo": [9, 9, 9]})
    out_none = bf.attach_cross_asset_features(events, df_primary, None)
    assert all(c in out_none.columns for c in bf.XBTC_FEATURE_COLUMNS)
    assert out_none["xbtc_ret_3"].isna().all()
    assert "foo" in out_none.columns
