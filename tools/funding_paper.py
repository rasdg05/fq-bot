#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  FUNDING PAPER — runner FORWARD en PAPEL de la REVERSION de funding (estructural)
  by RasDG_Sol + Claude

  El test CORRECTO de un edge NO-DRIFTING (estructural) es acumular un track
  record FORWARD real: el funding extremo revierte o no, y eso se ve operandolo
  hacia adelante con precios reales, 0% capital. Mientras funding_research.py da
  el read DEFLACTADO sobre la historia que exista (shallow), ESTE runner acumula
  el forward que ningun backtest puede falsear.

  Por poll (mirror de motor_paper.py / gold_paper.py):
    1) FETCH del funding mas reciente del exchange y APPEND al cache parquet
       (funding_oi; solo crece con funding YA LIQUIDADO -> causal). Refresca el
       precio spot/mark del perp.
    2) recomputa fund_zscore sobre el cache (trailing, shift, causal) y EVALUA
       funding_strategy.funding_reversion_signal en la ULTIMA barra.
    3) resuelve la posicion abierta contra el precio (TP/SL, empate pesimista),
       y si la senal cambia de lado: cierra la actual y abre la nueva en PAPEL
       (PaperBroker -> DurableHashLedger que el Reconciler audita).
  Todo CAUSAL: el runner SOLO ve funding realizado; jamas una ventana futura.

  LEDGER DURABLE = el PRODUCTO de la fase (sobrevive restarts). Reconcile hooks
  gated por baseline en R (FQ_FUNDING_PAPER_BASELINE_R), igual que gold/motor.

  --once  : una iteracion (para tests / cron).
  --loop --interval SECS : bucle (para systemd; ver DEPLOY abajo).

  ───────────────────────────────────────────────────────────────────────────
  DEPLOY EN HETZNER (systemd):  (corre en el host CON red; 0% real)

    # 1) bajar el funding mas profundo a cache una vez (Part C):
    cd /opt/fq-bot && /opt/fq-bot/.venv/bin/python -c \
      "import funding_oi as fo; print(fo.format_depth_table( \
       fo.probe_funding_depth('BTC', data_dir='/data')))"

    # 2) /etc/systemd/system/funding-paper-btc.service
    #   [Unit]
    #   Description=FQ funding-reversion paper (BTC, 0%% real)
    #   After=network-online.target
    #   Wants=network-online.target
    #   [Service]
    #   Type=simple
    #   WorkingDirectory=/opt/fq-bot
    #   Environment=FQ_FUNDING_PAPER_LEDGER_PATH=/data/funding_paper_BTC.jsonl
    #   Environment=FQ_FUNDING_PAPER_EQUITY=10000
    #   ExecStart=/opt/fq-bot/.venv/bin/python tools/funding_paper.py \
    #       --exchange okx --funding-base BTC --symbol BTC/USDT:USDT \
    #       --loop --interval 1800
    #   Restart=always
    #   RestartSec=30
    #   [Install]
    #   WantedBy=multi-user.target

    # 3) systemctl daemon-reload && systemctl enable --now funding-paper-btc
    #    journalctl -u funding-paper-btc -f
    #    # lee el track record:  python tools/funding_paper.py --report \
    #    #     --ledger /data/funding_paper_BTC.jsonl
  ───────────────────────────────────────────────────────────────────────────
================================================================================
"""
import argparse
import logging
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution import RiskGovernor, Account, PaperBroker, DurableHashLedger
import reconciler as rc
import funding_oi as fo
import funding_strategy as fs

log = logging.getLogger("funding_paper")

LONG, SHORT, FLAT = 1, -1, 0


class FundingPaperRuntime:
    """Mantiene UNA posicion de reversion de funding en papel y la actualiza por
    poll: resolver contra el precio -> reevaluar la senal -> si cambia de lado,
    cerrar y abrir la nueva. Track record en un ledger durable.

    funding_oi / funding_strategy son puros (inyectados via metodos) -> el runtime
    se testea sin red (fetch_fn mockeable)."""

    def __init__(self, symbol, *, account, broker=None, governor=None,
                 reconciler=None, notify_fn=None, requested_risk=None,
                 z_enter=2.0, z_exit=0.5, z_win=96, stop_r_pct=0.01,
                 target_rr=1.0, reconcile_every=20):
        self.symbol = symbol
        self.account = account
        self.broker = broker or PaperBroker()
        self.governor = governor or RiskGovernor()
        self.reconciler = reconciler
        self.notify_fn = notify_fn
        self.requested_risk = requested_risk
        self.z_enter = float(z_enter)
        self.z_exit = float(z_exit)
        self.z_win = int(z_win)
        self.stop_r_pct = float(stop_r_pct)
        self.target_rr = float(target_rr)
        self.reconcile_every = int(reconcile_every)
        self._ticks = 0
        self.cur_dir = FLAT
        self.cur_pos = None
        self.counts = {"poll": 0, "opened": 0, "closed": 0, "flat": 0}

    @classmethod
    def from_env(cls, symbol, *, ledger_path=None, **overrides):
        """Arma el runtime desde el entorno:
          FQ_FUNDING_PAPER_LEDGER_PATH  ledger durable (default /data/funding_paper_<slug>.jsonl)
          FQ_FUNDING_PAPER_EQUITY       equity paper (default 10000)
          FQ_FUNDING_PAPER_Z_ENTER / _Z_EXIT / _Z_WIN   umbrales de la senal
          FQ_FUNDING_PAPER_STOP_R_PCT / _TARGET_RR      geometria del trade
          FQ_FUNDING_PAPER_BASELINE_R   baseline OOS en R (enciende el reconciler)
        """
        slug = symbol.replace("/", "_").replace(":", "_")
        led_path = ledger_path or os.environ.get(
            "FQ_FUNDING_PAPER_LEDGER_PATH", "/data/funding_paper_%s.jsonl" % slug)
        broker = PaperBroker(ledger=DurableHashLedger.load(led_path))
        equity = float(os.environ.get("FQ_FUNDING_PAPER_EQUITY", "10000"))
        acc = Account("paper-funding-%s" % symbol, equity)

        baseline = os.environ.get("FQ_FUNDING_PAPER_BASELINE_R")
        reconciler = None
        if baseline not in (None, ""):
            try:
                reconciler = rc.Reconciler(broker.ledger, RiskGovernor(),
                                           backtest_expectancy_r=float(baseline))
                log.info("[funding] reconciler activo (baseline=%.3fR)", float(baseline))
            except Exception as e:
                log.warning("[funding] reconciler OFF (baseline malo: %s)", e)
        else:
            log.info("[funding] reconciler OFF: sin baseline en R "
                     "(setea FQ_FUNDING_PAPER_BASELINE_R tras observar el paper)")

        kw = dict(
            z_enter=float(os.environ.get("FQ_FUNDING_PAPER_Z_ENTER", "2.0")),
            z_exit=float(os.environ.get("FQ_FUNDING_PAPER_Z_EXIT", "0.5")),
            z_win=int(os.environ.get("FQ_FUNDING_PAPER_Z_WIN", "96")),
            stop_r_pct=float(os.environ.get("FQ_FUNDING_PAPER_STOP_R_PCT", "0.01")),
            target_rr=float(os.environ.get("FQ_FUNDING_PAPER_TARGET_RR", "1.0")),
        )
        kw.update(overrides)
        return cls(symbol, account=acc, broker=broker, reconciler=reconciler,
                   **kw)

    # ----- evaluacion de la senal (pura, sobre el cache de funding) -----
    def latest_zscore(self, df_funding):
        """fund_zscore de la ULTIMA ventana de funding del cache (causal: shift +
        trailing dentro de funding_oi). Devuelve float o NaN si no hay lectura."""
        if df_funding is None or len(df_funding) == 0:
            return float("nan")
        # df_primary minimo de 1 barra en el ULTIMO timestamp del funding: el
        # merge_asof backward le entrega el ultimo funding YA LIQUIDADO (shift=1).
        last_ts = pd.to_datetime(df_funding["timestamp"]).iloc[-1]
        dfp = pd.DataFrame({"timestamp": [last_ts], "close": [1.0]})
        ff = fo.funding_oi_features(dfp, df_funding, df_oi=None, z_win=self.z_win)
        z = ff["fund_zscore"].to_numpy()
        return float(z[-1]) if len(z) else float("nan")

    def _desired_dir(self, zscore):
        """Direccion deseada con HISTERESIS a partir del z y la posicion actual.
        Identica regla que funding_reversion_signal (un solo paso, con estado)."""
        if not np.isfinite(zscore):
            return self.cur_dir          # sin lectura nueva: mantener (no inventa)
        if zscore >= self.z_enter:
            return SHORT
        if zscore <= -self.z_enter:
            return LONG
        if abs(zscore) <= self.z_exit:
            return FLAT
        return self.cur_dir              # zona intermedia: histeresis

    # ----- resolucion / apertura en papel -----
    def _resolve_open(self, price, high, low, ts):
        """Resuelve la posicion abierta contra la vela/precio (TP/SL pesimista)."""
        resolved = []
        if self.cur_pos is None:
            return resolved
        hi = high if high is not None else price
        lo = low if low is not None else price
        out = self.broker.resolve_on_bar(self.account, self.cur_pos, hi, lo, ts=ts)
        if out is not None:
            resolved.append({"pid": self.cur_pos.pid, **out})
            self.counts["closed"] += 1
            self.cur_pos = None
            self.cur_dir = FLAT
        return resolved

    def _close_at(self, price, ts, reason):
        """Cierra la posicion abierta al precio dado (volteo / salida por senal)."""
        if self.cur_pos is None:
            return None
        out = self.broker.resolve(self.account, self.cur_pos, float(price),
                                  reason=reason, ts=ts)
        self.counts["closed"] += 1
        self.cur_pos = None
        self.cur_dir = FLAT
        return out

    def _open(self, direction, price, ts, zscore):
        """Abre una posicion de reversion en papel (stop/target en R sobre price)."""
        entry = float(price)
        if not np.isfinite(entry) or entry <= 0:
            log.warning("[funding] precio invalido (%s); no abre", price)
            return None
        risk = entry * self.stop_r_pct
        stop = entry - direction * risk
        tp = entry + direction * risk * self.target_rr
        sig = {"symbol": self.symbol, "direction": int(direction),
               "entry": entry, "stop": float(stop), "tp": float(tp)}
        d = self.governor.decide(self.account, requested_risk=self.requested_risk)
        if not d["approved"]:
            log.info("[funding] apertura rechazada por gobernador: %s", d["reason"])
            return None
        pos = self.broker.open(self.account, sig, d["risk_frac"], ts=ts)
        # provenance: liga el pid con el z que disparo la entrada (auditable).
        self.broker.ledger.append({
            "event": "FUNDING_OPEN_META", "ts": str(ts), "pid": pos.pid,
            "direction": int(direction), "fund_zscore": float(zscore),
            "z_enter": self.z_enter, "z_exit": self.z_exit})
        self.cur_pos = pos
        self.cur_dir = int(direction)
        self.counts["opened"] += 1
        if self.notify_fn is not None:
            try:
                self.notify_fn(sig, {"fund_zscore": zscore}, pos)
            except Exception as e:
                log.warning("[funding] notify_fn: %s", e)
        return pos

    def poll(self, df_funding, price, *, high=None, low=None, ts=None):
        """UNA iteracion: resolver -> reconciliar -> reevaluar senal -> ajustar
        posicion. df_funding = cache YA actualizado (causal). Devuelve un dict de
        lo que paso (para tests / logging)."""
        self.counts["poll"] += 1
        self._ticks += 1
        ts = ts if ts is not None else (
            pd.to_datetime(df_funding["timestamp"]).iloc[-1]
            if df_funding is not None and len(df_funding) else None)

        # 1) resolver la abierta contra el precio (TP/SL pesimista)
        resolved = self._resolve_open(price, high, low, ts)

        # 2) reconciliar periodicamente (kill-switch si la viva diverge del OOS)
        if self.reconciler is not None and self._ticks % self.reconcile_every == 0:
            try:
                self.reconciler.check(accounts=[self.account])
            except Exception as e:
                log.warning("[funding] reconciler.check: %s", e)

        # 3) reevaluar la senal en la ultima ventana de funding
        z = self.latest_zscore(df_funding)
        want = self._desired_dir(z)

        opened = None
        if want != self.cur_dir:
            # cambio de estado: cerrar lo abierto (si lo hay) al precio y, si la
            # nueva direccion no es FLAT, abrir.
            if self.cur_pos is not None:
                self._close_at(price, ts, reason="signal_flip")
            if want != FLAT:
                pos = self._open(want, price, ts, z)
                if pos is not None:
                    opened = {"pid": pos.pid, "direction": want, "fund_zscore": z}
            else:
                self.counts["flat"] += 1
        return {"fund_zscore": z, "desired_dir": want, "cur_dir": self.cur_dir,
                "opened": opened, "resolved": resolved, "price": float(price)}


# ============================================================
# FETCH del funding mas reciente -> APPEND al cache (causal; solo crece)
# ============================================================
def refresh_funding_cache(exchange, symbol, data_dir, exchange_name, *,
                          recent_limit=200, now_ms=None):
    """Trae el funding mas reciente y lo MERGEA al cache parquet (solo añade
    ventanas YA LIQUIDADAS). Reusa _funding_frame de funding_oi para el esquema.
    Devuelve el DataFrame del cache COMPLETO (ascendente). Si la red falla, lanza
    -> el caller (loop) lo captura y reintenta en el siguiente poll."""
    path = fo.funding_path(data_dir, exchange_name, symbol)
    existing = pd.read_parquet(path) if os.path.exists(path) else None
    batch = exchange.fetch_funding_rate_history(symbol, since=None,
                                                limit=recent_limit, params={})
    rows = []
    for item in (batch or []):
        ts = item.get("timestamp")
        if ts is None:
            continue
        rows.append((int(ts), fo._to_float(item.get("fundingRate"))))
    floor = 0 if now_ms is None else int(now_ms) - 365 * 4 * 86_400_000
    fresh = fo._funding_frame(rows, floor)
    if existing is not None and len(existing):
        merged = pd.concat([existing, fresh], ignore_index=True)
    else:
        merged = fresh
    merged = (merged.dropna(subset=["timestamp"])
              .drop_duplicates(subset="timestamp")
              .sort_values("timestamp").reset_index(drop=True))
    fo._to_parquet(merged, path)
    return merged


def latest_price(exchange, symbol):
    """Precio mark/last del perp para abrir/resolver en papel. Devuelve float o
    None (el caller decide)."""
    try:
        t = exchange.fetch_ticker(symbol)
        for k in ("last", "mark", "close", "info"):
            v = t.get(k) if isinstance(t, dict) else None
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
        return float(t["last"]) if t and t.get("last") else None
    except Exception as e:
        log.warning("[funding] fetch_ticker(%s): %s", symbol, e)
        return None


def ledger_report(path):
    """Lee el ledger del funding paper y resume el track record (cartera + por
    direccion). None si no existe. Verifica la cadena SHA-256 (lanza si rota)."""
    if not os.path.exists(path):
        return None
    led = DurableHashLedger.load(path)
    recs = [r["payload"] for r in led.records]
    pnl, meta = {}, {}
    for p in recs:
        ev, pid = p.get("event"), p.get("pid")
        if ev == "CLOSE":
            pnl[pid] = p.get("pnl_r")
        elif ev == "FUNDING_OPEN_META":
            meta[pid] = p.get("direction")
    closed = {pid: r for pid, r in pnl.items() if r is not None}

    def _agg(rs):
        rs = [r for r in rs if r is not None]
        n = len(rs)
        if not n:
            return {"n": 0, "mean": None, "wr": None, "total": 0.0}
        return {"n": n, "mean": sum(rs) / n,
                "wr": sum(1 for r in rs if r > 0) / n, "total": sum(rs)}

    longs = [closed[p] for p in closed if meta.get(p) == LONG]
    shorts = [closed[p] for p in closed if meta.get(p) == SHORT]
    return {"records": len(recs), "n_closed": len(closed),
            "portfolio": _agg(list(closed.values())),
            "long": _agg(longs), "short": _agg(shorts)}


def _print_report(path):
    rep = ledger_report(path)
    if rep is None:
        print(f"[funding-paper] sin ledger en {path} (aun no ha corrido).")
        return
    p = rep["portfolio"]
    print(f"[funding-paper] {path}")
    print(f"  registros={rep['records']} cierres={rep['n_closed']}")
    if p["n"]:
        print(f"  cartera: n={p['n']} exp={p['mean']:+.4f}R WR={p['wr']*100:.0f}% "
              f"total={p['total']:+.2f}R")
        for side, lbl in (("long", "LONG (fade -z)"), ("short", "SHORT (fade +z)")):
            s = rep[side]
            if s["n"]:
                print(f"    {lbl}: n={s['n']} exp={s['mean']:+.4f}R WR={s['wr']*100:.0f}%")
    else:
        print("  aun SIN cierres (la reversion entra lento; cada flanco entra aqui).")


def _build_exchange(args):
    import bt_data
    return bt_data.make_exchange(args.exchange, "swap")


def _one_iteration(rt, exchange, args):
    """Refresca el cache, trae el precio y corre un poll. Devuelve el dict del poll
    o None si el precio no estuvo disponible."""
    df = refresh_funding_cache(
        exchange, args.funding_symbol, args.data_dir, args.exchange,
        recent_limit=args.recent_limit)
    price = latest_price(exchange, args.symbol)
    if price is None:
        log.warning("[funding] sin precio este poll; salto (reintenta luego)")
        return None
    out = rt.poll(df, price)
    log.info("[funding] z=%.3f desired=%+d cur=%+d price=%.2f opened=%s resolved=%d",
             out["fund_zscore"] if np.isfinite(out["fund_zscore"]) else float("nan"),
             out["desired_dir"], out["cur_dir"], out["price"],
             bool(out["opened"]), len(out["resolved"]))
    return out


def main():
    p = argparse.ArgumentParser(
        description="Runner forward en PAPEL de la reversion de funding (0% real).")
    p.add_argument("--exchange", default="okx",
                   help="exchange ccxt del funding + precio (swap). Default okx")
    p.add_argument("--symbol", default="BTC/USDT:USDT",
                   help="simbolo del perp para precio/ordenes (formato ccxt)")
    p.add_argument("--funding-base", default=None,
                   help="base del perp de funding (BTC/SOL/ETH). Default: de --symbol")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--ledger", default=None,
                   help="ruta del ledger durable (override de FQ_FUNDING_PAPER_LEDGER_PATH)")
    p.add_argument("--recent-limit", type=int, default=200,
                   help="ventanas de funding a traer por poll (se mergean al cache)")
    p.add_argument("--once", action="store_true",
                   help="una sola iteracion (para tests / cron) y termina")
    p.add_argument("--loop", action="store_true",
                   help="bucle continuo (para systemd)")
    p.add_argument("--interval", type=int, default=1800,
                   help="segundos entre polls en --loop (default 1800 = 30 min)")
    p.add_argument("--report", action="store_true",
                   help="solo imprime el track record del ledger y termina")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    base = args.funding_base or args.symbol.upper().replace("-", "/").split(":")[0].split("/")[0]
    args.funding_symbol = fo.perp_symbol_for(args.exchange, base)

    led_path = args.ledger or os.environ.get(
        "FQ_FUNDING_PAPER_LEDGER_PATH",
        "/data/funding_paper_%s.jsonl" % args.symbol.replace("/", "_").replace(":", "_"))

    if args.report:
        _print_report(led_path)
        return

    rt = FundingPaperRuntime.from_env(args.symbol, ledger_path=led_path)
    exchange = _build_exchange(args)
    log.info("[funding] runtime paper REVERSION activo (%s, funding=%s, z_enter=%.2f "
             "z_exit=%.2f, ledger=%s)", args.symbol, args.funding_symbol,
             rt.z_enter, rt.z_exit, led_path)

    if args.loop:
        log.info("[funding] loop cada %ds (Ctrl-C / systemd stop para salir)",
                 args.interval)
        while True:
            try:
                _one_iteration(rt, exchange, args)
            except Exception as e:
                log.warning("[funding] poll fallo (%s: %s); reintento en %ds",
                            type(e).__name__, str(e)[:160], args.interval)
            time.sleep(max(1, int(args.interval)))
    else:
        # default: --once (una iteracion). Sin --loop no entra en bucle.
        _one_iteration(rt, exchange, args)
        _print_report(led_path)


if __name__ == "__main__":
    main()
