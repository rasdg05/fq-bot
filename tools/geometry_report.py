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

Dos fuentes, DOS DEFINICIONES (no se promedian)
-----------------------------------------------
El ledger vivo mide el recorrido sobre la VIDA REAL del trade: deja de mirar
cuando la posicion se cierra. El cube (`cosecha_cubes/*.parquet`) lo mide sobre
el HORIZONTE ENTERO de la etiqueta triple-barrera — sigue acumulando MFE/MAE
DESPUES de que la barrera resolvio (ver bt_labeler.label_event_grid: mfe_cum se
acumula hasta `h`, no hasta `bars_held`). Es la misma forma del fantasma de
julio: credito por un recorrido posterior a la muerte de la senal.

No son la misma medida y **no se mezclan**: `excursion_scope()` levanta si un
informe recibe cierres de las dos. Cada lectura declara para que scope vale.

Uso:
    python tools/geometry_report.py [--db /data/fq_motor.db] [--symbol SOL/USDT]
    python tools/geometry_report.py --jsonl /data/motor_paper_SOL_USDT.jsonl
    python tools/geometry_report.py --cube cosecha_cubes/ [--tp tp4] [--horizon 288]
================================================================================
"""
import argparse
import glob
import json
import os
import random
import sqlite3
import sys

# Umbral de muestra por debajo del cual NO se concluye nada. Mismo criterio que
# el resto del repo: con menos, ordenar por resultado selecciona ruido.
MIN_N = 30

# Scope del recorrido. La clave viaja EN cada cierre para que ninguna funcion
# pueda promediar por accidente dos definiciones distintas.
SCOPE_KEY = "excursion_scope"
SCOPE_LIFE = "life"          # ledger: hasta que el trade cerro
SCOPE_HORIZON = "horizon"    # cube: hasta el final del horizonte de la etiqueta


class MixedScopeError(ValueError):
    """Cierres con definiciones de recorrido distintas en el mismo informe."""


def excursion_scope(closes):
    """Scope unico del lote, o levanta. Es la invariante de E7: el MFE/MAE del
    cube (horizonte) y el del ledger (vida) responden preguntas distintas; si
    alguien los junta, el informe miente sin avisar.
    """
    scopes = {c.get(SCOPE_KEY, SCOPE_LIFE) for c in closes}
    if len(scopes) > 1:
        raise MixedScopeError(
            "recorridos de scope distinto en el mismo lote: %s. El del cube se "
            "mide sobre el horizonte de la etiqueta y el del ledger sobre la "
            "vida real del trade: no son comparables ni promediables."
            % sorted(scopes))
    return scopes.pop() if scopes else SCOPE_LIFE


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
                    p[SCOPE_KEY] = SCOPE_LIFE
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
            p[SCOPE_KEY] = SCOPE_LIFE
            out.append(p)
    conn.close()
    return out


def load_cube_closes(paths, tp="tp4", horizon=288, symbol=None):
    """Las mismas lecturas, pero sobre las senales etiquetadas del cube.

    `paths` es un directorio, un glob o una lista de parquets. Se toma UNA celda
    (tp, horizon) — el cube es largo: una fila por (evento x tp x horizonte), y
    sumarlas contaria cada senal 12 veces. Dentro de la celda se deduplica por
    (symbol, entry_ts), que es el criterio de "senal canonica" del GHOST_MAP.

    El recorrido que sale de aqui es scope=horizon (ver cabecera). No trae orden
    de barra: el cube guarda el maximo y el minimo del tramo, no cuando ocurrio
    cada uno, asi que todo contrafactual sobre el sale por la regla pesimista.
    """
    import pandas as pd

    if isinstance(paths, str):
        paths = sorted(glob.glob(os.path.join(paths, "*.parquet")
                                 if os.path.isdir(paths) else paths))
    out = []
    for path in paths:
        sym = os.path.basename(path).split("tp_cube_")[-1].replace(".parquet", "")
        if symbol and sym != symbol:
            continue
        c = pd.read_parquet(path)
        c = c[(c["tp"].astype(str) == tp) & (c["horizon"].astype(int) == int(horizon))]
        c = c.drop_duplicates(subset=["entry_ts"])
        for r in c.itertuples(index=False):
            if r.mfe_r is None or r.mae_r is None:
                continue
            out.append({
                "event": "CLOSE",
                "symbol": sym,
                "entry_ts": str(r.entry_ts),
                "direction": int(r.direction),
                "pnl_r": float(r.pnl_r),
                "mfe_r": float(r.mfe_r),
                "mae_r": float(r.mae_r),
                "bars_held": int(r.bars_held),
                # mfe_bar/mae_bar AUSENTES a proposito: el cube no los tiene.
                SCOPE_KEY: SCOPE_HORIZON,
                "horizon": int(horizon),
                "tp_label": tp,
            })
    return out


def _note(n):
    return "" if n >= MIN_N else "   <- n<%d, NO concluir" % MIN_N


def scope_banner(closes):
    """Que mide el recorrido de este lote, dicho antes de cualquier numero."""
    sc = excursion_scope(closes)
    if sc == SCOPE_HORIZON:
        hs = sorted({c.get("horizon") for c in closes if c.get("horizon")})
        print("\n[scope=horizonte] El MFE/MAE se acumula sobre las %s velas de la"
              % ("/".join(str(h) for h in hs) or "?"))
        print("  etiqueta, TAMBIEN despues de que la barrera resolvio el trade.")
        print("  NO es el recorrido del ledger (que para al cerrar): las lecturas 1")
        print("  y 2 de abajo son COTAS SUPERIORES, y los dos numeros no se promedian.")
    else:
        print("\n[scope=vida] El MFE/MAE va desde la apertura hasta el cierre real.")
    return sc


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
        print("  OJO: 'ganador' significa que el precio TOCO el TP, o sea que su MFE")
        print("  es >= la distancia al TP por construccion. Esta comparacion esta")
        print("  mecanicamente sesgada a separar; el juez honesto es la seccion 4.")


def _boot_mean_ci(xs, reps=2000, seed=7, alpha=5.0):
    """IC bootstrap de la media (percentil) + P(media>0). Sin scipy, como el gate."""
    rnd = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(reps):
        s = 0.0
        for _ in range(n):
            s += xs[rnd.randrange(n)]
        means.append(s / n)
    means.sort()
    return (_pct(means, alpha / 2.0), _pct(means, 100.0 - alpha / 2.0),
            sum(1 for m in means if m > 0) / float(reps))


def report_separation(closes, reps=2000, seed=7):
    """4. LA LECTURA QUE MAS IMPORTA — ¿el lado elegido separa, o es un volado?

    Comparar el MFE de ganadores contra el de perdedores no vale: el desenlace
    se DEFINE por cruzar el TP, asi que los ganadores tienen MFE alto por
    construccion. El contraste honesto es contra la senal INVERTIDA: tomar el
    lado contrario en la misma vela, con la misma distancia de riesgo, cambia el
    recorrido de sitio — lo que era favorable pasa a ser adverso. Es decir
    mfe' = -mae y mae' = -mfe, y el estadistico por senal se reduce a

        asimetria = mfe_r + mae_r

    positivo si el tape se movio mas a favor que en contra. Cero = volado. No
    depende del TP ni del SL, asi que responde "¿la ENTRADA vale algo?" separado
    de "¿la geometria la cobra?" — que es justo la ambiguedad de las tres
    enfermedades. Se reporta con IC bootstrap y desglosado por lado, porque un
    solo lado positivo por deriva del mercado no es senal (H1).
    """
    print("\n=== 4. ¿SEPARA LA ENTRADA? (recorrido vs. la senal invertida) ===")
    if not closes:
        return None
    asym = [c["mfe_r"] + c["mae_r"] for c in closes]
    lo, hi, p = _boot_mean_ci(asym, reps=reps, seed=seed)
    print("  asimetria = MFE + MAE  (>0 = el tape fue mas a favor que en contra)")
    print("  todos   n=%5d  media %+.3fR  IC95%%[%+.3f, %+.3f]  P(>0)=%.3f%s"
          % (len(asym), _mean(asym), lo, hi, p, _note(len(asym))))
    for d, lab in ((1, "long"), (-1, "short")):
        grp = [c["mfe_r"] + c["mae_r"] for c in closes if c.get("direction") == d]
        if not grp:
            continue
        l2, h2, p2 = _boot_mean_ci(grp, reps=reps, seed=seed)
        print("  %-7s n=%5d  media %+.3fR  IC95%%[%+.3f, %+.3f]  P(>0)=%.3f%s"
              % (lab, len(grp), _mean(grp), l2, h2, p2, _note(len(grp))))
    if len(asym) < MIN_N:
        return _mean(asym)
    if lo > 0:
        print("  >> SEPARA. El recorrido es asimetrico a favor del lado elegido:")
        print("     invertir la senal habria dado la asimetria opuesta. El problema")
        print("     NO es la entrada -> es geometria y/o coste (ver E8).")
    elif hi < 0:
        print("  >> SEPARA AL REVES. El lado elegido es el peor de los dos.")
    else:
        print("  >> NO separa: el IC95%% cruza cero. Es un volado y ninguna")
        print("     geometria de TP/SL arregla eso. El trabajo esta en la entrada.")
    print("  (bruto y sobre el recorrido: dice que el movimiento EXISTE, no que")
    print("   una orden real lo capture. Eso lo contesta el coste, no el tape.)")
    return _mean(asym)


def report_tp_too_far(closes):
    print("\n=== 1. EL TP, DEMASIADO LEJOS? (perdedores que llegaron a estar bien) ===")
    loss = [c for c in closes if c["pnl_r"] <= 0]
    if not loss:
        return
    horizon_scope = excursion_scope(closes) == SCOPE_HORIZON
    print("  de %d perdedores:%s" % (len(loss), _note(len(loss))))
    for thr in (0.5, 1.0, 1.5, 2.0):
        k = sum(1 for c in loss if c["mfe_r"] >= thr)
        print("    MFE >= %.1fR : %3d (%4.0f%%)" % (thr, k, 100.0 * k / len(loss)))
    k1 = sum(1 for c in loss if c["mfe_r"] >= 1.0)
    if horizon_scope:
        print("  COTA SUPERIOR: con scope=horizonte, parte de ese MFE ocurrio DESPUES")
        print("  de que el stop cerrara el trade. Un TP mas cerca no lo habria")
        print("  cobrado: la senal ya estaba muerta. No leas esto como 'se sale tarde'.")
        return
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
    if excursion_scope(closes) == SCOPE_HORIZON:
        print("  COTA SUPERIOR: con scope=horizonte el MAE incluye lo que paso DESPUES")
        print("  de tocar el TP. Ensanchar el stop no salva a quien ya habia cobrado.")
        return
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


def _ambiguous_frac(closes, tp, sl):
    """Fraccion de la celda que cae en la regla pesimista por falta de orden."""
    k = sum(1 for c in closes
            if c["mfe_r"] >= tp and c["mae_r"] <= -sl
            and (c.get("mfe_bar") is None or c.get("mae_bar") is None
                 or c["mfe_bar"] == c["mae_bar"]))
    return k / float(len(closes))


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
    worst = 0.0
    for tp in tps:
        row = "    %-8.2f" % tp
        for sl in sls:
            tot = sum(_replay_one(c, tp, sl) for c in closes)
            worst = max(worst, _ambiguous_frac(closes, tp, sl))
            row += "%9.3f" % (tot / len(closes))
        print(row)
    print("\n    Lee la celda como E[R] BRUTA en R del SL original, sin fees.")
    print("    Un SL mas ancho arriesga mas capital por trade: compara a riesgo")
    print("    igual, no celda contra celda.")
    print("    Ambiguedad maxima de la tabla: %.0f%% de las filas cruzan AMBOS"
          % (100.0 * worst))
    print("    umbrales sin orden conocido -> se cuentan como perdedoras.")
    if worst > 0.5:
        print("    >> La tabla es una COTA INFERIOR VACIA: con esa ambiguedad casi")
        print("       toda celda colapsa a -SL. No la leas como 'esta geometria")
        print("       pierde'; leela como 'este dato no puede juzgar geometrias'.")
        print("       Para juzgarlas hace falta el orden de barra (ledger vivo o")
        print("       re-etiquetar el cube sellando mfe_bar/mae_bar).")
    return worst


def main(argv=None):
    ap = argparse.ArgumentParser(description="Informe de geometria TP/SL desde el recorrido")
    ap.add_argument("--db", default=os.environ.get("FQ_MOTOR_DB", "/data/fq_motor.db"))
    ap.add_argument("--jsonl", default=None)
    ap.add_argument("--cube", default=None,
                    help="directorio o glob de cosecha_cubes/*.parquet")
    ap.add_argument("--tp", default="tp4", help="celda de TP del cube")
    ap.add_argument("--horizon", type=int, default=288, help="horizonte del cube")
    ap.add_argument("--symbol", default=None)
    a = ap.parse_args(argv)

    if a.cube:
        closes = load_cube_closes(a.cube, tp=a.tp, horizon=a.horizon,
                                  symbol=a.symbol)
        origen = "cube %s/h%d" % (a.tp, a.horizon)
    else:
        closes = load_closes(db_path=a.db, jsonl_path=a.jsonl, symbol=a.symbol)
        origen = "ledger"
    if not closes:
        print("Sin cierres con recorrido sellado todavia.")
        print("El campo mfe_r se sella desde la instrumentacion de ago-2026: los")
        print("trades anteriores no lo tienen y este informe no puede juzgarlos.")
        return 1

    print("=" * 66)
    print("  GEOMETRIA TP/SL — %d senales con recorrido [%s]%s" % (
        len(closes), origen, (" [%s]" % a.symbol) if a.symbol else ""))
    print("=" * 66)
    scope_banner(closes)
    report_distribution(closes)
    report_tp_too_far(closes)
    report_sl_too_tight(closes)
    report_separation(closes)
    counterfactual(closes, tps=[0.5, 1.0, 1.5, 2.0, 3.0], sls=[0.5, 0.75, 1.0, 1.5])
    print("\nRecordatorio: esto reprecia los trades QUE SE TOMARON. No dice nada")
    print("de los que otra geometria habria abierto o evitado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
