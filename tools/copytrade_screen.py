#!/usr/bin/env python3
"""copytrade_screen — ¿queda ALGUIEN copiable en el top de un leaderboard on-chain?

Detonante (2026-08-05): un vídeo de TikTok propone copiar "al insider de Trump" y
a las wallets más rentables. Preguntas de RasDG: ¿esa wallet es consistente? ¿no
usan varias? ¿cómo estar al tanto? Esto MIDE la primera y la tercera sobre la
población que un leaderboard bruto señala — que es exactamente a quien copiaría
alguien que siga el vídeo.

Tres filtros, en orden de coste (el más barato primero). Cada uno es una pregunta
que hay que responder ANTES de escribir un colector de copy-trading:

  1. ¿OPERA?      Cuentas sin un solo fill en la ventana. Un track record de por
                  vida no se copia; se copia lo que la wallet haga MAÑANA.
  2. ¿ES ALCANZABLE?  fills/día. Una cuenta que opera miles de veces al día no es
                  copiable con latencia y fees retail, gane lo que gane.
  3. I-7 CONCENTRACIÓN. Sobre las que pasan 1 y 2: PnL realizado NETO de fees por
                  trade de cierre, y qué queda al quitar el MEJOR trade. Si queda
                  <50%, el track record es n=1 — un volado, no un método.

La cohorte se congela ANTES de medir (invariante I-4) y la ventana es común y
cerrada para todas: dentro del experimento no se ordena por resultado.

Lo que este screen NO dice: que el copy-trading no tenga edge. Dice que el MÉTODO
de selección por leaderboard bruto apunta a cosas muertas, inalcanzables o n=1.
Ver internal/EXPERIMENT_COPYTRADE_ONCHAIN.md.

  python tools/copytrade_screen.py --self-test
  python tools/copytrade_screen.py --top 100 --days 30 --out /tmp/screen.json
"""
import argparse
import json
import sys
import time
import urllib.request

INFO_API = "https://api.hyperliquid.xyz/info"
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"

FILL_PAGE_CAP = 2000        # tope duro del endpoint userFillsByTime
COPYABLE_MAX_FILLS_DAY = 20.0
I7_MIN_REMAINING = 0.5

# ---------------------------------------------------------------------------
# Núcleo puro (sin red): es lo que fijan los tests.
# ---------------------------------------------------------------------------


def net_closed_pnls(fills):
    """PnL realizado NETO por trade de cierre.

    `closedPnl` de Hyperliquid es bruto; `fee` viene con signo (negativo = rebate
    de maker), así que el neto RESTA la fee. Solo cuentan los fills que cierran
    (closedPnl != 0): los de apertura no realizan nada.

    Sesgo conocido y declarado: la fee del fill de APERTURA no se imputa a este
    trade, y el funding tampoco. El neto que sale de aquí es OPTIMISTA — lo cual
    es la dirección correcta para un filtro de descarte (si falla siendo
    optimista, falla).
    """
    out = []
    for f in fills or []:
        try:
            cp = float(f.get("closedPnl", 0) or 0)
        except (TypeError, ValueError):
            continue
        if cp == 0:
            continue
        try:
            fee = float(f.get("fee", 0) or 0)
        except (TypeError, ValueError):
            fee = 0.0
        out.append(cp - fee)
    return out


def concentration(pnls):
    """(total, top, remaining_frac). remaining_frac None si el total no es > 0.

    remaining_frac = qué fracción del PnL sobrevive al quitar el MEJOR trade.
    """
    if not pnls:
        return 0.0, 0.0, None
    total = sum(pnls)
    top = max(pnls)
    if total <= 0:
        return total, top, None
    return total, top, (total - top) / total


def fails_i7(pnls, min_remaining=I7_MIN_REMAINING):
    """True si el track record es n=1: el mejor trade se lleva >50% del PnL.

    None si no es evaluable (sin cierres, o PnL no positivo — una cuenta que
    pierde no necesita I-7 para descartarse)."""
    _, _, rem = concentration(pnls)
    if rem is None:
        return None
    return rem < min_remaining


def fills_per_day(fills, window_days, page_cap=FILL_PAGE_CAP):
    """(tasa, es_cota_inferior).

    Si el lote llegó al tope del endpoint, el lote son los fills MÁS RECIENTES de
    la ventana: su propio span da la tasa vigente, que es cota INFERIOR de la
    real. Devolver una cota inferior es seguro aquí — solo puede subestimar lo
    inalcanzable que es la cuenta.
    """
    n = len(fills or [])
    if n == 0:
        return 0.0, False
    if n >= page_cap:
        span_ms = max(1, fills[-1]["time"] - fills[0]["time"])
        return n / (span_ms / 86400000.0), True
    return n / float(window_days), False


def classify(fills, window_days, max_fills_day=COPYABLE_MAX_FILLS_DAY):
    """Veredicto de una cuenta. Devuelve dict con la razón del descarte."""
    rate, lower_bound = fills_per_day(fills, window_days)
    rec = {"n_fills": len(fills or []), "fills_per_day": rate,
           "rate_is_lower_bound": lower_bound,
           "capped": len(fills or []) >= FILL_PAGE_CAP}
    if not fills:
        rec["verdict"] = "inactiva"
        return rec
    if rate >= max_fills_day:
        rec["verdict"] = "inalcanzable"
        return rec
    pnls = net_closed_pnls(fills)
    total, top, rem = concentration(pnls)
    rec.update({"n_closes": len(pnls), "pnl_net": total, "top_trade_net": top,
                "remaining_frac": rem})
    if rem is None:
        rec["verdict"] = "sin_pnl_positivo"
    elif rem < I7_MIN_REMAINING:
        rec["verdict"] = "falla_I7"
    else:
        rec["verdict"] = "candidata"
    return rec


def summarize(records):
    """Conteo por veredicto + el embudo, que es lo que se reporta."""
    order = ["inactiva", "inalcanzable", "sin_pnl_positivo", "falla_I7", "candidata"]
    counts = {k: 0 for k in order}
    for r in records:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    n = len(records)
    return {"n": n, "by_verdict": counts,
            "candidatas": counts["candidata"],
            "tasa_supervivencia": (counts["candidata"] / n) if n else 0.0}


# ---------------------------------------------------------------------------
# Envoltura de red
# ---------------------------------------------------------------------------


def _post(payload, retries=4, timeout=40):
    body = json.dumps(payload).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                INFO_API, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def _window_perf(row, window):
    for w, d in row.get("windowPerformances", []):
        if w == window:
            return d
    return {}


def freeze_cohort(top_n, timeout=120):
    """Congela la cohorte AHORA (I-4) y la devuelve con su sello temporal."""
    with urllib.request.urlopen(LEADERBOARD, timeout=timeout) as r:
        rows = json.load(r)["leaderboardRows"]
    ranked = sorted(rows,
                    key=lambda x: float(_window_perf(x, "allTime").get("pnl", 0)),
                    reverse=True)[:top_n]
    return {
        "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": LEADERBOARD,
        "universe_size": len(rows),
        "selection": "top {} por pnl allTime".format(top_n),
        "rows": ranked,
    }


def run(top_n=100, window_days=30, pace_s=1.1, log=print):
    cohort = freeze_cohort(top_n)
    end = int(time.time() * 1000) - 3600 * 1000   # 1h de guarda: ventana cerrada
    start = end - window_days * 86400 * 1000
    log("cohorte congelada: top {} de {} @ {}".format(
        top_n, cohort["universe_size"], cohort["frozen_at_utc"]))

    records = []
    for i, row in enumerate(cohort["rows"]):
        addr = row["ethAddress"]
        try:
            fills = _post({"type": "userFillsByTime", "user": addr,
                           "startTime": start, "endTime": end})
        except Exception as e:
            log("  ! {} fallo: {}".format(addr, str(e)[:60]))
            continue
        rec = classify(fills, window_days)
        rec["addr"] = addr
        rec["pnl_alltime_lb"] = float(_window_perf(row, "allTime").get("pnl", 0))
        rec["pnl_month_lb"] = float(_window_perf(row, "month").get("pnl", 0))
        records.append(rec)
        time.sleep(pace_s)
        if (i + 1) % 25 == 0:
            log("  ...{}/{}".format(i + 1, top_n))

    return {"cohort": {k: v for k, v in cohort.items() if k != "rows"},
            "window": {"start_ms": start, "end_ms": end, "days": window_days},
            "records": records, "summary": summarize(records)}


# ---------------------------------------------------------------------------


def _self_test():
    # net: resta la fee con signo (negativa = rebate -> sube el neto)
    fills = [{"closedPnl": "100", "fee": "2"}, {"closedPnl": "0", "fee": "1"},
             {"closedPnl": "50", "fee": "-1"}]
    assert net_closed_pnls(fills) == [98.0, 51.0], net_closed_pnls(fills)

    # concentracion: un volado falla, un reparto pasa
    assert fails_i7([100.0, 5.0, 5.0]) is True
    assert fails_i7([10.0, 10.0, 10.0]) is False
    assert fails_i7([]) is None
    assert fails_i7([-5.0, 1.0]) is None          # PnL no positivo -> no evaluable

    # frontera exacta del 50%
    assert fails_i7([50.0, 50.0]) is False        # resto = 50% -> NO falla
    assert fails_i7([51.0, 49.0]) is True         # resto = 49% -> falla

    # tasa: lote capado -> cota inferior desde el span del propio lote
    capped = [{"time": 0}, {"time": 43200000}] * 1000   # 2000 fills en 12h
    rate, lb = fills_per_day(capped, 30)
    assert lb is True and abs(rate - 4000.0) < 1e-6, rate
    rate, lb = fills_per_day([{"time": 0}] * 60, 30)
    assert lb is False and abs(rate - 2.0) < 1e-9, rate
    assert fills_per_day([], 30) == (0.0, False)

    # embudo
    assert classify([], 30)["verdict"] == "inactiva"
    assert classify(capped, 30)["verdict"] == "inalcanzable"
    assert classify([{"time": 0, "closedPnl": "100", "fee": "0"},
                     {"time": 1, "closedPnl": "1", "fee": "0"}],
                    30)["verdict"] == "falla_I7"
    s = summarize([{"verdict": "inactiva"}, {"verdict": "candidata"}])
    assert s["candidatas"] == 1 and abs(s["tasa_supervivencia"] - 0.5) < 1e-9
    print("self-test OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--pace", type=float, default=1.1,
                    help="segundos entre requests (presupuesto: 1200 peso/min)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        _self_test()
        return 0

    res = run(top_n=a.top, window_days=a.days, pace_s=a.pace)
    s = res["summary"]
    print("\nembudo sobre {} cuentas:".format(s["n"]))
    for k, v in s["by_verdict"].items():
        print("  {:<18} {:>4}".format(k, v))
    print("  -> candidatas: {}/{} ({:.0%})".format(
        s["candidatas"], s["n"], s["tasa_supervivencia"]))
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(res, fh, indent=1)
        print("\nescrito {}".format(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
