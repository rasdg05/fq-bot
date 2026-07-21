# -*- coding: utf-8 -*-
"""Multi-simbolo para /analisis y alias (2026-07-20, pedido de RasDG):
1) /analisis (y /lectura /niveles /pspace /claude /ia) toman un 1er argumento
   opcional SOL/BTC/ETH (default SOL) -> fetch_ohlcv pide el par correcto.
2) La tabla cruda de probabilidades QTE (Monte Carlo de 500 paths + optimizer
   QAOA) sale de cmd_lectura: era "carga inutil" -- computo pesado en cada
   /analisis on-demand solo para imprimir numeros que nadie usaba para
   decidir. El battle plan VIP (2000 paths, cmd_analisis_vip) sigue intacto,
   ese si alimenta una decision real."""
import numpy as np
import pandas as pd

import fq_bot_v3_2 as b
import vip_format as vf


_LEVELS = {"entry": 145.0, "sl": 142.0, "risk": 3.0,
           "tp1": 149.0, "rr_tp1": 1.33, "tp2": 153.0, "rr_tp2": 2.67,
           "tp3": 158.0, "rr_tp3": 4.33}
_LAST = {"close": 145.0}


def test_build_vip_analisis_hashtag_dinamico_por_par():
    """Regresion: build_vip_analisis usaba HASHTAGS_SIGNAL hardcodeado a
    '#FQ #SOLUSDT' -- /analisis BTC o ETH mostraba el tag de SOL igual."""
    out_btc = vf.build_vip_analisis("long", dict(_LEVELS), "alcista", 3.0, _LAST,
                                    pair="BTC/USDT")
    out_eth = vf.build_vip_analisis("long", dict(_LEVELS), "alcista", 3.0, _LAST,
                                    pair="ETH/USDT")
    out_default = vf.build_vip_analisis("long", dict(_LEVELS), "alcista", 3.0, _LAST)

    assert "#FQ #BTCUSDT" in out_btc and "#SOLUSDT" not in out_btc
    assert "#FQ #ETHUSDT" in out_eth and "#SOLUSDT" not in out_eth
    assert "#FQ #SOLUSDT" in out_default  # sin pair -> fallback historico


def _synth_df(n=220, seed=1):
    rng = np.random.default_rng(seed)
    close = 100.0 + rng.normal(0.02, 1.0, n).cumsum()
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = np.abs(rng.normal(1000, 200, n))
    ts = pd.date_range("2026-01-01", periods=n, freq="5min")
    return pd.DataFrame({"timestamp": ts, "open": open_, "high": high,
                         "low": low, "close": close, "volume": vol})


# ============================================================
# _resolve_analisis_pair
# ============================================================
def test_resolve_pair_default_sol_sin_argumentos():
    assert b._resolve_analisis_pair([]) == "SOL"
    assert b._resolve_analisis_pair(None) == "SOL"


def test_resolve_pair_reconoce_btc_eth_case_insensitive():
    assert b._resolve_analisis_pair(["btc"]) == "BTC"
    assert b._resolve_analisis_pair(["ETH"]) == "ETH"
    assert b._resolve_analisis_pair(["Eth/usdt"]) == "ETH"


def test_resolve_pair_desconocido_cae_a_sol():
    """Nunca rompe el comando: un ccy no soportado (o basura) cae a SOL."""
    assert b._resolve_analisis_pair(["DOGE"]) == "SOL"
    assert b._resolve_analisis_pair(["asdf123"]) == "SOL"


# ============================================================
# cmd_lectura: multi-simbolo + sin tabla QTE
# ============================================================
def _wire_lectura(monkeypatch):
    calls = []

    def fake_fetch(exchange, symbol, tf_id, limit=200):
        calls.append((symbol, tf_id))
        return _synth_df(seed=abs(hash(symbol)) % 1000)

    monkeypatch.setattr(b, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(b.claude_ai, "is_available", lambda: False)
    return calls


def test_cmd_lectura_default_sol(monkeypatch):
    calls = _wire_lectura(monkeypatch)
    out = b.cmd_lectura(None)
    assert all(sym == b.SYMBOL for sym, _tf in calls)
    assert "SOL/USDT" in out
    assert "#SOL" in out


def test_cmd_lectura_btc_arg_pide_simbolo_btc(monkeypatch):
    calls = _wire_lectura(monkeypatch)
    out = b.cmd_lectura(None, "BTC")
    assert calls  # se hicieron fetches
    assert all(sym == b.SYMBOL_BTC for sym, _tf in calls)
    assert "BTC/USDT" in out
    assert "#BTC" in out
    assert "SOL/USDT" not in out


def test_cmd_lectura_eth_arg_pide_simbolo_eth(monkeypatch):
    calls = _wire_lectura(monkeypatch)
    out = b.cmd_lectura(None, "ETH")
    assert all(sym == b.SYMBOL_ETH for sym, _tf in calls)
    assert "ETH/USDT" in out
    assert "#ETH" in out


def test_cmd_lectura_pair_no_reconocido_cae_a_sol(monkeypatch):
    calls = _wire_lectura(monkeypatch)
    out = b.cmd_lectura(None, "DOGE")
    assert all(sym == b.SYMBOL for sym, _tf in calls)
    assert "SOL/USDT" in out


def test_cmd_lectura_cooldown_gateado_por_par(monkeypatch):
    """El cooldown por TF solo se trackea para SOL (unico symbol cuyo
    STATE.last_signal_ts_tf se escribe); BTC/ETH muestran una nota en vez de
    un numero potencialmente incorrecto (mezclaria el cooldown de SOL)."""
    _wire_lectura(monkeypatch)
    out_sol = b.cmd_lectura(None, "SOL")
    out_btc = b.cmd_lectura(None, "BTC")
    assert "Cooldown: listo" in out_sol or "Cooldown: {" not in out_sol
    assert "n/a (motor BTC propio)" in out_btc
    assert "n/a (motor SOL propio)" not in out_sol


def test_cmd_lectura_sin_tabla_qte(monkeypatch):
    """Regresion: cmd_lectura ya NO corre el Monte Carlo de 500 paths +
    optimizer QAOA solo para imprimir la tabla de probabilidades -- 'carga
    inutil' segun RasDG (2026-07-20). Ni el texto ni el computo deben
    aparecer/ejecutarse."""
    _wire_lectura(monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("quantum_analysis NO debe correr en cmd_lectura")
    monkeypatch.setattr(b.qt, "quantum_analysis", _boom, raising=False)

    out = b.cmd_lectura(None, "SOL")
    assert "QUANTUM TIMELINES ENGINE" not in out
    assert "PROBABILIDADES (sobre niveles propuestos)" not in out
    assert "Toca SL primero" not in out


# ============================================================
# cmd_lectura: reversion parcial 2026-07-21 -- TP1/TP2 de vuelta SOLO en el
# TF anchor (5m). RasDG: "como quedo ahora no dice TPs y esta muy confuso,
# regresame TP1 y 2 en TF 5m y el nivel crudo de eso, eso si me sirve para
# operar". TP3/TP4 NO vuelven (el pedido fue especificamente TP1/TP2); 15m/1h
# se quedan en sesgo+contexto, sin niveles.
# ============================================================
def test_cmd_lectura_5m_trae_entry_sl_tp1_tp2(monkeypatch):
    _wire_lectura(monkeypatch)
    out = b.cmd_lectura(None, "SOL")
    assert "[INTRADIA 5m]" in out
    idx_5m = out.index("[INTRADIA 5m]")
    idx_15m = out.index("[SCALPING 15m]")
    block_5m = out[idx_5m:idx_15m]
    assert "Entry:" in block_5m
    assert "SL:" in block_5m
    assert "TP1:" in block_5m
    assert "TP2:" in block_5m


def test_cmd_lectura_5m_no_trae_tp3_ni_tp4(monkeypatch):
    _wire_lectura(monkeypatch)
    out = b.cmd_lectura(None, "SOL")
    idx_5m = out.index("[INTRADIA 5m]")
    idx_15m = out.index("[SCALPING 15m]")
    block_5m = out[idx_5m:idx_15m]
    assert "TP3:" not in block_5m
    assert "TP4:" not in block_5m


def test_cmd_lectura_15m_y_1h_siguen_sin_niveles(monkeypatch):
    _wire_lectura(monkeypatch)
    out = b.cmd_lectura(None, "SOL")
    idx_15m = out.index("[SCALPING 15m]")
    resto = out[idx_15m:]
    # Corta antes de la lectura tactica de Claude (esa es prosa, no niveles
    # estructurados, y no aplica el mismo criterio de "Entry:"/"TP1:" exacto).
    thin_idx = resto.find("LECTURA TACTICA")
    if thin_idx != -1:
        resto = resto[:thin_idx]
    assert "Entry:" not in resto
    assert "TP1:" not in resto
    assert "TP2:" not in resto


def test_cmd_lectura_5m_anchor_cambia_con_analisis_anchor_tf(monkeypatch):
    """Si ANALISIS_ANCHOR_TF cambiara, los niveles deben seguirlo (no quedar
    hardcodeados a '5m' en el condicional)."""
    _wire_lectura(monkeypatch)
    monkeypatch.setattr(b, "ANALISIS_ANCHOR_TF", "15m")
    out = b.cmd_lectura(None, "SOL")
    idx_5m = out.index("[INTRADIA 5m]")
    idx_15m = out.index("[SCALPING 15m]")
    block_5m = out[idx_5m:idx_15m]
    block_15m = out[idx_15m:]
    assert "Entry:" not in block_5m
    assert "Entry:" in block_15m


# ============================================================
# build_analisis_context / cmd_analisis_vip: threading de pair
# ============================================================
def _wire_context(monkeypatch, pair_ccy):
    calls = []

    def fake_fetch(exchange, symbol, tf_id, limit=200):
        calls.append((symbol, tf_id))
        return _synth_df(seed=42)

    monkeypatch.setattr(b, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(b, "QTE_AVAILABLE", False)  # aisla: sin QTE ni battle plan
    return calls


def test_build_analisis_context_hila_symbol_y_pair(monkeypatch):
    calls = _wire_context(monkeypatch, "ETH")
    ctx = b.build_analisis_context(None, "ETH")
    assert ctx is not None
    assert ctx["pair"] == "ETH/USDT"
    assert ctx["ccy"] == "ETH"
    assert ctx["symbol"] == b.SYMBOL_ETH
    assert all(sym == b.SYMBOL_ETH for sym, _tf in calls)


def test_build_analisis_context_default_sol(monkeypatch):
    calls = _wire_context(monkeypatch, "SOL")
    ctx = b.build_analisis_context(None)
    assert ctx["pair"] == "SOL/USDT"
    assert ctx["ccy"] == "SOL"
    assert all(sym == b.SYMBOL for sym, _tf in calls)


def test_cmd_analisis_vip_pasa_pair_al_formato(monkeypatch):
    """El pair del contexto llega a vip_format.build_vip_analisis (antes,
    el par mostrado siempre era la constante PAIR = SOL, sin importar que
    se estuviera analizando BTC/ETH)."""
    _wire_context(monkeypatch, "BTC")
    ctx = b.build_analisis_context(None, "BTC")
    captured = {}

    def fake_build_vip_analisis(**kwargs):
        captured.update(kwargs)
        return "OK"

    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b.vip_format, "build_vip_analisis", fake_build_vip_analisis)
    out = b.cmd_analisis_vip(None, ctx=ctx)
    assert out == "OK"
    assert captured.get("pair") == "BTC/USDT"
