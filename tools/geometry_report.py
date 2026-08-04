# -*- coding: utf-8 -*-
"""
================================================================================
  GEOMETRY REPORT — juzgar el TP y el SL con el RECORRIDO, no con el desenlace
================================================================================

El ledger sellaba donde SALIO cada trade, no hasta donde LLEGO. Con eso se puede
decir "perdio", pero no POR QUE: si el TP estaba demasiado lejos, si el SL
demasiado cerca, o si la senal no separa y ninguna geometria la salva. Son tres
enfermedades con el mismo sintoma y tratamientos opuestos.

Desde que execution.PaperBroker sella mfe_r / mae_r / bars_held en cada CLOSE,
esa pregunta es contestable. Este informe la contesta.

Las cuatro lecturas
-------------------
1. TP DEMASIADO LEJOS. Perdedores cuyo MFE supero un umbral: llegaron a estar
   bien y volvieron. Si muchos stops tuvieron MFE >= 1R, el problema es que no
   se recoge, no que la senal falle.
2. SL DEMASIADO CERCA. Ganadores cuyo MAE fue profundo: aguantaron un viaje en
   contra antes de funcionar. Si los ganadores rutinariamente tocan -0.7R, un
   stop un poco mas ancho convierte perdedores en ganadores... a costa de
   agrandar la perdida cuando falla. El informe cuantifica ese intercambio en
   vez de opinar.
3. TECHO REAL. Distribucion del MFE: si casi ningun trade llega nunca al TP
   actual, el TP es una fantasia y hay que bajarlo al percentil que se alcanza.
4. SEPARACION. Si el MFE de ganadores y perdedores se distribuye IGUAL, la
   senal no distingue y ninguna geometria arregla eso. Es la lectura que mas
   duele y la que mas hay que mirar.

Contrafactuales
---------------
Reprecia cada trade bajo TP/SL alternativos usando el recorrido observado. OJO
con su alcance: es una aproximacion de COTA, no una simulacion. Dentro de una
vela no se conoce el orden de los extremos, asi que un trade cuyo MFE y MAE
crucen ambos umbrales se cuenta como PERDEDOR (pesimista, misma convencion que
resolve_on_bar). Y reprecia sobre los trades QUE SE TOMARON: no dice nada de los
que otra geometria habria abierto o evitado.

Uso:
    python tools/geometry_report.py [--db /data/fq_motor.db] [--symbol SOL/USDT]
    python tools/geometry_report.py --jsonl /data/motor_paper_SOL_USDT.jsonl
================================================================================
"""
import argparse
import json
import os
import sqlite3
import sys

# Umbral de muestra por debajo del cual NO se concluye nada. Mismo criterio que
# el resto del repo: con menos, ordenar por resultado selecciona ruido.
MIN_N = 30


def _pct(xs, q):
    """Percentil q (0..100) sin numpy, interpolando."""
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def load_closes(db_path=None, jsonl_path=None, symbol=None):
    """Cierres con recorrido sellado. Acepta el SQLite multi-simbolo o el JSONL."""
    out = []
    if jsonl_path:
        with open(jsonl_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    p = json.loads(line).get("payload", {})
                except ValueError:
                    continue
                if p.get("event") == "CLOSE" and p.get("mfe_r") is not None:
                    out.append(p)
        return out

    conn = sqlite3.connect(db_path)
    q = "SELECT symbol, payload FROM motor_ledger"
    args = ()
    if symbol:
        q += " WHERE symbol = ?"
        args = (symbol,)
    q += " ORDER BY symbol, seq"
    for sym, payload in conn.execute(q, args):
        p = json.loads(payload)
        if p.get("event") == "CLOSE" and p.get("mfe_r") is not None:
            p["symbol"] = sym
            out.append(p)
    conn.close()
    return out


def _note(n):
    return "" if n >= MIN_N else "   <- n<%d, NO concluir" % MIN_N


def report_distribution(closes):
    print("\n=== RECORRIDO (en R de precio) ===")
    wins = [c for c in closes if c["pnl_r"] > 0]
    loss = [c for c in closes if c["pnl_r"] <= 0]
    print("%-12s %4s %8s %8s %8s %8s" % ("grupo", "n", "MFE p50", "MFE p75", "MFE p90", "MAE p50"))
    for nm, grp in (("todos", closes), ("ganadores", wins), ("perdedores", loss)):
        if not grp:
            continue
        mfe = [c["mfe_r"] for c in grp]
        mae = [c["mae_r"] for c in grp]
        print("%-12s %4d %8.2f %8.2f %8.2f %8.2f%s" % (
            nm, len(grp), _pct(mfe, 50), _pct(mfe, 75), _pct(mfe, 90),
            _pct(mae, 50), _note(len(grp))))

    # 4. SEPARACION: solapamiento del MFE entre ganadores y perdedores.
    if wins and loss:
        mw, ml = _mean([c["mfe_r"] for c in wins]), _mean([c["mfe_r"] for c in loss])
        print("\n  MFE medio  ganadores %+.2fR  vs  perdedores %+.2fR" % (mw, ml))
        if abs(mw - ml) < 0.25:
            print("  >> Se solapan. La senal NO separa por recorrido: ninguna")
            print("     geometria de TP/SL arregla esto. El problema es la entrada.")
        else:
            print("  >> Separan. Hay margen para que la geometria capture mas.")


def report_tp_too_far(closes):
    print("\n=== 1. EL TP, DEMASIADO LEJOS? (perdedores que llegaron a estar bien) ===")
    loss = [c for c in closes if c["pnl_r"] <= 0]
    if not loss:
        return
    print("  de %d perdedores:%s" % (len(loss), _note(len(loss))))
    for thr in (0.5, 1.0, 1.5, 2.0):
        k = sum(1 for c in loss if c["mfe_r"] >= thr)
        print("    MFE >= %.1fR : %3d (%4.0f%%)" % (thr, k, 100.0 * k / len(loss)))
    k1 = sum(1 for c in loss if c["mfe_r"] >= 1.0)
    if len(loss) >= MIN_N and k1 / len(loss) > 0.35:
        print("  >> Mas de un tercio de las perdidas estuvo >= +1R a favor.")
        print("     Recoger antes (TP mas cerca o parcial) cambia el resultado.")


def report_sl_too_tight(closes):
    print("\n=== 2. EL SL, DEMASIADO CERCA? (ganadores que sufrieron primero) ===")
    wins = [c for c in closes if c["pnl_r"] > 0]
    if not wins:
        return
    mae = [c["mae_r"] for c in wins]
    print("  de %d ganadores:%s" % (len(wins), _note(len(wins))))
    print("    MAE p50 %.2fR | p75 %.2fR | p90 %.2fR | peor %.2fR" % (
        _pct(mae, 50), _pct(mae, 25), _pct(mae, 10), min(mae)))
    deep = sum(1 for m in mae if m <= -0.7)
    print("    ganadores que llegaron a -0.7R o peor: %d (%.0f%%)" % (
        deep, 100.0 * deep / len(wins)))
    if len(wins) >= MIN_N and deep / len(wins) > 0.3:
        print("  >> Muchos ganadores rozan el stop. Ensancharlo los salvaria,")
        print("     pero agranda cada perdida: mira el contrafactual antes de tocarlo.")


def _replay_one(c, tp, sl):
    """Reprecia UN trade bajo (tp, sl) usando el recorrido y el ORDEN de barras.

    MFE/MAE por si solos no bastan: un trade que llego a +2R y luego murio en el
    stop se contaria como perdedor bajo un TP de +1R, cuando en realidad habria
    salido en TP ANTES de que el stop llegara a existir. `mfe_bar`/`mae_bar`
    desambiguan ese orden.

    Reglas, de mas informada a mas conservadora:
      1. Solo se cruza un umbral -> ese decide.
      2. Se cruzan ambos en barras DISTINTAS -> gana el que ocurrio antes.
      3. Se cruzan ambos en la MISMA barra (o falta el indice) -> pesimista:
         perdedor. Dentro de una vela el orden es genuinamente desconocido.
    """
    hit_tp = c["mfe_r"] >= tp
    hit_sl = c["mae_r"] <= -sl
    if hit_tp and hit_sl:
        bt, bs = c.get("mfe_bar"), c.get("mae_bar")
        if bt is None or bs is None or bt == bs:
            return -sl                      # ambiguo -> peor caso
        return tp if bt < bs else -sl
    if hit_sl:
        return -sl
    if hit_tp:
        return tp
    # Ninguno: el trade salio por otra via (timeout). Se acota su R realizada
    # a la nueva geometria.
    return max(min(c["pnl_r"], tp), -sl)


def counterfactual(closes, tps, sls):
    print("\n=== CONTRAFACTUAL: repreciando el MISMO set con otra geometria ===")
    amb = sum(1 for c in closes if c.get("mfe_bar") is None)
    print("    (orden resuelto por barra; empate intra-vela -> perdedor)")
    if amb:
        print("    OJO: %d de %d cierres sin indice de barra -> se juzgan siempre"
              % (amb, len(closes)))
        print("    en el peor caso. Son trades anteriores a la instrumentacion;")
        print("    sesgan la tabla a la baja hasta que roten fuera de la muestra.")
    base = sum(c["pnl_r"] for c in closes) / len(closes)
    print("    E[R] realizada actual: %+.3f  (n=%d)\n" % (base, len(closes)))
    print("    %-8s" % "TP\\SL" + "".join("%9.2f" % s for s in sls))
    for tp in tps:
        row = "    %-8.2f" % tp
        for sl in sls:
            tot = sum(_replay_one(c, tp, sl) for c in closes)
            row += "%9.3f" % (tot / len(closes))
        print(row)
    print("\n    Lee la celda como E[R] BRUTA en R del SL original, sin fees.")
    print("    Un SL mas ancho arriesga mas capital por trade: compara a riesgo")
    print("    igual, no celda contra celda.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Informe de geometria TP/SL desde el recorrido")
    ap.add_argument("--db", default=os.environ.get("FQ_MOTOR_DB", "/data/fq_motor.db"))
    ap.add_argument("--jsonl", default=None)
    ap.add_argument("--symbol", default=None)
    a = ap.parse_args(argv)

    closes = load_closes(db_path=a.db, jsonl_path=a.jsonl, symbol=a.symbol)
    if not closes:
        print("Sin cierres con recorrido sellado todavia.")
        print("El campo mfe_r se sella desde la instrumentacion de ago-2026: los")
        print("trades anteriores no lo tienen y este informe no puede juzgarlos.")
        return 1

    print("=" * 66)
    print("  GEOMETRIA TP/SL — %d cierres con recorrido%s" % (
        len(closes), (" [%s]" % a.symbol) if a.symbol else ""))
    print("=" * 66)
    report_distribution(closes)
    report_tp_too_far(closes)
    report_sl_too_tight(closes)
    counterfactual(closes, tps=[0.5, 1.0, 1.5, 2.0, 3.0], sls=[0.5, 0.75, 1.0, 1.5])
    print("\nRecordatorio: esto reprecia los trades QUE SE TOMARON. No dice nada")
    print("de los que otra geometria habria abierto o evitado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
