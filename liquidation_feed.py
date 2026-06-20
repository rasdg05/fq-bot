# -*- coding: utf-8 -*-
"""
================================================================================
  liquidation_feed — feed de LIQUIDACIONES (Binance USDT-M, stream gratis
  !forceOrder@arr) -> combustible direccional para volume_liquidation_trigger.
  by RasDG_Sol + Claude
================================================================================
Binance es el venue de perps mas profundo: sus cascadas de liquidacion mueven el
precio de SOL/BTC/ETH en TODO el mercado, asi que sirven como proxy aunque el bot
referencie OKX. El stream publico !forceOrder@arr no requiere API key.

DISENO (seguro sobre el bot vivo):
  · OPT-IN total: FQ_LIQ_FEED_ENABLED (default 0). Sin prender -> snapshot() devuelve
    fresh=False y el trigger degrada a SOLO volumen. Prenderlo no puede romper nada.
  · Lazy-start: el hilo websocket arranca en el primer snapshot() (no toca el startup
    del monolito). Daemon, con reconnect y backoff; TODA excepcion se traga (nunca
    propaga al bot). Si falta websocket-client -> se loguea una vez y queda off.
  · Buffer PURO y testeable (ventana rodante por simbolo, intensidad + skew). El
    runner websocket es delgado y no se testea aqui (necesita red); el buffer/parser
    si.

side de Binance: una forceOrder 'SELL' = se liquido un LONG (lo venden); 'BUY' = se
liquido un SHORT (lo recompran). skew>0 = mas SHORTS liquidados (squeeze al alza ->
fuel LONG), coherente con la tesis 'momentum' del trigger.
================================================================================
"""
import os
import json
import time
import logging
import threading
from collections import deque

log = logging.getLogger("liquidation_feed")


def _flag(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


ENABLED = _flag("FQ_LIQ_FEED_ENABLED", "0")
WINDOW_SEC = float(os.environ.get("FQ_LIQ_WINDOW_SEC", "300"))          # ventana rodante
INTENSITY_REF_USD = float(os.environ.get("FQ_LIQ_INTENSITY_REF_USD", "750000"))
PRIMARY_SYMBOL = os.environ.get("FQ_LIQ_PRIMARY_SYMBOL", "SOLUSDT").upper()
TRACKED = set(s.strip().upper() for s in
              os.environ.get("FQ_LIQ_SYMBOLS", "SOLUSDT,BTCUSDT,ETHUSDT").split(",")
              if s.strip())
WS_URL = os.environ.get("FQ_LIQ_WS_URL", "wss://fstream.binance.com/ws/!forceOrder@arr")


def _binance_symbol(sym):
    """Normaliza cualquier formato a 'SOLUSDT': OKX 'SOL-USDT-SWAP', ccxt
    'SOL/USDT:USDT' o 'SOL/USDT', binance 'SOLUSDT'. None/vacio -> None."""
    if not sym:
        return None
    s = str(sym).upper().split(":")[0]               # 'SOL/USDT:USDT' -> 'SOL/USDT'
    s = s.replace("-SWAP", "").replace("-PERP", "")
    s = s.replace("/", "").replace("-", "")
    return s or None


def parse_force_order(data):
    """Binance forceOrder -> (binance_symbol, side, usd) o None. side: 'long' si se
    liquido un LONG (orden SELL), 'short' si un SHORT (orden BUY). usd = ap*q."""
    o = data.get("o") if isinstance(data, dict) else None
    if not o:
        return None
    try:
        sym = str(o.get("s", "")).upper()
        s = str(o.get("S", "")).upper()
        price = float(o.get("ap") or o.get("p") or 0.0)
        qty = float(o.get("q") or o.get("z") or 0.0)
        usd = price * qty
        if not sym or usd <= 0 or s not in ("SELL", "BUY"):
            return None
        return sym, ("long" if s == "SELL" else "short"), usd
    except Exception:
        return None


class LiquidationBuffer:
    """Ventana rodante thread-safe de liquidaciones por simbolo. snapshot() devuelve
    intensity [0,1] (total/ref, capado) y skew [-1,1] (+ = mas SHORT liquidado)."""

    def __init__(self, window_sec=300.0, intensity_ref_usd=750000.0):
        self.window_ms = int(window_sec * 1000)
        self.ref = float(intensity_ref_usd)
        self._events = deque()        # (ts_ms, symbol, side, usd)
        self._lock = threading.Lock()
        self._last_ms = 0

    def ingest(self, ts_ms, symbol, side, usd):
        with self._lock:
            self._events.append((int(ts_ms), symbol, side, float(usd)))
            self._last_ms = max(self._last_ms, int(ts_ms))
            self._prune(int(ts_ms))

    def _prune(self, now_ms):
        cutoff = now_ms - self.window_ms
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def snapshot(self, symbol, now_ms):
        with self._lock:
            self._prune(int(now_ms))
            long_usd = short_usd = 0.0
            for _ts, sym, side, usd in self._events:
                if sym != symbol:
                    continue
                if side == "long":
                    long_usd += usd
                else:
                    short_usd += usd
            total = long_usd + short_usd
            intensity = min(1.0, total / self.ref) if self.ref > 0 else 0.0
            skew = ((short_usd - long_usd) / total) if total > 0 else 0.0
            return {"long_usd": long_usd, "short_usd": short_usd,
                    "intensity": intensity, "skew": skew, "fresh": total > 0}


_BUFFER = LiquidationBuffer(WINDOW_SEC, INTENSITY_REF_USD)
_started = False
_start_lock = threading.Lock()
_STOP = threading.Event()


def _now_ms():
    return int(time.time() * 1000)


def _run_feed():
    """Daemon: consume !forceOrder@arr y alimenta el buffer. Reconnecta con backoff.
    TODO excepcion se traga: el feed jamas tumba el bot (peor caso: sin datos ->
    el trigger degrada a volumen)."""
    import websocket  # websocket-client (lazy: solo si el feed arranca)

    def on_message(_ws, message):
        try:
            data = json.loads(message)
            events = data if isinstance(data, list) else [data]
            for ev in events:
                parsed = parse_force_order(ev)
                if parsed and parsed[0] in TRACKED:
                    sym, side, usd = parsed
                    _BUFFER.ingest(_now_ms(), sym, side, usd)
        except Exception:
            pass

    def on_error(_ws, err):
        log.warning("[liq] ws error: %s", str(err)[:120])

    while not _STOP.is_set():
        try:
            ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_error=on_error)
            ws.run_forever(ping_interval=180, ping_timeout=10)
        except Exception as e:
            log.warning("[liq] run_forever crash: %s", str(e)[:120])
        _STOP.wait(5.0)            # backoff de reconexion


def _ensure_started():
    global _started
    if _started:
        return
    with _start_lock:
        if _started:
            return
        try:
            import websocket  # noqa: F401  (falla rapido si falta la lib)
        except Exception:
            log.warning("[liq] websocket-client no instalado -> feed OFF (vol-only)")
            _started = True       # no reintentar
            return
        threading.Thread(target=_run_feed, name="liq-feed", daemon=True).start()
        _started = True
        log.info("[liq] feed Binance forceOrder iniciado (window=%ss, tracked=%s)",
                 WINDOW_SEC, sorted(TRACKED))


def snapshot(symbol=None):
    """Snapshot de liquidaciones para `symbol` (cualquier formato; None -> primary).
    Arranca el feed lazy. Feed off / sin datos -> fresh=False (trigger -> vol-only)."""
    if not ENABLED:
        return {"fresh": False, "intensity": 0.0, "skew": 0.0,
                "long_usd": 0.0, "short_usd": 0.0}
    _ensure_started()
    bsym = _binance_symbol(symbol) or PRIMARY_SYMBOL
    return _BUFFER.snapshot(bsym, _now_ms())
