# -*- coding: utf-8 -*-
"""
================================================================================
  GOLD PAPER - runtime en PAPEL del gate ORO (admin-only, 0% real)
  by RasDG_Sol + Claude

  El monolito invoca esto por vela cuando FQ_GOLD_LIVE=1 (default OFF). Cierra el
  lazo: clasifica el estado con el gate de retrieval (GoldLiveEngine), y si es ORO
  abre en PAPEL (PaperBroker -> sella en un HashLedger DURABLE que el Reconciler
  audita), resuelve lo abierto contra la vela y avisa al admin (notify_fn
  inyectable; en prod = broadcast_to_subscribers(..., tiers=["admin"])). SIN VIP.

  Endurecido (P0):
    · LEDGER DURABLE: el track record forward se persiste en disco (sobrevive a
      restarts de Railway). Es el PRODUCTO de la fase.
    · RECONCILER AUTO (gated): si hay baseline en unidades de TRADE
      (FQ_GOLD_BASELINE_R o meta.json), arma el Reconciler -> kill-switch si la
      viva diverge del OOS. Gated a proposito: el forward-label del research NO
      esta en las mismas unidades que el trade TP1; sin baseline correcto, no se
      reconcilia (mejor que un kill-switch espurio).
    · TELEMETRIA: chequeo de cobertura de features al primer bar (caza drift de
      esquema del vector) + digest periodico ORO/BASE/ABSTAIN al admin.
================================================================================
"""
import os
import logging

from execution import RiskGovernor, Account, PaperBroker, DurableHashLedger
import reconciler as rc
import gold_live

log = logging.getLogger("gold_paper")


def process_maker_pending(pending, ledger, high, low, ts, *, eps, ttl_bars):
    """Shadow maker COMPARTIDO (gold_paper ORO + motor_paper): una limite
    descansando en `limit` se considera llena solo si el precio PENETRA el
    nivel mas alla de `eps` (touch NO llena: peor caso de cola/adverse
    selection). TTL en barras evaluables; al expirar -> MISS. Sella
    MAKER_FILL/MAKER_MISS por pid en `ledger` y devuelve la lista de pendientes
    que siguen vivas. Instrumentacion pura: no toca posiciones."""
    still = []
    for pend in pending:
        d, limit = pend["direction"], pend["limit"]
        filled = (low < limit * (1 - eps)) if d > 0 \
            else (high > limit * (1 + eps))
        if filled:
            ledger.append({
                "event": "MAKER_FILL", "ts": ts, "pid": pend["pid"],
                "limit": limit, "bars_waited": pend["waited"] + 1})
            continue
        pend["waited"] += 1
        if pend["waited"] >= ttl_bars:
            ledger.append({
                "event": "MAKER_MISS", "ts": ts, "pid": pend["pid"],
                "limit": limit, "bars_waited": pend["waited"]})
        else:
            still.append(pend)
    return still


class GoldPaperRuntime:
    """Orquesta, por vela: resolver abiertas -> reconciliar -> clasificar y, si
    ORO, abrir en paper + avisar admin. Track record en un ledger durable."""

    def __init__(self, engine, *, account, governor=None, broker=None,
                 notify_fn=None, requested_risk=None, reconciler=None,
                 reconcile_every=50, digest_every=0,
                 maker_sim=False, maker_eps_bps=1.0, maker_ttl_bars=6):
        self.engine = engine
        self.account = account
        self.governor = governor or RiskGovernor()
        self.broker = broker or PaperBroker()
        self.notify_fn = notify_fn
        self.requested_risk = requested_risk
        self.reconciler = reconciler
        self.reconcile_every = reconcile_every
        self.digest_every = digest_every
        self._ticks = 0
        self.counts = {"gold": 0, "base": 0, "abstain": 0}
        self._coverage_checked = False
        # SHADOW maker (FQ_GOLD_MAKER_SIM): mide en paralelo si una LIMITE en
        # el precio de la senal se habria llenado (penetracion, NO touch) o
        # expirado — el dato de adverse selection que decide si la frontera
        # maker del research (bt_engine [2.2/4]) es capturable. NO cambia las
        # posiciones taker del paper: instrumentacion pura sobre el ledger
        # (MAKER_FILL/MAKER_MISS por pid).
        self.maker_sim = bool(maker_sim)
        self.maker_eps = float(maker_eps_bps) / 10_000.0
        self.maker_ttl_bars = int(maker_ttl_bars)
        self._maker_pending = []

    @classmethod
    def from_env(cls, symbol, *, calculate_levels_fn, notify_fn=None):
        """Arma el runtime desde el entorno:
          FQ_RETRIEVAL_DIR   artefacto del gate (obligatorio)
          FQ_GOLD_LEDGER_PATH ledger durable (default /data/gold_ledger_<slug>.jsonl)
          FQ_GOLD_TP_R       multiplo de R del TP1 (default 1.0)
          FQ_GOLD_PAPER_EQUITY equity de la cuenta paper (default 10000)
          FQ_GOLD_BASELINE_R baseline OOS en unidades de TRADE (enciende reconcile)
          FQ_GOLD_DIGEST_EVERY barras entre digests al admin (0 = off)
        """
        gate_dir = os.environ.get("FQ_RETRIEVAL_DIR")
        if not gate_dir:
            raise RuntimeError("FQ_RETRIEVAL_DIR no seteado (artefacto del gate)")
        engine = gold_live.GoldLiveEngine.from_dir(
            gate_dir, symbol, calculate_levels_fn=calculate_levels_fn,
            tp_r=float(os.environ.get("FQ_GOLD_TP_R", "1.0")))

        slug = symbol.replace("/", "_").replace(":", "_")
        led_path = os.environ.get("FQ_GOLD_LEDGER_PATH",
                                  "/data/gold_ledger_%s.jsonl" % slug)
        broker = PaperBroker(ledger=DurableHashLedger.load(led_path))
        equity = float(os.environ.get("FQ_GOLD_PAPER_EQUITY", "10000"))
        acc = Account("paper-gold-%s" % symbol, equity)
        governor = RiskGovernor()

        # Reconciler AUTO (gated por baseline en unidades de trade).
        baseline = cls._baseline_from_env_or_meta(gate_dir)
        reconciler = None
        if baseline is not None:
            reconciler = rc.Reconciler(broker.ledger, governor,
                                       backtest_expectancy_r=baseline)
            log.info("[gold] reconciler activo (baseline=%.3fR)", baseline)
        else:
            log.info("[gold] reconciler OFF: sin baseline de trade "
                     "(setea FQ_GOLD_BASELINE_R tras observar el paper)")

        digest_every = int(os.environ.get("FQ_GOLD_DIGEST_EVERY", "0"))
        maker_sim = os.environ.get("FQ_GOLD_MAKER_SIM", "0").strip() in ("1", "true", "yes")
        maker_eps = float(os.environ.get("FQ_GOLD_MAKER_EPS_BPS", "1.0"))
        maker_ttl = int(os.environ.get("FQ_GOLD_MAKER_TTL_BARS", "6"))
        if maker_sim:
            log.info("[gold] maker shadow ON (eps=%.1fbps ttl=%d barras): "
                     "midiendo fill-rate de limites, posiciones siguen taker",
                     maker_eps, maker_ttl)
        return cls(engine, account=acc, governor=governor, broker=broker,
                   notify_fn=notify_fn, reconciler=reconciler,
                   digest_every=digest_every, maker_sim=maker_sim,
                   maker_eps_bps=maker_eps, maker_ttl_bars=maker_ttl)

    @staticmethod
    def _baseline_from_env_or_meta(gate_dir):
        env = os.environ.get("FQ_GOLD_BASELINE_R")
        if env not in (None, ""):
            try:
                return float(env)
            except ValueError:
                pass
        try:
            import json
            with open(os.path.join(gate_dir, "meta.json")) as fh:
                meta = json.load(fh)
            v = meta.get("gold_trade_expectancy_r")  # solo si el build lo calculo
            return float(v) if v is not None else None
        except Exception:
            return None

    def _check_coverage(self, state):
        """Una vez: avisa si el state-row vivo no cubre las features del indice
        (drift de esquema -> vecindarios basura en silencio)."""
        self._coverage_checked = True
        try:
            vec = self.engine.gate.index.vec
            expected = list(vec.numeric) + list(vec.categorical)
            missing = [c for c in expected if c not in state]
            if missing and self.notify_fn is not None:
                self.notify_fn(None, {"alert": "cobertura de features incompleta",
                                      "missing": missing}, None)
            if missing:
                log.warning("[gold] features ausentes en el state-row vivo: %s", missing)
        except Exception as e:
            log.warning("[gold] coverage check: %s", e)

    def _maybe_digest(self):
        if self.digest_every and self._ticks % self.digest_every == 0 \
                and self.notify_fn is not None:
            try:
                self.notify_fn(None, {"digest": dict(self.counts),
                                      "ticks": self._ticks, "open": len(self.account.open)},
                               None)
            except Exception as e:
                log.warning("[gold] digest: %s", e)

    def _process_maker_pending(self, high, low, ts):
        """Shadow maker del ORO (delega en el helper compartido)."""
        self._maker_pending = process_maker_pending(
            self._maker_pending, self.broker.ledger, high, low, ts,
            eps=self.maker_eps, ttl_bars=self.maker_ttl_bars)

    def on_bar(self, field, report, df_primary, price, *, high=None, low=None,
               ts=None, vetoed=False):
        """Procesa una vela. high/low resuelven posiciones abiertas. `vetoed` lo
        decide el llamador (capa de decision, con el ts de la VELA — §6.7): si la
        senal es ORO pero la killzone esta vetada, NO se abre. Devuelve
        {tier, opened, resolved, vetoed}."""
        # 1) resolver abiertas contra la vela real (empate pesimista)
        resolved = []
        if high is not None and low is not None:
            for pos in list(self.account.open):
                out = self.broker.resolve_on_bar(self.account, pos, high, low, ts=ts)
                if out is not None:
                    resolved.append({"pid": pos.pid, **out})
            # 1.5) shadow maker: evaluar limites pendientes contra ESTA vela
            #      (antes de abrir nuevas: una limite no se llena en su vela 0)
            if self.maker_sim and self._maker_pending:
                self._process_maker_pending(high, low, ts)

        # 2) reconciliar periodicamente (cierra el lazo de seguridad)
        self._ticks += 1
        if self.reconciler is not None and self._ticks % self.reconcile_every == 0:
            try:
                self.reconciler.check(accounts=[self.account])
            except Exception as e:
                log.warning("[gold] reconciler.check: %s", e)

        # 3) clasificar; si ORO y el gobernador aprueba, abrir en paper + avisar
        sig, verdict = self.engine.evaluate(field, report, df_primary, price)
        tier = verdict.get("tier")
        if tier in self.counts:
            self.counts[tier] += 1
        if not self._coverage_checked:
            self._check_coverage(gold_live.live_state_row(field, report))

        opened = None
        vetoed_now = bool(sig is not None and vetoed)
        if vetoed_now:
            # §6.8 VETO DE SESION (capa de decision; el llamador lo decidio con la
            # killzone de la VELA): la senal ORO NO se abre — consistente con el
            # edge validado (base + veto). Se SELLA para el track record forward
            # (mismo patron que el shadow maker) y se cuenta, pero no entra al
            # broker. Resolucion/maker/reconcile de arriba siguen corriendo.
            self.counts["vetoed"] = self.counts.get("vetoed", 0) + 1
            try:
                self.broker.ledger.append({
                    "event": "GOLD_VETO", "ts": str(ts),
                    "direction": sig.get("direction"), "entry": sig.get("entry")})
            except Exception as e:
                log.warning("[gold] sello veto: %s", e)
            log.info("[gold] ORO VETADO por sesion (no se abre)")
        elif sig is not None:
            d = self.governor.decide(self.account, requested_risk=self.requested_risk)
            if d["approved"]:
                pos = self.broker.open(self.account, sig, d["risk_frac"], ts=ts)
                opened = {"pid": pos.pid, "risk_frac": d["risk_frac"], **sig}
                if self.maker_sim:
                    self._maker_pending.append({
                        "pid": pos.pid, "direction": pos.direction,
                        "limit": pos.entry, "waited": 0})
                if self.notify_fn is not None:
                    try:
                        self.notify_fn(sig, verdict, pos)
                    except Exception as e:
                        log.warning("[gold] notify_fn: %s", e)
            else:
                log.info("[gold] ORO rechazado por gobernador: %s", d["reason"])

        self._maybe_digest()
        return {"tier": tier, "opened": opened, "resolved": resolved,
                "vetoed": vetoed_now}
