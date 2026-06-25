# -*- coding: utf-8 -*-
"""
================================================================================
  motor_paper_stats — lee el ledger del MOTOR PAPER (§6.10.1) y reporta el dato
  que decide si el techo +0.10R es CAPTURABLE: el FILL-RATE maker REAL y la
  ADVERSE SELECTION (¿la límite se llena en los perdedores y se escapa de los
  ganadores?).

  El research (regrade_events --maker-matrix) midió el techo asumiendo fill 100%.
  Este forward mide el fill REAL. El edge maker neto ≈ matriz §6.10.1 (entrada+TP
  maker, +veto) escalado por el fill-rate de aquí. NO reimplementa los costes
  (esa es la matriz autoritativa); aquí: fill-rate + adverse selection + muestra.

  Uso:
      python tools/motor_paper_stats.py [ruta_ledger]
      # default: $FQ_MOTOR_PAPER_LEDGER_PATH o /data/motor_paper_SOL_USDT.jsonl

  No enciende ni apaga nada: MIDE. La decisión (adoptar maker / matar la línea)
  es manual y exige ≥30-50 fills (regla §6.10).
================================================================================
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution import DurableHashLedger

MIN_FILLS = 30  # regla §6.10: ~30-50 fills para conocer el fill-rate REAL


def _stats(rs):
    if not rs:
        return 0, float("nan"), float("nan"), float("nan")
    n = len(rs)
    mean = sum(rs) / n
    wr = sum(1 for r in rs if r > 0) / n
    total = sum(rs)
    return n, mean, wr, total


def _fmt(n, mean, wr, total, label="GROSS"):
    if n == 0:
        return "n=0"
    return "n=%d  exp_r=%+.4f (%s)  WR=%.1f%%  total=%+.2fR" % (
        n, mean, label, wr * 100.0, total)


def main(argv):
    path = (argv[1] if len(argv) > 1 else
            os.environ.get("FQ_MOTOR_PAPER_LEDGER_PATH",
                           "/data/motor_paper_SOL_USDT.jsonl"))
    if not os.path.exists(path):
        print("[motor-stats] no existe el ledger: %s" % path)
        print("  (¿corrió ya el motor paper? revisa FQ_MOTOR_PAPER=1 y el Volume)")
        return 2

    ledger = DurableHashLedger.load(path)  # verifica la cadena SHA-256 o LANZA
    recs = [r["payload"] for r in ledger.records]

    # join por pid: outcome (CLOSE) + provenance (META) + maker (FILL/MISS)
    pnl = {}          # pid -> pnl_r
    kz = {}           # pid -> killzone
    maker = {}        # pid -> "FILL" | "MISS"  (shadow)
    ftype = {}        # pid -> "maker" | "taker"  (modo EJECUCION)
    regime_m = {}     # pid -> "stable" | "deriva" | ...  (juez de FQ_DERIVA_VETO)
    vetoed = {}       # killzone -> n
    n_runaway = 0     # runners perdidos (modo EJECUCION, sin posicion)
    net = False       # ¿NETO de costes? (resolve con cost model)
    for p in recs:
        ev = p.get("event")
        pid = p.get("pid")
        if ev == "CLOSE":
            pnl[pid] = p.get("pnl_r")
            if p.get("fill_type") is not None:
                net = True
        elif ev == "MOTOR_OPEN_META":
            kz[pid] = p.get("killzone")
            regime_m[pid] = p.get("regime")
            if p.get("fill_type") is not None:
                ftype[pid] = p.get("fill_type")
        elif ev == "MAKER_FILL":
            maker[pid] = "FILL"
        elif ev == "MAKER_MISS":
            maker[pid] = "MISS"
        elif ev == "MAKER_RUNAWAY":
            n_runaway += 1
        elif ev == "MOTOR_VETOED":
            k = p.get("killzone")
            vetoed[k] = vetoed.get(k, 0) + 1

    closed = {pid: r for pid, r in pnl.items() if r is not None}
    n_open_meta = len(kz)
    n_closed = len(closed)
    n_veto = sum(vetoed.values())
    lbl = "NETO" if net else "GROSS"

    print("[motor-stats] ledger=%s  registros=%d" % (path, len(recs)))
    print("  abiertas(META)=%d  cerradas(CLOSE)=%d  vetadas=%d" %
          (n_open_meta, n_closed, n_veto))
    if vetoed:
        print("  vetadas por killzone: " +
              ", ".join("%s:%d" % (k, v) for k, v in sorted(vetoed.items())))

    if not closed:
        print("  Sin trades cerrados todavía — sigue acumulando paper.")
        return 1

    # 1) cartera abierta (post-veto): el motor base operable
    allr = list(closed.values())
    cap = "" if net else "  (GROSS = sin costes; net via matriz §6.10.1)"
    print("\n  [cartera post-veto] " + _fmt(*_stats(allr), label=lbl) + cap)

    # 1b) R por REGIME (stable vs deriva): el juez forward de FQ_DERIVA_VETO=0.
    #     El +0.10R del cubo es 100% 'stable'; aquí se mide si los fires de 'deriva'
    #     (que el veto bloquea) aguantan o arrastran cuando se los deja pasar.
    regs = sorted({r for r in regime_m.values() if r})
    if regs:
        print("\n  [R por regime] (¿deriva aguanta como stable, o arrastra?)")
        for rg in regs:
            rr = [closed[pid] for pid in closed if regime_m.get(pid) == rg]
            if rr:
                print("    %-8s " % rg + _fmt(*_stats(rr), label=lbl))

    # 2) FILL-RATE maker (el dato que faltaba; techo asumía 100%)
    n_fill = sum(1 for v in maker.values() if v == "FILL")
    n_miss = sum(1 for v in maker.values() if v == "MISS")
    n_eval = n_fill + n_miss
    n_pend = n_closed - n_eval
    if n_eval > 0:
        rate = n_fill / n_eval
        print("\n  [fill-rate maker] FILL=%d  MISS=%d  pendientes/abiertas≈%d  "
              "-> fill_rate=%.1f%%" % (n_fill, n_miss, max(n_pend, 0), rate * 100.0))
    elif not ftype and not n_runaway:
        print("\n  [fill-rate maker] aún sin eventos MAKER_* (¿FQ_MOTOR_PAPER_"
              "MAKER_SIM=1?).")

    # 3) ADVERSE SELECTION: ¿la límite se llena en los perdedores?
    fill_r = [closed[pid] for pid in closed if maker.get(pid) == "FILL"]
    miss_r = [closed[pid] for pid in closed if maker.get(pid) == "MISS"]
    if fill_r or miss_r:
        print("\n  [adverse selection] (lente del caveat §6.10.1 #1)")
        print("    FILLED (lo que el maker SÍ captura): " + _fmt(*_stats(fill_r), label=lbl))
        print("    MISSED (los que se escapan):          " + _fmt(*_stats(miss_r), label=lbl))
        nf, mf, _, _ = _stats(fill_r)
        nm, mm, _, _ = _stats(miss_r)
        if nf and nm:
            if mf < mm:
                print("    ⚠ los FILLED rinden MENOS que los MISSED -> adverse "
                      "selection (el maker se queda los flojos). Cuidado.")
            else:
                print("    ✓ los FILLED NO rinden peor que los MISSED -> sin "
                      "adverse selection evidente (alienta el maker).")

    # 3b) EJECUCION maker (FQ_EXEC_MODE=maker): fill-rate REAL (runaways = miss) +
    #     maker vs fallback taker -> el numero de adverse selection del modo exec.
    n_mk = sum(1 for v in ftype.values() if v == "maker")
    n_tk = sum(1 for v in ftype.values() if v == "taker")
    exec_total = n_mk + n_tk + n_runaway
    if exec_total:
        print("\n  [EJECUCION maker] maker=%d  fallback_taker=%d  runaway=%d  "
              "-> fill_rate=%.1f%%" % (n_mk, n_tk, n_runaway,
                                       100.0 * n_mk / exec_total))
        mk_r = [closed[pid] for pid in closed if ftype.get(pid) == "maker"]
        tk_r = [closed[pid] for pid in closed if ftype.get(pid) == "taker"]
        print("    MAKER (fill barato):     " + _fmt(*_stats(mk_r), label=lbl))
        print("    FALLBACK (taker, chase): " + _fmt(*_stats(tk_r), label=lbl))
        nmk, mmk, _, _ = _stats(mk_r)
        ntk, mtk, _, _ = _stats(tk_r)
        if nmk and ntk and mmk < mtk:
            print("    ⚠ MAKER rinde MENOS que el FALLBACK -> adverse selection.")
        if n_runaway:
            print("    RUNAWAY: %d runners perdidos = el costo real del maker." %
                  n_runaway)

    # 4) segmento por killzone de la cartera operable
    by_kz = {}
    for pid, r in closed.items():
        by_kz.setdefault(kz.get(pid, "?"), []).append(r)
    if len(by_kz) > 1:
        print("\n  [por killzone, cartera operable]")
        for k, rs in sorted(by_kz.items(), key=lambda kv: -_stats(kv[1])[1]):
            print("    %-22s %s" % (k, _fmt(*_stats(rs), label=lbl)))

    # 5) veredicto de muestra (en EJECUCION manda exec_total: el fill-rate REAL)
    sample = exec_total if exec_total else n_eval
    print("\n  [muestra] %d fills evaluados (meta §6.10: >=%d-50 para decidir)." %
          (sample, MIN_FILLS))
    if sample < MIN_FILLS:
        print("  ⏳ insuficiente: sigue en paper. El +0.10R es TECHO hasta tener "
              "el fill-rate sobre >=%d fills." % MIN_FILLS)
        return 1
    print("  ✅ muestra suficiente: combina fill_rate × matriz §6.10.1 (entrada+TP "
          "maker, +veto) y aplica la regla de decisión §6.10.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
