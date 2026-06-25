# -*- coding: utf-8 -*-
"""
COIN FRAGILITY — pruebas SIN RED del scorer de quiebra cross-seccional.

Verifica los SIGNOS documentados (Ma-Tu-Zhu): una moneda grande/líquida/poco
volátil/momentum+ sale SÓLIDA; una chica/ilíquida/volátil/momentum− sale FRÁGIL.
Y que los stablecoins (planos en todas las ventanas) se marcan is_stable. Todo con
cross-sección sintética (columnas estilo CoinGecko), cero red.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import coin_fragility as cf  # noqa: E402


def _coin(id, sym, mcap, vol, c1, c24, c7, c30):
    return {"id": id, "symbol": sym, "market_cap": mcap, "total_volume": vol,
            "price_change_percentage_1h_in_currency": c1,
            "price_change_percentage_24h_in_currency": c24,
            "price_change_percentage_7d_in_currency": c7,
            "price_change_percentage_30d_in_currency": c30}


def _universe():
    return pd.DataFrame([
        # grande, líquida, poco volátil, momentum + -> SÓLIDA
        _coin("solid", "SLD", 50e9, 5e9, 0.1, 0.5, 1.0, 8.0),
        # mediana
        _coin("mid", "MID", 2e9, 1e8, 0.5, 1.5, -3.0, -5.0),
        # chica, ilíquida, MUY volátil, momentum -- -> FRÁGIL
        _coin("fragile", "FRG", 80e6, 3e5, 5.0, -12.0, -25.0, -60.0),
        # stablecoin: plana en todas las ventanas
        _coin("astable", "USDX", 5e9, 8e8, 0.0, 0.01, -0.02, 0.0),
    ])


def test_signos_documentados_orden_fragilidad():
    d = cf.score(_universe())
    frag = {r["id"]: r["fragility"] for _, r in d.iterrows()}
    # la sólida menos frágil que la mediana, y la mediana menos que la frágil
    assert frag["solid"] < frag["mid"] < frag["fragile"]
    # rango sano
    assert 0.0 <= frag["solid"] <= 1.0 and 0.0 <= frag["fragile"] <= 1.0
    # la frágil debe ser claramente alta
    assert frag["fragile"] > 0.6


def test_stablecoin_se_marca():
    d = cf.score(_universe())
    st = {r["id"]: bool(r["is_stable"]) for _, r in d.iterrows()}
    assert st["astable"] is True          # plana -> stable
    assert st["solid"] is False           # se mueve -> tradeable
    assert st["fragile"] is False


def test_componentes_signos():
    d = cf.score(_universe()).set_index("id")
    # la chica tiene f_size alto (chica=frágil); la grande, bajo
    assert d.loc["fragile", "f_size"] > d.loc["solid", "f_size"]
    # la volátil tiene f_vol alto
    assert d.loc["fragile", "f_vol"] > d.loc["solid", "f_vol"]
    # momentum: la de mejor retorno 30d tiene f_mom más bajo
    assert d.loc["solid", "f_mom"] < d.loc["fragile", "f_mom"]


def test_rank01_monotonia():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    asc = cf._rank01(s, ascending=True)
    assert asc.iloc[0] < asc.iloc[-1]      # valor alto -> rank alto
    desc = cf._rank01(s, ascending=False)
    assert desc.iloc[0] > desc.iloc[-1]    # valor alto -> rank bajo


def test_salida_ordenada_y_columnas():
    d = cf.score(_universe())
    assert d["fragility"].is_monotonic_increasing      # ordenado sólido->frágil
    for col in ("f_size", "f_illiq", "f_vol", "f_mom", "is_stable", "sym"):
        assert col in d.columns
