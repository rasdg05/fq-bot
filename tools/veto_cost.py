# -*- coding: utf-8 -*-
"""
================================================================================
  veto_cost — ¿cuánto R dejó sobre la mesa cada veto?
================================================================================

Se mide lo que se abrió. De los fires SUPRIMIDOS no se sabía nada: ni cuántos,
ni por quién, ni qué habrían hecho. Así que "¿el veto de londres salva o cuesta?"
no tenía respuesta ni con un año de ledger — el contrafactual no existía.

Desde E2, `MOTOR_VETOED` sella la geometría (dirección/entry/stop/tp) y el vector
de features junto al motivo y al `stage` (quién lo suprimió). Con eso este informe
reprecia cada veto contra las velas que vinieron después y contesta la pregunta.

Lo que este informe NO hace
---------------------------
No decide. Un veto que "cuesta" R en la muestra puede seguir siendo correcto: los
vetos existen para cortar colas, y una cola no aparece en 40 observaciones. Por
eso cada línea trae su n y las de n<30 salen marcadas. Con muestra chica, ordenar
vetos por lo que costaron selecciona ruido — exactamente el error de mayo.

Tampoco reprecia contra un mundo consistente: si el veto no hubiera existido, la
posición habría ocupado riesgo y quizá bloqueado otra señal. Esto mide el R de la
señal suprimida aislada, que es una cota, no una simulación de cartera.

Uso:
    python tools/veto_cost.py [ruta_ledger] [--candles velas.parquet]
    python tools/veto_cost.py /data/motor_paper_SOL_USDT.jsonl
================================================================================
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution import DurableHashLedger

MIN_N = 30


def load_vetoes(path):
    """Fires suprimidos con geometría suficiente para repreciarse."""
    ledger = DurableHashLedger.load(path)     # verifica SHA-256 o LANZA
    out = []
    for r in ledger.records:
        p = r["payload"]
        if p.get("event") not in ("MOTOR_VETOED", "MOTOR_FILL_REJECTED"):
            continue
        p = dict(p)
        p.setdefault("stage", "segmento")     # filas previas a E2
        out.append(p)
    return out


def repriceable(vetoes):
    """Los que traen geometría. Los de antes de E2 no y hay que decirlo, no
    contarlos como cero."""
    return [v for v in vetoes
            if v.get("entry") is not None and v.get("stop") is not None
            and v.get("tp") is not None and v.get("direction") is not None]


def outcome_r(v, highs, lows):
    """R de la señal suprimida contra las velas siguientes, empate pesimista.

    Misma convención que `resolve_on_bar` y que el etiquetado de research: si TP
    y SL caen en la misma vela se cuenta como stop. Es la única regla honesta
    cuando no se conoce el orden intra-vela, y mantiene el contrafactual
    comparable con el ledger real en vez de darle un premio que el motor vivo no
    habría cobrado.
    """
    d = int(v["direction"])
    entry, stop, tp = float(v["entry"]), float(v["stop"]), float(v["tp"])
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    for hi, lo in zip(highs, lows):
        hit_sl = (lo <= stop) if d > 0 else (hi >= stop)
        hit_tp = (hi >= tp) if d > 0 else (lo <= tp)
        if hit_sl:
            return -1.0                       # empate incluido -> pesimista
        if hit_tp:
            return abs(tp - entry) / risk
    return None                               # sin resolver dentro de la ventana


def _fmt(rs, label):
    if not rs:
        return "  %-28s n=0" % label
    n = len(rs)
    mean = sum(rs) / n
    wr = sum(1 for r in rs if r > 0) / n * 100.0
    nota = "" if n >= MIN_N else "   <- n<%d, NO concluir" % MIN_N
    return "  %-28s n=%4d  E[R]=%+.3f  WR=%4.1f%%  total=%+.1fR%s" % (
        label, n, mean, wr, sum(rs), nota)


def report(vetoes, r_by_index=None):
    """Reparte el coste de los vetos por `stage` y por motivo."""
    print("=" * 70)
    print("  COSTE DE LOS VETOS — %d fires suprimidos" % len(vetoes))
    print("=" * 70)

    rep = repriceable(vetoes)
    ciegos = len(vetoes) - len(rep)
    if ciegos:
        print("\n  %d de %d son ANTERIORES a E2: sin geometría sellada no se pueden"
              % (ciegos, len(vetoes)))
        print("  repreciar. No cuentan como cero — no cuentan. Rotan fuera de la")
        print("  muestra según el motor siga corriendo.")

    print("\n=== ¿QUIÉN suprime? (cadencia por stage) ===")
    por_stage = {}
    for v in vetoes:
        por_stage.setdefault(v.get("stage", "?"), []).append(v)
    for st, vs in sorted(por_stage.items(), key=lambda kv: -len(kv[1])):
        print("  %-14s %4d fires (%4.1f%%)" % (st, len(vs), 100.0 * len(vs) / len(vetoes)))
    print("  (GHOST_MAP H7 sospechaba que el silencio del VIP es el stack de")
    print("   gates y no falta de setups. Esta tabla lo reparte entre culpables.)")

    if r_by_index is None:
        print("\n  Sin velas para repreciar: pasa --candles para el contrafactual.")
        print("  (la cadencia de arriba ya es medible sin ellas)")
        return

    print("\n=== ¿CUÁNTO R dejó cada veto sobre la mesa? ===")
    print("  (pesimista: empate TP/SL en la misma vela cuenta como stop)")
    rs_all = []
    for st, vs in sorted(por_stage.items()):
        rs = [r_by_index[id(v)] for v in vs if r_by_index.get(id(v)) is not None]
        rs_all += rs
        print(_fmt(rs, "stage=" + st))
    por_why = {}
    for v in rep:
        r = r_by_index.get(id(v))
        if r is not None:
            por_why.setdefault(str(v.get("why"))[:26], []).append(r)
    if por_why:
        print("  -- por motivo --")
        for why, rs in sorted(por_why.items(), key=lambda kv: sum(kv[1])):
            print(_fmt(rs, why))
    print(_fmt(rs_all, "TODOS los vetados"))
    if rs_all and len(rs_all) >= MIN_N and sum(rs_all) > 0:
        print("\n  >> En esta muestra los vetos CUESTAN R (lo suprimido era +EV).")
        print("     Antes de aflojarlos: un veto existe para cortar COLAS, y una")
        print("     cola no aparece en %d observaciones. Mira la peor racha, no" % len(rs_all))
        print("     solo la media.")
    elif rs_all and len(rs_all) >= MIN_N:
        print("\n  >> En esta muestra los vetos SALVAN R (lo suprimido era -EV).")


def main(argv=None):
    ap = argparse.ArgumentParser(description="¿Cuánto R cuesta cada veto?")
    ap.add_argument("ledger", nargs="?",
                    default=os.environ.get("FQ_MOTOR_PAPER_LEDGER_PATH",
                                           "/data/motor_paper_SOL_USDT.jsonl"))
    ap.add_argument("--candles", default=None,
                    help="parquet OHLC 5m para repreciar (ts,high,low)")
    ap.add_argument("--horizon", type=int, default=288,
                    help="velas de ventana para resolver el contrafactual")
    a = ap.parse_args(argv)

    if not os.path.exists(a.ledger):
        print("[veto-cost] no existe el ledger: %s" % a.ledger)
        return 2
    vetoes = load_vetoes(a.ledger)
    if not vetoes:
        print("[veto-cost] ningún fire suprimido en este ledger.")
        return 1

    r_by_index = None
    if a.candles:
        import pandas as pd
        df = pd.read_parquet(a.candles).sort_values("ts").reset_index(drop=True)
        ts = df["ts"].to_numpy()
        highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
        r_by_index = {}
        for v in repriceable(vetoes):
            i = int(ts.searchsorted(v.get("ts")))
            r_by_index[id(v)] = outcome_r(v, highs[i + 1:i + 1 + a.horizon],
                                          lows[i + 1:i + 1 + a.horizon])
    report(vetoes, r_by_index)
    return 0


if __name__ == "__main__":
    sys.exit(main())
