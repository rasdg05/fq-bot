# -*- coding: utf-8 -*-
"""
================================================================================
  GOLD PAPER - runtime en PAPEL del gate ORO (admin-only, 0% real)
  by RasDG_Sol + Claude

  El monolito invoca esto por vela cuando FQ_GOLD_LIVE=1 (default OFF). Cierra el
  lazo: clasifica el estado con el gate de retrieval (GoldLiveEngine), y si es ORO
  abre en PAPEL (PaperBroker -> sella en HashLedger que el Reconciler audita),
  resuelve lo abierto contra la vela y avisa al admin (notify_fn inyectable;
  en prod = broadcast_to_subscribers(..., tiers=["admin"])). SIN broadcast a VIP.

  Reusa execution (RiskGovernor/PaperBroker/Account), gold_live y reconciler. No
  decide tamano real, no toca la entrega VIP. Pieza pura: engine y notify_fn se
  inyectan -> se testea sin red ni monolito.
================================================================================
"""
import os
import logging

from execution import RiskGovernor, Account, PaperBroker
import gold_live

log = logging.getLogger("gold_paper")


class GoldPaperRuntime:
    """Orquesta, por vela: resolver abiertas -> reconciliar (periodico) ->
    clasificar y, si ORO, abrir en paper + avisar admin. Todo en una cuenta de
    papel; el ledger del broker es el track record forward sellado."""

    def __init__(self, engine, *, account, governor=None, broker=None,
                 notify_fn=None, requested_risk=None, reconciler=None,
                 reconcile_every=50):
        self.engine = engine
        self.account = account
        self.governor = governor or RiskGovernor()
        self.broker = broker or PaperBroker()
        self.notify_fn = notify_fn
        self.requested_risk = requested_risk
        self.reconciler = reconciler
        self.reconcile_every = reconcile_every
        self._ticks = 0

    @classmethod
    def from_env(cls, symbol, *, calculate_levels_fn, notify_fn=None,
                 broker=None, reconciler=None):
        """Arma el runtime desde el entorno: FQ_RETRIEVAL_DIR (artefacto del gate),
        FQ_GOLD_TP_R (TP1=1.0), FQ_GOLD_PAPER_EQUITY. Lanza si falta el artefacto."""
        gate_dir = os.environ.get("FQ_RETRIEVAL_DIR")
        if not gate_dir:
            raise RuntimeError("FQ_RETRIEVAL_DIR no seteado (artefacto del gate)")
        engine = gold_live.GoldLiveEngine.from_dir(
            gate_dir, symbol, calculate_levels_fn=calculate_levels_fn,
            tp_r=float(os.environ.get("FQ_GOLD_TP_R", "1.0")))
        equity = float(os.environ.get("FQ_GOLD_PAPER_EQUITY", "10000"))
        acc = Account(f"paper-gold-{symbol}", equity)
        return cls(engine, account=acc, notify_fn=notify_fn, broker=broker,
                   reconciler=reconciler)

    def on_bar(self, field, report, df_primary, price, *, high=None, low=None, ts=None):
        """Procesa una vela. high/low (si se pasan) resuelven posiciones abiertas
        contra la vela. Devuelve un reporte {tier, opened, resolved}."""
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
                log.warning("reconciler.check: %s", e)

        # 3) clasificar; si ORO y el gobernador aprueba, abrir en paper + avisar
        sig, verdict = self.engine.evaluate(field, report, df_primary, price)
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
                        log.warning("notify_fn: %s", e)
            else:
                log.info("ORO rechazado por gobernador: %s", d["reason"])
        return {"tier": verdict.get("tier"), "opened": opened, "resolved": resolved}
