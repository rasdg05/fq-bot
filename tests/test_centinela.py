# -*- coding: utf-8 -*-
"""centinela — horarios de sesion + digest (puro, sin red ni reloj real)."""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import centinela as ce
import killzones_pd as kz
import lectura


def _synth(n, tf_ms, *, seed=1):
    rng = np.random.default_rng(seed)
    close = 100.0 + rng.normal(0.02, 1.0, n).cumsum()
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = np.abs(rng.normal(1000, 200, n))
    ts = 1_700_000_000_000 + np.arange(n) * tf_ms
    return lectura._ensure_indicators(pd.DataFrame(
        {"timestamp": ts, "open": open_, "high": high, "low": low,
         "close": close, "volume": vol}))


def _at(h, m=0):
    return datetime(2026, 6, 3, h, m, tzinfo=kz.CDMX_TZ)   # miercoles


# ---- ventanas de apertura ----
def test_session_now_ny_am():
    assert ce.session_now(_at(8, 5)) == "ny_am_kz"       # 08:05 dentro de NY AM


def test_session_now_asia_open():
    assert ce.session_now(_at(17, 10)) == "asia_open"     # 17:10 dentro de Asia open


def test_session_now_londres_excluida():
    # 01:00-02:00 es apertura de Londres: NO dispara con el set por default
    assert ce.session_now(_at(1, 30)) is None


def test_session_now_fuera_de_apertura():
    assert ce.session_now(_at(12, 0)) is None


def test_londres_no_esta_en_default():
    assert "london_open_kz" not in ce.DEFAULT_OPENS


# ---- proxima apertura ----
def test_next_session_open_tarde_apunta_a_asia():
    nxt, name = ce.next_session_open(_at(12, 0))
    assert name == "asia_open" and nxt.hour == 17


def test_next_session_open_noche_apunta_a_ny_manana():
    nxt, name = ce.next_session_open(_at(20, 0))
    assert name == "ny_am_kz" and nxt.hour == 8 and nxt.day == 4   # manana


# ---- digest ----
def test_build_session_digest_compone_lecturas():
    dfs = {"SOL-USDT-SWAP": {"15m": _synth(200, 900000), "1h": _synth(200, 3600000, seed=2),
                             "4h": _synth(200, 14400000, seed=3), "1m": None}}
    d = ce.build_session_digest(["SOL-USDT-SWAP"], "ny_am_kz", _at(8, 5), dfs_by_symbol=dfs)
    assert d["session"] == "ny_am_kz"
    assert "DESPERTAR" in d["header"] and "Apertura NY" in d["header"]
    assert "LA LECTURA" in d["text"]
    assert len(d["blocks"]) == 1


# ---- telegram opt-in degrada sin credenciales ----
def test_telegram_send_sin_credenciales(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    ok, info = ce._telegram_send("hola")
    assert ok is False and "sin TELEGRAM" in info


def test_fire_key_formato():
    assert ce._fire_key(_at(8, 5), "ny_am_kz") == "2026-06-03|ny_am_kz"
