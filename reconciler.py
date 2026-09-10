# -*- coding: utf-8 -*-
"""
================================================================================
  RECONCILER - lazo de seguridad operativo (cierra ANTES de cualquier orden)
  by RasDG_Sol + Claude

  El guardia que se ejecuta entre el track record vivo y el motor de riesgo.
  No abre nada: AUDITA y, si hace falta, APAGA. Tres comprobaciones, en orden
  de severidad, todas puras (sin red):

    1) Integridad de cadena: relee el HashLedger y verifica la cadena SHA-256.
       Si alguien editó el historial, las métricas son mentira -> kill-switch y
       cortocircuito (no tiene sentido seguir midiendo sobre datos corruptos).
    2) Drawdown diario: si alguna cuenta cruzó el tope de pérdida del día,
       activa el kill-switch (freno duro, igual que la regla de DD del governor
       pero a nivel de libro completo).
    3) Drift de expectancy: extrae los pnl_r REALIZADOS del ledger y los pasa a
       bt_forward.reconcile() contra la expectancy del backtest. Si la viva cae
       FUERA del IC bootstrap y rinde POR DEBAJO del backtest (decay del edge /
       cambio de régimen), activa el kill-switch. Si supera al backtest, solo
       avisa: no se apaga por ir bien.

  Con muestra insuficiente NO apaga: no se castiga la falta de datos, se espera.
  Reusa execution.HashLedger / RiskGovernor / Account y bt_forward.reconcile.
================================================================================
"""
import logging

import bt_forward

log = logging.getLogger("reconciler")

CLOSE = "CLOSE"


def extract_closed_r(ledger):
    """Recorre el ledger y devuelve la lista de pnl_r de los eventos CLOSE
    (ignora los OPEN: solo cuentan los desenlaces realizados). Es la materia
    prima de la expectancy viva."""
    out = []
    for rec in ledger.records:
        p = rec.get("payload", {})
        if p.get("event") == CLOSE and p.get("pnl_r") is not None:
            out.append(float(p["pnl_r"]))
    return out


class SignalLedgerView:
    """Adaptador: expone el ledger de SENALES (SQLite, fq_ledger.db) con la
    misma interfaz que HashLedger (.records / .verify()) para que Reconciler
    pueda auditarlo SIN cambios.

    Por que existe
    --------------
    El Reconciler estaba conectado solo a los HashLedger de gold/funding paper
    — y ademas apagado por defecto (sin baseline en env). El numero que se
    publica a clientes sale de OTRA base, fq_ledger.db, que nadie auditaba. El
    10-jun-2026 esa base acumulo 23 cierres imposibles y el track record se fue
    a E[R]=+1.84R mientras el motor real marcaba -0.51R, sin que saltara nada.
    Este adaptador cierra ese lazo: el detector se conecta a lo que realmente
    se publica.

    Mapeo de las dos comprobaciones
    -------------------------------
    - `verify()`  <- integridad. En el HashLedger es la cadena SHA-256; aqui es
      el INVARIANTE DE AUDITABILIDAD: ninguna senal cerrada RECIENTEMENTE puede
      tener una vida registrada mayor que su horizonte de timeout. Si aparece
      una, el tracker volvio a romperse y las metricas son indefendibles ->
      mismo tratamiento que una cadena corrupta (kill + cortocircuito).
      El chequeo se limita a `lookback_days` a proposito: la corrupcion
      historica ya esta excluida de las stats por ledger_stats; lo que hay que
      detectar es una RECAIDA, no volver a castigar lo ya contenido.
    - `records`   <- expectancy viva. Solo filas AUDITABLES, en el formato de
      evento CLOSE que espera extract_closed_r.
    """

    def __init__(self, fetch_rows, lookback_days=7):
        """fetch_rows: callable -> secuencia de filas con outcome, pnl_r,
        ts_closed y minutes_open (inyectado para no acoplar a sqlite ni
        obligar a un import circular con entropy_cognition)."""
        self._fetch_rows = fetch_rows
        self.lookback_days = lookback_days

    def _rows(self):
        try:
            return list(self._fetch_rows() or [])
        except Exception as e:
            log.warning("SignalLedgerView: fetch fallo (%s)", e)
            return []

    @property
    def records(self):
        import ledger_stats
        auditable, _ = ledger_stats.filter_auditable(self._rows())
        return [{"payload": {"event": CLOSE, "pnl_r": float(r["pnl_r"])}}
                for r in auditable if r["pnl_r"] is not None]

    def verify(self):
        """False si una senal cerrada dentro de la ventana de lookback viola el
        invariante de auditabilidad (= el tracker esta produciendo desenlaces
        imposibles otra vez)."""
        import ledger_stats
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(days=self.lookback_days)).isoformat()
        for r in self._rows():
            try:
                ts_closed = r["ts_closed"]
            except (KeyError, IndexError, TypeError):
                continue
            if not ts_closed or ts_closed < cutoff:
                continue
            if not ledger_stats.is_auditable(r):
                log.error(
                    "ledger de senales: cierre NO auditable en los ultimos %dd "
                    "(outcome=%s minutes_open=%s) -> tracker roto",
                    self.lookback_days, r["outcome"], r["minutes_open"])
                return False
        return True


class Reconciler:
    """Compara el track record vivo (HashLedger) contra el baseline del backtest
    y, ante drift / DD / cadena rota, activa el kill-switch del gobernador. Es el
    componente que hay que poder correr ANTES de cada orden y de forma periódica.

    ledger                 : HashLedger sellado por el broker.
    governor               : RiskGovernor cuyo kill-switch se activará si salta algo.
    backtest_expectancy_r  : expectancy (en R) del backtest = baseline a defender.
    max_daily_loss_frac    : tope de pérdida del día por cuenta (DD diario).
    min_trades             : muestra mínima para evaluar drift (debajo, espera).
    ci                     : nivel del IC bootstrap del reconcile.
    """

    def __init__(self, ledger, governor, backtest_expectancy_r,
                 max_daily_loss_frac=0.04, min_trades=20, ci=0.90):
        self.ledger = ledger
        self.governor = governor
        self.backtest_expectancy_r = backtest_expectancy_r
        self.max_daily_loss_frac = max_daily_loss_frac
        self.min_trades = min_trades
        self.ci = ci

    def _kill(self, reasons, reason):
        """Activa el kill-switch global y acumula el motivo."""
        self.governor.cfg.kill_switch = True
        reasons.append(reason)

    def check(self, accounts=None):
        """Corre las tres comprobaciones en orden de severidad y devuelve un
        reporte. Activa el kill-switch del governor si algo salta.

        accounts : iterable de Account para el chequeo de DD diario (opcional).
        Devuelve dict con: chain_ok, n_trades, dd_breach, reconcile, killed, reasons.
        """
        reasons = []

        # 1) Integridad de cadena. Si está rota, todo lo demás es indefendible.
        chain_ok = self.ledger.verify()
        if not chain_ok:
            self._kill(reasons, "cadena del ledger corrupta (verify() falló)")
            return {"chain_ok": False, "n_trades": None, "dd_breach": None,
                    "reconcile": None, "killed": True, "reasons": reasons}

        # 2) Drawdown diario por cuenta (freno duro de libro completo).
        dd_breach = False
        for acc in (accounts or []):
            if acc.day_pnl_frac() <= -self.max_daily_loss_frac:
                dd_breach = True
                self._kill(reasons,
                           f"DD diario de {acc.account_id}: {acc.day_pnl_frac():.2%} "
                           f"<= -{self.max_daily_loss_frac:.0%}")

        # 3) Drift de expectancy viva vs IC del backtest.
        live_r = extract_closed_r(self.ledger)
        n = len(live_r)
        recon = None
        if n < self.min_trades:
            recon = {"within": None, "n": n,
                     "verdict": f"muestra insuficiente ({n}/{self.min_trades}) — esperar"}
        else:
            recon = bt_forward.reconcile(self.backtest_expectancy_r, live_r, ci=self.ci)
            live_exp = recon.get("live_expectancy_r")
            bt = recon.get("backtest_expectancy_r")
            if (recon.get("within") is False and bt is not None
                    and live_exp is not None and live_exp < bt):
                self._kill(reasons, f"DRIFT a la baja: viva {live_exp:.3f}R < backtest "
                                    f"{bt:.3f}R y fuera del IC")

        killed = len(reasons) > 0
        return {"chain_ok": chain_ok, "n_trades": n, "dd_breach": dd_breach,
                "reconcile": recon, "killed": killed, "reasons": reasons}
