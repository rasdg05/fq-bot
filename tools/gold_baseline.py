# -*- coding: utf-8 -*-
"""
================================================================================
  gold_baseline — lee el ledger durable del gate ORO y calcula la expectancy
  VIVA en unidades de TRADE, lista para fijar en FQ_GOLD_BASELINE_R.

  Es el puente entre la fase paper (admin-only, reconciler OFF) y el armado del
  kill-switch: el research entrega su edge en unidades de forward-label, que NO
  es la misma vara que el TP1 del PaperBroker. Por eso el baseline del Reconciler
  debe salir del PROPIO paper. Esta herramienta lo extrae sin red ni deps nuevas:
  rehidrata el HashLedger (verifica la cadena SHA-256), toma los pnl_r de los
  CLOSE y reporta media / WR / dispersión + la línea de env lista para copiar.

  Uso:
      python tools/gold_baseline.py [ruta_ledger]
      # default: $FQ_GOLD_LEDGER_PATH o /data/gold_ledger_SOL_USDT.jsonl

  No apaga ni enciende nada: solo MIDE y sugiere. La decisión de fijar el env es
  manual (igual que el resto del runbook §9.2.1).
================================================================================
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution import DurableHashLedger
from reconciler import extract_closed_r

MIN_TRADES = 20  # mismo umbral que Reconciler.min_trades: debajo, no hay baseline


def _stats(rs):
    n = len(rs)
    mean = sum(rs) / n
    wins = sum(1 for r in rs if r > 0)
    var = sum((r - mean) ** 2 for r in rs) / n if n > 1 else 0.0
    std = var ** 0.5
    gains = sum(r for r in rs if r > 0)
    losses = -sum(r for r in rs if r < 0)
    pf = (gains / losses) if losses > 0 else float("inf")
    return n, mean, wins / n, std, pf


def main(argv):
    path = (argv[1] if len(argv) > 1 else
            os.environ.get("FQ_GOLD_LEDGER_PATH",
                           "/data/gold_ledger_SOL_USDT.jsonl"))
    if not os.path.exists(path):
        print("[gold-baseline] no existe el ledger: %s" % path)
        print("  (¿corrió ya la fase paper? revisa FQ_GOLD_LEDGER_PATH y el Volume)")
        return 2

    # load() verifica la cadena y LANZA si está manipulada/parcial: si la cadena
    # está rota, la expectancy es indefendible y no debe usarse de baseline.
    ledger = DurableHashLedger.load(path)
    rs = extract_closed_r(ledger)
    n_total = len(ledger.records)

    print("[gold-baseline] ledger=%s  registros=%d  CLOSE=%d" %
          (path, n_total, len(rs)))

    if not rs:
        print("  Sin trades cerrados todavía — el reconciler sigue OFF. Espera "
              "más paper antes de fijar baseline.")
        return 1

    n, mean, wr, std, pf = _stats(rs)
    print("  n_cerrados=%d  expectancy=%.4fR  WR=%.1f%%  std=%.3fR  PF=%s" %
          (n, mean, wr * 100.0, std, ("%.2f" % pf if pf != float("inf") else "inf")))

    if n < MIN_TRADES:
        print("  ⚠ muestra insuficiente (%d/%d). El Reconciler tampoco evaluaría "
              "drift por debajo de %d cierres — sigue en paper." %
              (n, MIN_TRADES, MIN_TRADES))
        return 1

    print("\n  Baseline sugerido (expectancy viva de trade):")
    print("    FQ_GOLD_BASELINE_R=%.4f" % mean)
    print("  Fíjalo en el entorno de prod para ARMAR el kill-switch del "
          "Reconciler (apaga si la viva cae fuera del IC y por debajo del baseline).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
