# -*- coding: utf-8 -*-
"""
================================================================================
  MOTOR PAPER (RETRIEVAL_PLAN §6.10.1) — paper del MOTOR BASE + veto + shadow maker
  by RasDG_Sol + Claude
================================================================================
Mide el SUBSET CORRECTO para validar FORWARD el techo +0.10R: senales del MOTOR
BASE (el `fire` de fusion_engine.evaluate_signal) filtradas por el veto de
sesion (default london_open_kz), abiertas en PAPEL (taker = fill REAL) y
midiendo en paralelo si una LIMITE maker en el entry se habria llenado por
PENETRACION — el dato de ADVERSE SELECTION que decide si el techo es capturable.

Por que existe (§6.10.1): el paper ORO (gold_paper) abre senales del gate de la
ficcion NY = POBLACION INCORRECTA para esta espada. Este runtime abre la
poblacion correcta: el motor base + veto, que es donde se midio el +0.10R.

Invariantes:
  · PARALELO al ORO, NO lo reemplaza. 0% real. Ledger durable propio. Default
    OFF (FQ_MOTOR_PAPER). No toca el motor (fusion_engine) ni el ORO.
  · El monolito llama on_bar(fire, ...) con el `fire` CRUDO de evaluate_signal
    (pre QTE / pre veto-VIP) -> misma poblacion que el replay de research.
  · Veto PROPIO (FQ_MOTOR_PAPER_VETO_*), independiente del veto VIP en vivo:
    asi mide el config del techo SIN exigir el veto a clientes (desacopla la
    mision 2 de la 3). "" -> mide el motor base puro.
  · Shadow maker = mismo modelo de fill que el ORO (gold_paper.process_maker_pending).
    El fill-rate es microestructura (nivel->penetracion), no del gate.
================================================================================
"""
import os
import logging

from execution import RiskGovernor, Account, PaperBroker, DurableHashLedger
from live_driver import normalize_fire_report
from bt_engine import CostModel
import gold_paper
import segment_veto

log = logging.getLogger("motor_paper")


def cost_from_exec_mode(mode):
    """Traduce FQ_EXEC_MODE a un CostModel para el PaperBroker (mismo modelo de
    costes que el backtest, bt_engine.CostModel):
      ''/otro -> None  : PnL BRUTO (comportamiento historico; default, reversible).
      'taker' -> neto, ambas piernas taker (fee 5bps + slippage 1bp por lado).
      'maker' -> neto con ENTRADA maker (fee 2bps, SIN slippage de entrada); stop
                 y timeout siguen taker. TP maker solo si FQ_MAKER_TP_EXIT=1.
    El A/B taker-vs-maker sobre el MISMO set de senales mide cuanto edge te
    devuelve no pagar el spread. Funding: commit 2.
    """
    mode = (mode or "").strip().lower()
    if mode not in ("taker", "maker"):
        return None
    maker = (mode == "maker")
    tp_maker = maker and (os.environ.get("FQ_MAKER_TP_EXIT", "0").strip()
                          in ("1", "true", "yes"))
    return CostModel(maker_entry=maker, maker_tp_exit=tp_maker)


class MotorPaperRuntime:
    """Por vela del TF del motor: resolver abiertas -> shadow maker -> si `fire`
    y no vetada, abrir en paper (taker) + armar la limite maker shadow. Track
    record + provenance (killzone/tf) en un ledger durable, segmentable offline
    (tools/motor_paper_stats.py)."""

    def __init__(self, symbol, *, account, governor=None, broker=None,
                 veto=None, tp_key="tp1", notify_fn=None, requested_risk=None,
                 digest_every=0, maker_sim=True, maker_eps_bps=1.0,
                 maker_ttl_bars=6, cost=None):
        self.symbol = symbol
        self.account = account
        self.governor = governor or RiskGovernor()
        self.broker = broker or PaperBroker(cost=cost)
        self.veto = veto if veto is not None else segment_veto.SegmentVeto()
        self.tp_key = tp_key
        self.notify_fn = notify_fn
        self.requested_risk = requested_risk
        self.digest_every = digest_every
        self._ticks = 0
        self.counts = {"fire": 0, "opened": 0, "vetoed": 0}
        self.maker_sim = bool(maker_sim)
        self.maker_eps = float(maker_eps_bps) / 10_000.0
        self.maker_ttl_bars = int(maker_ttl_bars)
        self._maker_pending = []

    @classmethod
    def from_env(cls, symbol, *, notify_fn=None, ledger_path=None):
        """Arma el runtime desde el entorno:
          FQ_MOTOR_PAPER_LEDGER_PATH ledger durable (default /data/motor_paper_<slug>.jsonl)
          FQ_MOTOR_PAPER_EQUITY      equity de la cuenta paper (default 10000)
          FQ_MOTOR_PAPER_VETO_KILLZONES veto propio (default london_open_kz)
          FQ_MOTOR_PAPER_VETO_UTC_BLOCKS / _WEEKDAYS  vetos secundarios (default "")
          FQ_MOTOR_PAPER_TP          nivel del cubo a usar como TP (default tp1)
          FQ_MOTOR_PAPER_MAKER_SIM   shadow maker (default 1: es el punto del track)
          FQ_GOLD_MAKER_EPS_BPS / _TTL_BARS  mismo modelo de fill que el ORO
          FQ_MOTOR_PAPER_DIGEST_EVERY (cae a FQ_GOLD_DIGEST_EVERY) digest admin

        ledger_path: override explícito del ledger. CRÍTICO para correr DOS
        símbolos en paralelo (SOL + BTC): sin esto ambos heredarían el MISMO
        FQ_MOTOR_PAPER_LEDGER_PATH y mezclarían sus trades en un solo archivo.
        El resto de la config (TP/veto/maker/equity) SÍ se comparte a propósito:
        el único variable del experimento debe ser el símbolo.
        """
        slug = symbol.replace("/", "_").replace(":", "_")
        led_path = ledger_path or os.environ.get(
            "FQ_MOTOR_PAPER_LEDGER_PATH", "/data/motor_paper_%s.jsonl" % slug)
        exec_mode = os.environ.get("FQ_EXEC_MODE", "")
        cost = cost_from_exec_mode(exec_mode)
        broker = PaperBroker(ledger=DurableHashLedger.load(led_path), cost=cost)
        equity = float(os.environ.get("FQ_MOTOR_PAPER_EQUITY", "10000"))
        acc = Account("paper-motor-%s" % symbol, equity)
        # Veto PROPIO: default = el config del techo (+0.10R). "" -> motor base.
        veto = segment_veto.parse(
            killzones=os.environ.get("FQ_MOTOR_PAPER_VETO_KILLZONES", "london_open_kz"),
            utc_blocks=os.environ.get("FQ_MOTOR_PAPER_VETO_UTC_BLOCKS", ""),
            weekdays=os.environ.get("FQ_MOTOR_PAPER_VETO_WEEKDAYS", ""))
        tp_key = os.environ.get("FQ_MOTOR_PAPER_TP", "tp1")
        digest_every = int(os.environ.get(
            "FQ_MOTOR_PAPER_DIGEST_EVERY",
            os.environ.get("FQ_GOLD_DIGEST_EVERY", "0")))
        maker_eps = float(os.environ.get("FQ_GOLD_MAKER_EPS_BPS", "1.0"))
        maker_ttl = int(os.environ.get("FQ_GOLD_MAKER_TTL_BARS", "6"))
        maker_sim = os.environ.get("FQ_MOTOR_PAPER_MAKER_SIM", "1").strip() \
            in ("1", "true", "yes")
        log.info("[motor] runtime paper MOTOR BASE activo (%s, veto=%s, "
                 "maker_shadow=%s, exec=%s, ledger=%s)", symbol, veto.describe(),
                 maker_sim, exec_mode.strip() or "bruto", led_path)
        return cls(symbol, account=acc, broker=broker, veto=veto, tp_key=tp_key,
                   notify_fn=notify_fn, digest_every=digest_every,
                   maker_sim=maker_sim, maker_eps_bps=maker_eps,
                   maker_ttl_bars=maker_ttl)

    def _maybe_digest(self):
        if self.digest_every and self._ticks % self.digest_every == 0 \
                and self.notify_fn is not None:
            try:
                self.notify_fn(None, {"digest": dict(self.counts),
                                      "ticks": self._ticks,
                                      "open": len(self.account.open)}, None)
            except Exception as e:
                log.warning("[motor] digest: %s", e)

    def on_bar(self, fire, field, report, df_primary, price, *,
               high=None, low=None, ts=None, tf_id=None):
        """Procesa una vela. `fire` = disparo CRUDO de evaluate_signal. high/low
        resuelven abiertas + shadow maker. Devuelve {fire, opened, resolved}."""
        # 1) resolver abiertas (empate pesimista, = etiquetado de research) +
        #    shadow maker contra ESTA vela (antes de abrir: una limite no se
        #    llena en su vela 0).
        resolved = []
        if high is not None and low is not None:
            for pos in list(self.account.open):
                out = self.broker.resolve_on_bar(self.account, pos, high, low, ts=ts)
                if out is not None:
                    resolved.append({"pid": pos.pid, **out})
            if self.maker_sim and self._maker_pending:
                self._maker_pending = gold_paper.process_maker_pending(
                    self._maker_pending, self.broker.ledger, high, low, ts,
                    eps=self.maker_eps, ttl_bars=self.maker_ttl_bars)
        self._ticks += 1

        # 2) si el motor disparo: aplicar veto propio; si pasa, abrir en paper
        opened = None
        if fire:
            self.counts["fire"] += 1
            kz = getattr(field, "killzone", None)
            why = self.veto.reason(killzone=kz, ts_utc=ts) if self.veto.active else None
            if why:
                self.counts["vetoed"] += 1
                self.broker.ledger.append({
                    "event": "MOTOR_VETOED", "ts": ts, "tf": tf_id,
                    "killzone": kz, "why": why})
            else:
                sig = normalize_fire_report(report, self.symbol, tp_key=self.tp_key)
                if sig is not None:
                    d = self.governor.decide(self.account,
                                             requested_risk=self.requested_risk)
                    if d["approved"]:
                        pos = self.broker.open(self.account, sig, d["risk_frac"], ts=ts)
                        self.counts["opened"] += 1
                        opened = {"pid": pos.pid, "killzone": kz, "tf": tf_id,
                                  "risk_frac": d["risk_frac"], **sig}
                        # provenance: liga el pid con killzone/tf para segmentar
                        # el ledger forward (base vs +veto, por killzone/tf).
                        self.broker.ledger.append({
                            "event": "MOTOR_OPEN_META", "ts": ts, "pid": pos.pid,
                            "tf": tf_id, "killzone": kz})
                        if self.maker_sim:
                            self._maker_pending.append({
                                "pid": pos.pid, "direction": pos.direction,
                                "limit": pos.entry, "waited": 0})
                        if self.notify_fn is not None:
                            try:
                                self.notify_fn(sig, {"killzone": kz, "tf": tf_id}, pos)
                            except Exception as e:
                                log.warning("[motor] notify_fn: %s", e)
                    else:
                        log.info("[motor] fire rechazado por gobernador: %s",
                                 d.get("reason"))
        self._maybe_digest()
        return {"fire": bool(fire), "opened": opened, "resolved": resolved}


def ledger_report(path):
    """Lee el ledger del motor paper y devuelve un dict de stats (cartera +
    fill-rate maker + adverse selection). Reusado por el comando /paper del bot
    y por tools/motor_paper_stats.py. Devuelve None si el ledger no existe.
    DurableHashLedger.load verifica la cadena SHA-256 (LANZA si está rota)."""
    import os
    if not os.path.exists(path):
        return None
    led = DurableHashLedger.load(path)
    recs = [r["payload"] for r in led.records]
    pnl, kz, maker, vetoed = {}, {}, {}, {}
    for p in recs:
        ev, pid = p.get("event"), p.get("pid")
        if ev == "CLOSE":
            pnl[pid] = p.get("pnl_r")
        elif ev == "MOTOR_OPEN_META":
            kz[pid] = p.get("killzone")
        elif ev == "MAKER_FILL":
            maker[pid] = "FILL"
        elif ev == "MAKER_MISS":
            maker[pid] = "MISS"
        elif ev == "MOTOR_VETOED":
            k = p.get("killzone")
            vetoed[k] = vetoed.get(k, 0) + 1
    closed = {pid: r for pid, r in pnl.items() if r is not None}

    def _agg(rs):
        rs = [r for r in rs if r is not None]
        n = len(rs)
        if not n:
            return {"n": 0, "mean": None, "wr": None, "total": 0.0}
        return {"n": n, "mean": sum(rs) / n,
                "wr": sum(1 for r in rs if r > 0) / n, "total": sum(rs)}

    n_fill = sum(1 for v in maker.values() if v == "FILL")
    n_miss = sum(1 for v in maker.values() if v == "MISS")
    return {
        "records": len(recs), "n_open_meta": len(kz), "n_closed": len(closed),
        "n_vetoed": sum(vetoed.values()), "vetoed_by_kz": vetoed,
        "portfolio": _agg(list(closed.values())),
        "fill": _agg([closed[p] for p in closed if maker.get(p) == "FILL"]),
        "miss": _agg([closed[p] for p in closed if maker.get(p) == "MISS"]),
        "n_fill": n_fill, "n_miss": n_miss,
        "fill_rate": (n_fill / (n_fill + n_miss)) if (n_fill + n_miss) else None,
    }


def format_report_telegram(rep):
    """Resumen compacto del ledger motor paper para admin (HTML Telegram)."""
    if rep is None:
        return "📄 <b>Motor paper</b>: sin ledger aún (el archivo no existe)."
    if rep["n_closed"] == 0:
        return ("📄 <b>Motor paper</b>: {r} registros · {o} abiertas · "
                "{v} vetadas — aún SIN cierres. El motor dispara lento "
                "(~1-2/sem); cada fire entra aquí.").format(
                    r=rep["records"], o=rep["n_open_meta"], v=rep["n_vetoed"])
    p = rep["portfolio"]
    out = ["📄 <b>Motor paper (subset correcto §6.10.1)</b>",
           "cartera: n={n} · exp≈{m:+.3f}R GROSS · WR {w:.0f}%".format(
               n=p["n"], m=p["mean"], w=p["wr"] * 100.0)]
    if rep["fill_rate"] is not None:
        f, m = rep["fill"], rep["miss"]
        out.append("fill-rate maker: <b>{r:.0f}%</b> (FILL {nf} / MISS {nm})".format(
            r=rep["fill_rate"] * 100.0, nf=rep["n_fill"], nm=rep["n_miss"]))
        if f["n"] and m["n"]:
            tag = "⚠ adverse selection" if f["mean"] < m["mean"] else "✓ sin adverse sel."
            out.append("FILLED exp≈{ff:+.3f}R vs MISSED {mm:+.3f}R — {t}".format(
                ff=f["mean"], mm=m["mean"], t=tag))
    if rep["n_vetoed"]:
        out.append("vetadas: %d" % rep["n_vetoed"])
    out.append("<i>0% real · meta ≥30-50 fills para decidir (§6.10)</i>")
    return "\n".join(out)
