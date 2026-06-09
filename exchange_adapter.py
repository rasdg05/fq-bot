# -*- coding: utf-8 -*-
"""
================================================================================
  EXCHANGE ADAPTER - bróker ccxt (paper|live) con la MISMA interfaz que PaperBroker
  by RasDG_Sol + Claude

  El puente al venue real, escrito para que el driver no distinga paper de live.
  Implementa open / resolve / resolve_on_bar igual que execution.PaperBroker y
  sella en el MISMO HashLedger, así que el reconciliador del paso 1 lo audita sin
  cambios. La única diferencia es si se manda una orden real o no:

    mode="paper" : lee precios REALES del exchange (fetch_ticker/fetch_ohlcv) pero
                   NUNCA llama create_order. Sizing y PnL idénticos al PaperBroker
                   -> track record forward contra el venue real, 0% capital.
    mode="live"  : abre en una SUB-CUENTA (OKX por defecto) con SL/TP ADJUNTOS en
                   una sola create_order (OCO atado a la entrada). Cierre manual =
                   orden reduceOnly. Mismo venue que la data del CI -> el reconciler
                   mide drift del edge, no ruido entre exchanges.

  Sin claves hardcodeadas: make_exchange_from_env() lee OKX_API_KEY/SECRET/
  PASSWORD del entorno. ccxt se inyecta (exchange=...) para testear sin red.
  Reusa PaperBroker (sizing, ledger, PnL) por composición: cero lógica duplicada.
================================================================================
"""
import os
import logging

from execution import PaperBroker, HashLedger, LONG, SHORT

log = logging.getLogger("exchange_adapter")

PAPER, LIVE = "paper", "live"


def make_exchange_from_env(exchange_id=None, market_type=None):
    """Construye el cliente ccxt desde el entorno. Las lecturas públicas
    (precios) funcionan sin claves; las órdenes live exigen las tres credenciales
    de la sub-cuenta. Import perezoso de ccxt para no exigirlo en tests."""
    import ccxt
    ex_id = (exchange_id or os.getenv("FQ_EXEC_EXCHANGE", "okx")).lower()
    mkt = market_type or os.getenv("FQ_EXEC_MARKET_TYPE", "swap")
    klass = getattr(ccxt, ex_id)
    return klass({
        "apiKey": os.getenv("OKX_API_KEY"),
        "secret": os.getenv("OKX_SECRET"),
        "password": os.getenv("OKX_PASSWORD"),   # OKX exige passphrase
        "enableRateLimit": True,
        "options": {"defaultType": mkt},         # swap = perpetuo lineal USDT
    })


class CcxtBroker:
    """Bróker contra exchange real con interfaz idéntica a PaperBroker. En paper
    no manda órdenes; en live opera la sub-cuenta con SL/TP adjuntos. El registro
    (Position, ledger, equity, PnL) lo lleva un PaperBroker interno: una sola
    fuente de verdad para la contabilidad, mismo sello para el reconciliador."""

    def __init__(self, mode=PAPER, exchange=None, ledger=None,
                 market_type="swap", subaccount=None, entry_type="market"):
        if mode not in (PAPER, LIVE):
            raise ValueError(f"mode inválido: {mode!r} (usa 'paper'|'live')")
        self.mode = mode
        self.market_type = market_type
        self.subaccount = subaccount or os.getenv("OKX_SUBACCOUNT")
        self.entry_type = entry_type
        self._exchange = exchange                 # inyectable (mock en tests)
        self._paper = PaperBroker(ledger or HashLedger())
        self.ledger = self._paper.ledger          # mismo ledger -> reconciler
        self._live_orders = {}                    # pid -> orden ccxt de entrada

    # ---- exchange perezoso (se construye solo si hace falta) ----
    @property
    def exchange(self):
        if self._exchange is None:
            self._exchange = make_exchange_from_env(market_type=self.market_type)
        return self._exchange

    # ---- precios reales (sirven a paper y al driver) ----
    def last_price(self, symbol):
        return float(self.exchange.fetch_ticker(symbol)["last"])

    def last_bar(self, symbol, timeframe="5m"):
        o = self.exchange.fetch_ohlcv(symbol, timeframe, limit=1)
        ts, op, hi, lo, cl, vol = o[-1]
        return {"ts": ts, "open": op, "high": hi, "low": lo, "close": cl, "volume": vol}

    # ---- apertura ----
    def _place_live_order(self, signal, size):
        """Orden de entrada en la sub-cuenta con SL/TP ADJUNTOS (OCO atado): si
        entra, el stop y el objetivo ya existen en el mismo envío (atómico)."""
        side = "buy" if int(signal["direction"]) == LONG else "sell"
        params = {
            "stopLoss": {"triggerPrice": float(signal["stop"]), "type": "market"},
            "takeProfit": {"triggerPrice": float(signal["tp"]), "type": "market"},
        }
        if self.subaccount:
            params["subaccount"] = self.subaccount
        return self.exchange.create_order(signal["symbol"], self.entry_type, side,
                                          size, None, params)

    def open(self, account, signal, risk_frac, ts=None):
        """Misma firma/retorno que PaperBroker.open. En live manda la orden ANTES
        de sellar (una orden rechazada no deja posición fantasma en el ledger)."""
        if self.mode == LIVE:
            entry, stop = float(signal["entry"]), float(signal["stop"])
            rdist = abs(entry - stop)
            if rdist <= 0:
                raise ValueError("riesgo nulo (entry == stop)")
            size = account.equity * risk_frac / rdist
            order = self._place_live_order(signal, size)
            pos = self._paper.open(account, signal, risk_frac, ts=ts)
            self._live_orders[pos.pid] = order
            self.ledger.append({"event": "LIVE_ORDER", "ts": ts, "pid": pos.pid,
                                "order_id": order.get("id"), "symbol": pos.symbol,
                                "subaccount": self.subaccount})
            return pos
        # paper: sin red para ejecutar, solo registro contra precios reales.
        return self._paper.open(account, signal, risk_frac, ts=ts)

    # ---- cierre ----
    def _close_live(self, pos):
        """Cierre manual en live: orden reduceOnly que aplana la posición (los
        SL/TP adjuntos los gestiona el exchange como OCO)."""
        side = "sell" if pos.direction == LONG else "buy"
        return self.exchange.create_order(pos.symbol, "market", side, pos.size,
                                          None, {"reduceOnly": True})

    def resolve(self, account, pos, exit_price, reason="manual", ts=None):
        """Cierre explícito. En live aplana en el exchange; en ambos modos el PnL
        y el sello CLOSE los lleva el PaperBroker (mismo formato de retorno)."""
        if self.mode == LIVE:
            self._close_live(pos)
            self._live_orders.pop(pos.pid, None)
        return self._paper.resolve(account, pos, exit_price, reason=reason, ts=ts)

    def resolve_on_bar(self, account, pos, high, low, pessimistic=True, ts=None):
        """Resuelve contra una vela. En live, el SL/TP adjunto ya cerró en el
        exchange: aquí solo se registra el desenlace para mantener el libro y el
        ledger en sync (sin mandar órdenes). Reusa la lógica pesimista del paper."""
        return self._paper.resolve_on_bar(account, pos, high, low,
                                          pessimistic=pessimistic, ts=ts)
