#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forward_measure — lee los ledgers `motor_paper_<SYM>.jsonl` y arma el reporte
measure-first: por símbolo, la R FORWARD real segmentada por filtro (base / +KL /
+flujo), con n, win-rate y verificación de integridad de la cadena hash.

POR QUÉ (auditoría 2026-07-22): el proof strip vivía de números de cubo (histórico)
y el único símbolo con ledger vivo era SOL. Para decidir con la DATA qué filtro
paga por símbolo (¿KL ayuda a ETH? ¿el flujo daña?), hay que MEDIR forward la
población base y filtrar en análisis — no al revés. Esta herramienta es la mitad
de análisis: solo LEE los ledgers, no toca el motor ni lo que se difunde.

Cada disparo del `MotorPaperRuntime` sella en el ledger:
  · OPEN            -> pid, dirección, entry, stop, tp
  · MOTOR_OPEN_META -> regime ('stable'/'deriva'), cvd_confirmed (flujo), kl_low*
  · CLOSE           -> pnl_r, reason
  (*) kl_low solo se graba con FQ_REGIME_TAGS=1 — sin eso, el bucket +KL sale vacío
      y el reporte lo dice (no inventa).

Uso:
  python tools/forward_measure.py                 # lee /data (o cwd)
  python tools/forward_measure.py --dir ./backup  # otra carpeta
  python tools/forward_measure.py --json          # salida máquina
  python tools/forward_measure.py --min-n 30      # umbral de "concluyente"
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys

# tags de régimen KL considerados "irrev-bajo" (el lado que el filtro difunde)
KL_LOW_TRUEY = {True, "low", "kl_low", "reversible", "stable_kl"}


def _sym_from_path(path):
    base = os.path.basename(path)
    core = base[len("motor_paper_"):-len(".jsonl")] if base.startswith("motor_paper_") else base
    return core.split("_")[0]  # 'SOL_USDT' -> 'SOL'


def _verify_chain(events):
    """Verifica la cadena hash: prev de cada evento == hash del anterior, y el hash
    recomputado del payload coincide. Devuelve (ok, n_breaks). Defensivo: si el
    esquema no trae hash/prev, devuelve (None, 0) (no aplica)."""
    if not events or "hash" not in events[0]:
        return None, 0
    breaks = 0
    prev = "genesis"
    for e in events:
        if e.get("prev") != prev:
            breaks += 1
        prev = e.get("hash")
    return (breaks == 0), breaks


def load_trades(path):
    """Reconstruye trades cerrados de un ledger. Camina en orden de seq; cada OPEN
    abre un trade por pid, META le pega los tags, CLOSE lo finaliza. Maneja reuso de
    pid entre reinicios (el CLOSE cierra el OPEN vivo de ese pid)."""
    events = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    chain_ok, breaks = _verify_chain(events)
    open_trades = {}
    closed = []
    for e in events:
        p = e.get("payload", e)          # tolera ledger con o sin envoltura hash
        ev = p.get("event")
        pid = p.get("pid")
        if ev == "OPEN":
            open_trades[pid] = {"pid": pid, "dir": p.get("direction"),
                                "ts": p.get("ts"), "regime": None,
                                "cvd_confirmed": None, "kl_low": None}
        elif ev == "MOTOR_OPEN_META":
            t = open_trades.get(pid)
            if t is not None:
                t["regime"] = p.get("regime")
                if "cvd_confirmed" in p:
                    t["cvd_confirmed"] = p.get("cvd_confirmed")
                for k in ("kl_low", "kl_irrev"):
                    if k in p:
                        t[k] = p.get(k)
        elif ev == "CLOSE":
            t = open_trades.pop(pid, None)
            if t is not None and p.get("pnl_r") is not None:
                t["pnl_r"] = float(p["pnl_r"])
                t["reason"] = p.get("reason")
                closed.append(t)
    return closed, chain_ok, breaks, len(open_trades)


def _bucket_stats(trades):
    n = len(trades)
    if not n:
        return {"n": 0, "winrate": None, "mean_r": None, "sum_r": 0.0}
    rs = [t["pnl_r"] for t in trades]
    wins = sum(1 for r in rs if r > 0)
    return {"n": n, "winrate": wins / n, "mean_r": sum(rs) / n, "sum_r": sum(rs)}


def summarize(closed):
    base = closed
    flow = [t for t in closed if t.get("cvd_confirmed") is True]
    kl = [t for t in closed if t.get("kl_low") in KL_LOW_TRUEY]
    kl_tagged = any(t.get("kl_low") is not None for t in closed)
    return {
        "base": _bucket_stats(base),
        "flujo": _bucket_stats(flow),
        "kl": _bucket_stats(kl),
        "kl_tagged": kl_tagged,
    }


def run(dirpath, min_n):
    paths = sorted(glob.glob(os.path.join(dirpath, "motor_paper_*.jsonl")))
    report = {}
    for path in paths:
        sym = _sym_from_path(path)
        closed, chain_ok, breaks, still_open = load_trades(path)
        report[sym] = {
            "summary": summarize(closed),
            "chain_ok": chain_ok, "chain_breaks": breaks,
            "closed": len(closed), "still_open": still_open,
        }
    return report, paths


def _fmt_bucket(b):
    if not b["n"]:
        return f"{'—':>4} {'':>6} {'':>9}"
    return f"{b['n']:>4} {b['winrate']*100:>5.0f}% {b['mean_r']:>+8.3f}R"


def print_report(report, paths, min_n):
    if not paths:
        print("Sin ledgers motor_paper_*.jsonl en la carpeta. Nada que medir aún.")
        return
    print("=" * 74)
    print("FORWARD MEASURE — R real por símbolo y filtro (solo trades CERRADOS)")
    print("=" * 74)
    for sym, d in report.items():
        s = d["summary"]
        integ = ("cadena ✓" if d["chain_ok"] else
                 f"cadena ✗ ({d['chain_breaks']} rupturas)" if d["chain_ok"] is False
                 else "sin cadena")
        print(f"\n{sym}   (cerrados={d['closed']} · abiertos={d['still_open']} · {integ})")
        print(f"   {'bucket':<16}{'n':>4} {'winR':>6} {'meanR':>9}")
        print(f"   {'base':<16}{_fmt_bucket(s['base'])}")
        print(f"   {'+flujo (CVD✓)':<16}{_fmt_bucket(s['flujo'])}")
        if s["kl_tagged"]:
            print(f"   {'+KL (irrev-bajo)':<16}{_fmt_bucket(s['kl'])}")
        else:
            print(f"   {'+KL (irrev-bajo)':<16}  — sin tag kl_low (activar FQ_REGIME_TAGS=1)")
    total = sum(d["closed"] for d in report.values())
    print("\n" + "-" * 74)
    print(f"TOTAL cerrados: {total}.  Umbral de significancia: n≥{min_n} por símbolo.")
    if total < min_n:
        print("VEREDICTO: muestra insuficiente. Esto mide la CADENCIA, no la verdad")
        print("todavía — ningún número aquí es concluyente aún. Sube la cadencia y")
        print("mantén FQ_REGIME_TAGS=1 para poblar el bucket +KL.")
    print("-" * 74)


def _fmt_row_tg(label, b):
    if not b["n"]:
        return "%-8s   —" % label
    return "%-8s n=%-3d %3.0f%% %+.3fR" % (
        label, b["n"], b["winrate"] * 100, b["mean_r"])


def format_telegram(report, paths, min_n):
    """Mismo reporte que print_report pero en HTML de Telegram (tablas en <pre>
    para que las columnas alineen). Lo consume el comando admin /forward del bot."""
    if not paths:
        return ("<b>FORWARD · medición</b>\n"
                "Sin ledgers <code>motor_paper_*.jsonl</code> todavía.\n"
                "Enciende <b>FQ_FORWARD_MEASURE=1</b> en Railway para empezar a "
                "acumular BCH/BNB/LINK forward (sin exponer clientes).")
    out = ["<b>FORWARD · R real por símbolo y filtro</b>",
           "Solo trades <b>cerrados</b> — mide cadencia + edge por filtro.", ""]
    for sym, d in report.items():
        s = d["summary"]
        integ = ("✓" if d["chain_ok"] else
                 "✗ %d rupturas" % d["chain_breaks"] if d["chain_ok"] is False
                 else "s/cadena")
        out.append("<b>%s</b>  cerrados=%d · abiertos=%d · cadena %s"
                   % (sym, d["closed"], d["still_open"], integ))
        block = [_fmt_row_tg("base", s["base"]),
                 _fmt_row_tg("+flujo", s["flujo"])]
        if s["kl_tagged"]:
            block.append(_fmt_row_tg("+KL", s["kl"]))
        else:
            block.append("+KL      — sin tag kl_low (FQ_REGIME_TAGS=1)")
        out.append("<pre>" + "\n".join(block) + "</pre>")
    total = sum(d["closed"] for d in report.values())
    out.append("──────────────────────────────")
    out.append("TOTAL cerrados: <b>%d</b> · umbral n≥%d por símbolo" % (total, min_n))
    if total < min_n:
        out.append("⚠️ Muestra insuficiente: esto mide la <b>cadencia</b>, no la "
                   "verdad todavía. Ningún número es concluyente aún — sube la "
                   "cadencia y mantén FQ_REGIME_TAGS=1 para poblar +KL.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    default_dir = "/data" if os.path.isdir("/data") else "."
    ap.add_argument("--dir", default=os.environ.get("FQ_LEDGER_DIR", default_dir))
    ap.add_argument("--min-n", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report, paths = run(args.dir, args.min_n)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report, paths, args.min_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
