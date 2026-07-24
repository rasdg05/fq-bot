#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""psycho_analyzer — Psicólogo de mercado, Fase 1: lee un CSV de trades de tu broker
y saca patrones de comportamiento con estadística HONESTA (Python puro, sin deps).

Es la mitad de LECTURA del "AI Psychologist" (ver marca/vision_psicologo_broker.md):
segmenta tus trades por hora, día y símbolo, mide win-rate y P&L por segmento,
detecta la reentrada post-pérdida (el "revenge trade"), tus ventanas de
vulnerabilidad y tus fortalezas, y estima el costo de la indisciplina.

REGLA DE ORO (igual que forward_measure): sin muestra suficiente, NO afirma. Un
patrón con n chico se etiqueta "no concluyente" — nunca se vende como ley. Eso es
justo lo que nos separa de la competencia, que marca "Critical" con n=1.

Fase 2 (no aquí): cruzar cada trade con el RÉGIMEN de mercado de nuestro feed por
timestamp — ahí revelamos patrones clima-dependientes que la competencia no puede.

Uso:
  python tools/psycho_analyzer.py --file mis_trades.csv
  python tools/psycho_analyzer.py --file mis_trades.csv --min-n 15 --json
  python tools/psycho_analyzer.py --demo          # datos sintéticos, sin archivo

Formato CSV: flexible. Reconoce cabeceras comunes de MT4/MT5/cTrader/Binance/Bybit.
Campos mínimos: una fecha de apertura y el P&L. Symbol y fecha de cierre son opcionales.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timedelta

# Umbral por defecto para llamar "concluyente" a un segmento. Por debajo se muestra
# pero etiquetado como muestra chica (honestidad > titular).
MIN_N = 15
# Ventana de la reentrada "revenge": operar de nuevo dentro de X min tras cerrar en rojo.
REENTRY_MIN = 30

# --- resolución flexible de columnas: cabecera cruda (lower) -> campo canónico ---
_ALIASES = {
    "open_time": ["open time", "opentime", "open_time", "time", "date", "fecha",
                  "entry time", "entrytime", "open date", "opened", "open",
                  "created at", "datetime", "timestamp"],
    "close_time": ["close time", "closetime", "close_time", "exit time",
                   "exittime", "close date", "closed", "close"],
    "symbol": ["symbol", "instrument", "pair", "ticker", "market", "activo",
               "par", "simbolo"],
    "pnl": ["profit", "pnl", "p/l", "p&l", "net p/l", "net profit", "realized pnl",
            "realized p/l", "ganancia", "resultado", "profit/loss", "net", "result",
            "closed pnl", "realizedpnl"],
    "direction": ["direction", "side", "type", "buy/sell", "tipo", "lado"],
}


def _norm(h):
    """minúsculas + puntuación a espacio (así 'Date(UTC)'->'date utc', 'P/L'->'p l');
    normaliza header y alias IGUAL para que exacto y por-palabra funcionen en ambos."""
    s = (h or "").lower().replace("﻿", "")
    for ch in "()[]{}/\\|-_.,:;&%$#@!?\"'":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def resolve_columns(header):
    """header: lista de nombres de columna. Devuelve {canónico: índice} para lo que
    se pudo reconocer. Matching exacto primero, luego por palabra."""
    idx = {}
    low = [_norm(h) for h in header]
    for canon, names in _ALIASES.items():
        norm_names = [_norm(n) for n in names]
        found = None
        for name in norm_names:                   # exacto gana
            if name in low:
                found = low.index(name)
                break
        if found is None:                         # luego por palabra
            for i, h in enumerate(low):
                words = h.split()
                if any(n == h or n in words for n in norm_names):
                    found = i
                    break
        if found is not None:
            idx[canon] = found
    return idx


_DT_FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
    "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
]


def parse_dt(s):
    s = (s or "").strip().replace("T", " ").split(".")[0].split("+")[0].strip()
    if not s:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # epoch (s o ms)?
    try:
        v = float(s)
        if v > 1e12:
            v /= 1000.0
        return datetime.utcfromtimestamp(v)
    except (ValueError, OSError, OverflowError):
        return None


def parse_pnl(s):
    if s is None:
        return None
    t = str(s).strip().replace("$", "").replace(",", "").replace("%", "")
    t = t.replace("(", "-").replace(")", "")          # (123) contable = -123
    if t in ("", "-", "--"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def load_trades(path):
    """Devuelve (trades, meta). trade = {open_dt, close_dt, symbol, pnl, win}.
    Ignora filas sin fecha de apertura o sin P&L (no inventa)."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], {"cols": {}, "skipped": 0, "total_rows": 0}
    header, data = rows[0], rows[1:]
    cols = resolve_columns(header)
    return _rows_to_trades(data, cols)


def _rows_to_trades(data, cols):
    trades, skipped = [], 0
    for r in data:
        def cell(key):
            i = cols.get(key)
            return r[i] if (i is not None and i < len(r)) else None
        odt = parse_dt(cell("open_time"))
        pnl = parse_pnl(cell("pnl"))
        if odt is None or pnl is None:
            skipped += 1
            continue
        trades.append({
            "open_dt": odt,
            "close_dt": parse_dt(cell("close_time")),
            "symbol": (cell("symbol") or "?").strip() or "?",
            "pnl": pnl,
            "win": pnl > 0,
        })
    trades.sort(key=lambda t: t["open_dt"])
    return trades, {"cols": cols, "skipped": skipped, "total_rows": len(data)}


# ---------------------------------------------------------------- segmentación
def _bucket(trades):
    n = len(trades)
    if not n:
        return {"n": 0, "winrate": None, "pnl": 0.0, "mean": None}
    wins = sum(1 for t in trades if t["win"])
    pnl = sum(t["pnl"] for t in trades)
    return {"n": n, "winrate": wins / n, "pnl": pnl, "mean": pnl / n}


def _group(trades, keyfn):
    g = {}
    for t in trades:
        g.setdefault(keyfn(t), []).append(t)
    return {k: _bucket(v) for k, v in g.items()}


def session_of(hour):
    """Etiqueta de sesión aproximada por hora del timestamp (asume que la hora del
    CSV ya es la que le importa al trader; ver caveat en el reporte)."""
    if 7 <= hour < 13:
        return "Londres"
    if 13 <= hour < 22:
        return "Nueva York"
    return "Asia"


def _post_loss_reentries(trades, window_min=REENTRY_MIN):
    """Trades que abrieron dentro de `window` tras cerrar (o abrir) el trade previo,
    cuando ese previo fue PÉRDIDA. Es el 'revenge trade'. Devuelve (reentradas, resto)."""
    reentry, rest = [], []
    for i, t in enumerate(trades):
        if i == 0:
            rest.append(t)
            continue
        prev = trades[i - 1]
        ref = prev["close_dt"] or prev["open_dt"]
        gap = (t["open_dt"] - ref).total_seconds() / 60.0
        if prev["pnl"] < 0 and 0 <= gap <= window_min:
            reentry.append(t)
        else:
            rest.append(t)
    return reentry, rest


def analyze(trades, min_n=MIN_N):
    if not trades:
        return {"n": 0}
    overall = _bucket(trades)
    by_hour = _group(trades, lambda t: t["open_dt"].hour)
    by_weekday = _group(trades, lambda t: t["open_dt"].weekday())     # 0=lun
    by_session = _group(trades, lambda t: session_of(t["open_dt"].hour))
    by_symbol = _group(trades, lambda t: t["symbol"])

    reentry, rest = _post_loss_reentries(trades)
    revenge = {"reentry": _bucket(reentry), "resto": _bucket(rest)}

    # ventanas de vulnerabilidad: (día, sesión) con peor P&L y n>=min
    dow_sess = _group(trades, lambda t: (t["open_dt"].weekday(),
                                         session_of(t["open_dt"].hour)))
    vuln = sorted(((k, v) for k, v in dow_sess.items() if v["n"] >= min_n),
                  key=lambda kv: kv[1]["pnl"])[:3]
    strong = sorted(((k, v) for k, v in dow_sess.items() if v["n"] >= min_n),
                    key=lambda kv: kv[1]["pnl"], reverse=True)[:3]

    # costo de la indisciplina (honesto y acotado): pérdida NETA de las reentradas
    # revenge cuando sangran + pérdida de las ventanas de vulnerabilidad. NO es
    # "lo que ganarías siendo perfecto" — es lo que te cuestan tus peores contextos.
    revenge_cost = revenge["reentry"]["pnl"] if revenge["reentry"]["pnl"] < 0 else 0.0

    return {
        "n": overall["n"],
        "overall": overall,
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "by_session": by_session,
        "by_symbol": by_symbol,
        "revenge": revenge,
        "vulnerability": vuln,
        "strengths": strong,
        "revenge_cost": revenge_cost,
        "min_n": min_n,
    }


# ------------------------------------------------------------------- reporte
_WD = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _fmt_b(b):
    if not b["n"]:
        return "n=0"
    return "n=%-3d  %3.0f%% aciertos  P&L %+.1f  (media %+.2f)" % (
        b["n"], b["winrate"] * 100, b["pnl"], b["mean"])


def format_report(rep, meta=None):
    if not rep or rep.get("n", 0) == 0:
        return ("Sin trades legibles en el archivo. Revisa que tenga una columna de "
                "fecha de apertura y una de P&L (Profit / P&L / Ganancia).")
    L = []
    o = rep["overall"]
    L.append("PSICÓLOGO DE MERCADO · lectura de tus trades")
    L.append("=" * 52)
    if meta and meta.get("skipped"):
        L.append("(%d fila(s) ignoradas por falta de fecha o P&L)" % meta["skipped"])
    L.append("Total: %s" % _fmt_b(o))
    L.append("")

    # revenge / reentrada post-pérdida
    re, rest = rep["revenge"]["reentry"], rep["revenge"]["resto"]
    L.append("• Reentrada post-pérdida (dentro de %d min de cerrar en rojo)" % REENTRY_MIN)
    if re["n"] >= rep["min_n"]:
        delta = (re["mean"] or 0) - (rest["mean"] or 0)
        L.append("    reentrada: %s" % _fmt_b(re))
        L.append("    resto:     %s" % _fmt_b(rest))
        verdict = ("te CUESTA: tu media cae %+.2f cuando reentras dolido" % delta
                   if delta < 0 else
                   "no es tu fuga (aquí no te daña)")
        L.append("    → %s" % verdict)
    elif re["n"] > 0:
        L.append("    %s — muestra chica, aún NO concluyente" % _fmt_b(re))
    else:
        L.append("    no se detectó (o no hay fecha de cierre para medirla)")
    L.append("")

    # ventanas de vulnerabilidad / fortalezas
    L.append("• Ventanas de vulnerabilidad (día · sesión, n≥%d)" % rep["min_n"])
    if rep["vulnerability"]:
        for (wd, sess), b in rep["vulnerability"]:
            L.append("    %-9s %-11s %s" % (_WD[wd], sess, _fmt_b(b)))
    else:
        L.append("    aún sin suficientes trades por ventana para concluir")
    L.append("")
    L.append("• Tus fortalezas (día · sesión, n≥%d)" % rep["min_n"])
    if rep["strengths"]:
        for (wd, sess), b in rep["strengths"]:
            L.append("    %-9s %-11s %s" % (_WD[wd], sess, _fmt_b(b)))
    else:
        L.append("    aún sin suficientes trades por ventana para concluir")
    L.append("")

    # por símbolo (top y bottom por P&L)
    syms = sorted(rep["by_symbol"].items(), key=lambda kv: kv[1]["pnl"])
    if len(syms) > 1:
        L.append("• Por símbolo")
        for sym, b in (syms[:1] + syms[-1:] if len(syms) > 2 else syms):
            L.append("    %-10s %s" % (sym, _fmt_b(b)))
        L.append("")

    # costo de la indisciplina (honesto)
    if rep["revenge_cost"] < 0:
        L.append("Costo de la indisciplina (solo reentradas revenge): %+.1f" % rep["revenge_cost"])
        L.append("No es 'lo que ganarías siendo perfecto' — es lo que te cuesta ese")
        L.append("hábito puntual. El enemigo no es el mercado; y eso sí se arregla.")
    L.append("-" * 52)
    L.append("Nota: la hora se toma tal cual del CSV (si tu bróker guarda otra zona")
    L.append("horaria, las sesiones se corren). Sin muestra suficiente, no afirmamos.")
    return "\n".join(L)


# ------------------------------------------------------------------- demo/CLI
def _demo_trades(seed=0):
    import random
    rng = random.Random(seed)
    trades, t = [], datetime(2026, 1, 5, 8, 0, 0)
    for _ in range(240):
        t += timedelta(hours=rng.choice([1, 2, 3, 5, 20]))
        hour = t.hour
        # sesgo sintético: lunes noche pierde; NY de mañana gana
        base = 0.55 if 13 <= hour < 18 else (0.35 if t.weekday() == 0 and hour >= 22 else 0.48)
        win = rng.random() < base
        pnl = round(rng.uniform(20, 120) if win else -rng.uniform(20, 140), 1)
        close = t + timedelta(minutes=rng.choice([8, 15, 40, 90]))
        trades.append({"open_dt": t, "close_dt": close,
                       "symbol": rng.choice(["US100", "XAUUSD", "BTCUSD"]),
                       "pnl": pnl, "win": pnl > 0})
        # a veces reentra dolido tras perder (revenge sintético)
        if pnl < 0 and rng.random() < 0.5:
            t2 = close + timedelta(minutes=rng.choice([5, 12, 25]))
            p2 = round(-rng.uniform(20, 130) if rng.random() < 0.65 else rng.uniform(20, 90), 1)
            trades.append({"open_dt": t2, "close_dt": t2 + timedelta(minutes=20),
                           "symbol": "US100", "pnl": p2, "win": p2 > 0})
            t = t2
    trades.sort(key=lambda x: x["open_dt"])
    return trades


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="CSV de trades del broker")
    ap.add_argument("--min-n", type=int, default=MIN_N)
    ap.add_argument("--demo", action="store_true", help="datos sintéticos, sin archivo")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.demo:
        trades, meta = _demo_trades(), {"skipped": 0}
    elif args.file:
        trades, meta = load_trades(args.file)
    else:
        ap.error("da --file <csv> o --demo")

    rep = analyze(trades, min_n=args.min_n)
    if args.json:
        print(json.dumps(rep, default=str, indent=2))
    else:
        print(format_report(rep, meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
