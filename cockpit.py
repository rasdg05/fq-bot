# -*- coding: utf-8 -*-
"""cockpit — telemetría NO-CRÍTICA del motor para la interfaz "show" (FQ_COCKPIT=1).

Regla de hierro (encargo RasDG 2026-07-03: "que por la interfaz JAMÁS se caiga la
señal"): si el cockpit falla, el motor NI SE ENTERA. Todo va en try/except, todo es
no-op con el flag OFF (default), y el costo con el flag ON es despreciable:
un update de dict por vela + un write atómico THROTTLED (>= cada 2s) de un JSON de
~5-10 KB. La interfaz (tools/cockpit_server.py + cockpit.html) vive en OTRO proceso
(hijo critical=False del launcher): si muere, el bot sigue.

Qué sella por símbolo (lo que el motor "ve" en cada vela): precio + sparkline (últimos
48 closes), cambio % 24h (ticker del venue, decorativo), irreversibilidad KL (el
régimen), funding pctl (cache 1h compartido con el boost), killzone, contadores
fire/vetadas/abiertas. Más un ring de EVENTOS reales (fires/vetos/aperturas/cierres) —
el feed de "pensamientos" del algoritmo.
"""
import json
import logging
import os
import threading
import time

log = logging.getLogger("fq.cockpit")

_ENABLED = os.environ.get("FQ_COCKPIT", "0").strip().lower() in ("1", "true", "yes")
_PATH = os.environ.get("FQ_COCKPIT_PATH") or (
    "/data/cockpit.json" if os.path.isdir("/data") else "data/cockpit.json")
_MIN_WRITE_S = 2.0
_EVENTS_MAX = 60
_SPARK_N = 48

_lock = threading.Lock()
_state = {"boot": time.time(), "symbols": {}, "events": []}
_last_write = [0.0]
_CHG_CACHE = {}


def enabled():
    return _ENABLED


def _is_vip(ccy):
    """¿El símbolo BROADCASTEA a clientes AHORA? Lee la MISMA env que el monolito
    (FQ_<CCY>_VIP_BROADCAST, default on; SOL es el pilar, siempre VIP). Así el
    cockpit distingue producto (VIP) de laboratorio (paper) sin inventar nada."""
    if ccy == "SOL":
        return True
    return os.environ.get("FQ_%s_VIP_BROADCAST" % ccy, "1").strip() not in ("0", "false", "no")


def _chg24h_live(symbol, ttl_s=90):
    """Cambio % en 24h del perp (OKX público: (last-open24h)/open24h). DECORATIVO — solo
    para el show; cacheado y defensivo: un fallo deja el campo ausente y el front cae al
    cambio sobre el sparkline. Mismo venue/patrón que motor_paper.funding_pctl_live."""
    import time as _t
    s = str(symbol or "").upper()                        # 'SOL/USDT' -> 'SOL-USDT-SWAP'
    if s.endswith("-SWAP"):
        inst = s
    else:
        ccy = s.split("/")[0].split(":")[0].replace("-USDT", "").replace("USDT", "")
        inst = "%s-USDT-SWAP" % ccy if ccy else None
    if not inst:
        return None
    c = _CHG_CACHE.get(inst)
    if c and _t.time() - c[0] < ttl_s:
        return c[1]
    try:
        import json
        import urllib.request
        req = urllib.request.Request(
            "https://www.okx.com/api/v5/market/ticker?instId=%s" % inst,
            headers={"User-Agent": "fq-bot"})
        with urllib.request.urlopen(req, timeout=8) as r:
            rows = json.loads(r.read().decode()).get("data") or []
        if not rows:
            return None
        last = float(rows[0]["last"])
        op = float(rows[0]["open24h"])
        if op <= 0:
            return None
        chg = (last - op) / op * 100.0
        _CHG_CACHE[inst] = (_t.time(), chg)
        return chg
    except Exception as e:
        log.debug("[cockpit] chg24h: %s", e)
        return None


def tick(symbol, ts=None, price=None, closes=None, killzone=None,
         counts=None, n_open=None):
    """Una vela procesada. `closes` = cola de closes del primario (lista/array);
    de ahí salen sparkline e irreversibilidad. TODO defensivo; no-op si OFF."""
    if not _ENABLED:
        return
    try:
        sym = str(symbol or "?").split("/")[0].split("-")[0].upper()
        s = {"vip": _is_vip(sym),
             "ts": str(ts) if ts is not None else None,
             "price": float(price) if price is not None else None,
             "killzone": killzone,
             "counts": dict(counts) if counts else {},
             "open": int(n_open) if n_open is not None else 0,
             "updated": time.time()}
        if closes is not None and len(closes) >= 2:
            tail = [float(x) for x in list(closes)[-_SPARK_N:]]
            s["spark"] = tail
            try:                     # KL en ~64 closes: sub-ms; jamás rompe el tick
                import motor_paper
                kl = motor_paper.kl_regime_live([float(x) for x in list(closes)[-64:]])
                if kl is not None:
                    s["irrev"] = round(float(kl["irrev"]), 4)
                    s["kl_low"] = bool(kl["low"])
            except Exception:
                pass
        try:                          # funding: MISMO cache 1h del boost (barato)
            import motor_paper
            rate, pctl = motor_paper.funding_pctl_live(symbol)
            if pctl is not None:
                s["funding_rate"] = round(float(rate), 8)
                s["funding_pctl"] = round(float(pctl), 3)
        except Exception:
            pass
        try:                          # cambio 24h (decorativo, cache 90s, best-effort)
            chg = _chg24h_live(symbol)
            if chg is not None:
                s["chg_24h"] = round(float(chg), 2)
        except Exception:
            pass
        with _lock:
            _state["symbols"][sym] = s
        _write_maybe()
    except Exception as e:
        log.debug("[cockpit] tick: %s", e)


def log_event(symbol, kind, text):
    """Evento REAL del motor (fire/veto/open/close/...) al ring del feed."""
    if not _ENABLED:
        return
    try:
        ev = {"t": time.time(), "sym": str(symbol or "?").split("/")[0].upper(),
              "kind": str(kind), "text": str(text)[:200]}
        with _lock:
            _state["events"].append(ev)
            del _state["events"][:-_EVENTS_MAX]
        _write_maybe(force=True)
    except Exception as e:
        log.debug("[cockpit] event: %s", e)


def _write_maybe(force=False):
    now = time.time()
    if not force and now - _last_write[0] < _MIN_WRITE_S:
        return
    try:
        with _lock:
            payload = json.dumps(_state, default=str)
        d = os.path.dirname(_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(payload)
        os.replace(tmp, _PATH)       # atómico: el server jamás lee un JSON a medias
        _last_write[0] = now
    except Exception as e:
        log.debug("[cockpit] write: %s", e)
