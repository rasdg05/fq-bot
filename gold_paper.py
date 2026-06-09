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


class GoldPaperRuntime:
    """Orquesta, por vela: resolver abiertas -> reconciliar -> clasificar y, si
    ORO, abrir en paper + avisar admin. Track record en un ledger durable."""

    def __init__(self, engine, *, account, governor=None, broker=None,
                 notify_fn=None, requested_risk=None, reconciler=None,
                 reconcile_every=50, digest_every=0):
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
        return cls(engine, account=acc, governor=governor, broker=broker,
                   notify_fn=notify_fn, reconciler=reconciler,
                   digest_every=digest_every)

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

    def on_bar(self, field, report, df_primary, price, *, high=None, low=None, ts=None):
        """Procesa una vela. high/low resuelven posiciones abiertas. Devuelve
        {tier, opened, resolved}."""
        # 1) resolver abiertas contra la vela real (empate pesimista)
        resolved = []
        if high is not None and low is not None:
            for pos in list(self.account.open):
                out = self.broker.resolve_on_bar(self.account, pos, high, low, ts=ts)
                if out is not None:
                    resolved.append({"pid": pos.pid, **out})

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
        if sig is not None:
            d = self.governor.decide(self.account, requested_risk=self.requested_risk)
            if d["approved"]:
                pos = self.broker.open(self.account, sig, d["risk_frac"], ts=ts)
                opened = {"pid": pos.pid, "risk_frac": d["risk_frac"], **sig}
                if self.notify_fn is not None:
                    try:
                        self.notify_fn(sig, verdict, pos)
                    except Exception as e:
                        log.warning("[gold] notify_fn: %s", e)
            else:
                log.info("[gold] ORO rechazado por gobernador: %s", d["reason"])

        self._maybe_digest()
        return {"tier": tier, "opened": opened, "resolved": resolved}
