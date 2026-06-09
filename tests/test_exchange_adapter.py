# -*- coding: utf-8 -*-
"""
exchange_adapter: bróker ccxt (paper|live). ccxt se mockea con un doble que
registra llamadas -> sin red, determinista. Verifica que el contrato es idéntico
al PaperBroker y que en paper JAMÁS se manda una orden.
"""
import inspect

import pytest

import execution as ex
import exchange_adapter as xa


# --------------------------------------------------------------------------
# doble de ccxt: registra create_order y sirve precios fijos
# --------------------------------------------------------------------------
class FakeExchange:
    def __init__(self, last=100.0, bar=None):
        self._last = last
        self._bar = bar or [1700000000000, 100.0, 103.5, 98.5, 101.0, 12.0]
        self.orders = []

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        o = {"id": f"ord-{len(self.orders)+1}", "symbol": symbol, "type": type,
             "side": side, "amount": amount, "price": price, "params": params or {}}
        self.orders.append(o)
        return o

    def fetch_ticker(self, symbol):
        return {"last": self._last}

    def fetch_ohlcv(self, symbol, timeframe, limit=1):
        return [self._bar]


def _acct(eq=10_000.0):
    return ex.Account("A1", eq)


def _sig(direction=ex.LONG, entry=100.0, stop=99.0, tp=103.0, symbol="BTC/USDT:USDT"):
    return {"symbol": symbol, "direction": direction, "entry": entry, "stop": stop, "tp": tp}


# --------------------------------------------------------------------------
# contrato: misma interfaz que PaperBroker
# --------------------------------------------------------------------------
def test_same_interface_as_paperbroker():
    for name in ("open", "resolve", "resolve_on_bar"):
        assert hasattr(xa.CcxtBroker, name)
        sig_paper = inspect.signature(getattr(ex.PaperBroker, name))
        sig_ccxt = inspect.signature(getattr(xa.CcxtBroker, name))
        assert list(sig_paper.parameters) == list(sig_ccxt.parameters), name


def test_rejects_bad_mode():
    with pytest.raises(ValueError):
        xa.CcxtBroker(mode="demo")


# --------------------------------------------------------------------------
# PAPER: precios reales, sizing/PnL como el paper, CERO órdenes
# --------------------------------------------------------------------------
def test_paper_never_sends_orders():
    fx = FakeExchange()
    b = xa.CcxtBroker(mode="paper", exchange=fx)
    a = _acct()
    pos = b.open(a, _sig(), 0.0025)
    b.resolve(a, pos, 103.0, "tp")
    assert fx.orders == []                       # jamás create_order en paper


def test_paper_sizing_matches_paperbroker():
    a1, a2 = _acct(), _acct()
    pb = ex.PaperBroker()
    cb = xa.CcxtBroker(mode="paper", exchange=FakeExchange())
    p1 = pb.open(a1, _sig(), 0.0025)
    p2 = cb.open(a2, _sig(), 0.0025)
    assert p2.size == pytest.approx(p1.size)     # mismo sizing exacto


def test_paper_pnl_and_ledger():
    fx = FakeExchange()
    b = xa.CcxtBroker(mode="paper", exchange=fx)
    a = _acct()
    pos = b.open(a, _sig(), 0.0025)
    out = b.resolve(a, pos, 103.0, "tp")
    assert set(out) == {"pnl_quote", "pnl_r", "reason"}
    assert out["pnl_r"] == pytest.approx(3.0)    # (103-100)/(100-99) = 3R
    assert b.ledger.verify()
    events = [r["payload"]["event"] for r in b.ledger.records]
    assert events == ["OPEN", "CLOSE"]


def test_paper_reads_real_prices():
    b = xa.CcxtBroker(mode="paper", exchange=FakeExchange(last=123.45))
    assert b.last_price("BTC/USDT:USDT") == pytest.approx(123.45)
    bar = b.last_bar("BTC/USDT:USDT", "5m")
    assert bar["high"] == 103.5 and bar["low"] == 98.5


# --------------------------------------------------------------------------
# LIVE: orden con SL/TP adjuntos, reduceOnly al cerrar
# --------------------------------------------------------------------------
def test_live_open_sends_order_with_attached_sltp():
    fx = FakeExchange()
    b = xa.CcxtBroker(mode="live", exchange=fx)
    a = _acct()
    pos = b.open(a, _sig(direction=ex.LONG), 0.0025)
    assert len(fx.orders) == 1
    o = fx.orders[0]
    assert o["side"] == "buy"
    assert o["params"]["stopLoss"]["triggerPrice"] == 99.0
    assert o["params"]["takeProfit"]["triggerPrice"] == 103.0
    assert o["amount"] == pytest.approx(pos.size)
    # el ledger enlaza la posición con la orden real
    evs = [r["payload"]["event"] for r in b.ledger.records]
    assert evs == ["OPEN", "LIVE_ORDER"]
    assert b.ledger.records[-1]["payload"]["order_id"] == o["id"]


def test_live_short_side():
    fx = FakeExchange()
    b = xa.CcxtBroker(mode="live", exchange=fx)
    b.open(_acct(), _sig(direction=ex.SHORT, entry=100.0, stop=101.0, tp=97.0), 0.0025)
    assert fx.orders[0]["side"] == "sell"


def test_live_resolve_sends_reduce_only_close():
    fx = FakeExchange()
    b = xa.CcxtBroker(mode="live", exchange=fx)
    a = _acct()
    pos = b.open(a, _sig(), 0.0025)
    b.resolve(a, pos, 103.0, "tp")
    close = fx.orders[-1]
    assert close["side"] == "sell"               # contrario al LONG
    assert close["params"].get("reduceOnly") is True


def test_live_zero_risk_raises_before_order():
    fx = FakeExchange()
    b = xa.CcxtBroker(mode="live", exchange=fx)
    with pytest.raises(ValueError):
        b.open(_acct(), _sig(entry=100.0, stop=100.0), 0.0025)
    assert fx.orders == []                        # no manda orden si el riesgo es nulo


# --------------------------------------------------------------------------
# el reconciler audita el ledger del adapter sin cambios
# --------------------------------------------------------------------------
def test_ledger_feeds_reconciler():
    import reconciler as rc
    fx = FakeExchange()
    b = xa.CcxtBroker(mode="paper", exchange=fx)
    a = _acct()
    for _ in range(6):
        pos = b.open(a, _sig(), 0.0025)
        b.resolve(a, pos, 103.0, "tp")
    assert rc.extract_closed_r(b.ledger) == pytest.approx([3.0] * 6)
