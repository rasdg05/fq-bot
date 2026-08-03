# -*- coding: utf-8 -*-
"""
================================================================================
  PM ANALYZE - el veredicto de la Fase 0
  by RasDG_Sol + Claude

  Lee los JSONL del probe y contesta, con numeros y sin optimismo: con $X de
  capital, ¿cuanto pagaria el market making en Polymarket, y en que mercados?

  Reglas duras que aplica (las de la plataforma, no las nuestras):
    · El pago minimo de rewards es $1/dia. Debajo de eso NO se cobra: cero.
    · Ordenes por debajo del min_size del mercado no califican.
    · Fuera del max_spread, la orden puntua cero.

  El reparto usa la MEDIANA de las muestras, no el promedio: un mercado que la
  mayor parte del tiempo esta saturado y se vacia un minuto no es una
  oportunidad, y el promedio se dejaria enganar por ese minuto.

  Uso:
    python -m pm.analyze --bankroll 500
    python -m pm.analyze --bankroll 500 --spread 0.5 --glob 'pm_data/*.jsonl'
================================================================================
"""
import os
import gzip
import json
import glob as globmod
import argparse
from collections import defaultdict
from statistics import median

from pm import rewards

# Pago minimo diario de los programas de rewards y rebates de Polymarket.
MIN_PAYOUT_USD = 1.0

# Tamano del bloque del reparto voraz, en USD.
ALLOC_CHUNK = 25.0

# Si el libro calificado estuvo vacio en esta fraccion de las muestras o mas, el
# estimado de ese mercado no es creible (nos daria casi todo el pool).
SUSPECT_ZERO_FRAC = 0.20

# Debajo de esto no hay veredicto que dar: son muestras, no evidencia.
MIN_SAMPLES = 100


def load(pattern: str) -> tuple:
    """Devuelve (config_por_mercado, muestras_por_mercado)."""
    cfg, samples = {}, defaultdict(list)
    for path in sorted(globmod.glob(pattern)):
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("_meta") == "markets":
                    for m in rec.get("markets") or []:
                        cfg[m["condition_id"]] = m
                    continue
                cid = rec.get("condition_id")
                if cid:
                    samples[cid].append(rec)
    return cfg, samples


def summarize_market(cid: str, cfg: dict, recs: list) -> dict:
    """Resumen robusto de un mercado: medianas sobre las muestras."""
    mids = [r["mid"] for r in recs if r.get("mid") is not None]
    qs = [r["book_q_min"] for r in recs if r.get("book_q_min") is not None]
    if not mids or not qs:
        return None
    meta = cfg.get(cid, {})
    return {
        "condition_id": cid,
        "slug":         meta.get("slug") or recs[-1].get("slug") or cid[:12],
        "question":     meta.get("question", ""),
        "n":            len(recs),
        "daily_pool":   recs[-1].get("daily_pool") or meta.get("daily_pool") or 0.0,
        "min_size":     recs[-1].get("min_size") or meta.get("min_size") or 0.0,
        "max_spread":   recs[-1].get("max_spread") or meta.get("max_spread") or 0.0,
        "mid":          median(mids),
        "book_q_min":   median(qs),
        # Fraccion de muestras SIN profundidad calificada. Un pool que nadie
        # reclama casi nunca es un regalo: suele ser un mercado por cerrar, un
        # min_size inalcanzable o un hueco momentaneo del libro. Con esto el
        # estimador no canta victoria por una division entre casi cero.
        "zero_frac":    sum(1 for q in qs if q <= 0) / len(qs),
        "qual_usd":     median([r.get("qual_bid_usd") or 0.0 for r in recs]),
        "ask_sum_min":  min([r["ask_sum"] for r in recs if r.get("ask_sum")] or [None]),
        "bid_sum_max":  max([r["bid_sum"] for r in recs if r.get("bid_sum")] or [None]),
    }


def market_yield(sm: dict, capital: float, spread_cents: float) -> dict:
    """Reward diario estimado si metemos `capital` en este mercado."""
    unit = rewards.capital_for_two_sided(1.0, sm["mid"], spread_cents)
    size = capital / unit if unit > 0 else 0.0
    oq = rewards.our_q_min(size, spread_cents, sm["mid"], sm["max_spread"], sm["min_size"])
    est = rewards.estimate_daily_reward(sm["daily_pool"], sm["book_q_min"], oq)
    return {"capital": capital, "size_shares": size, "our_q_min": oq,
            "est_daily": est, "qualifies": size >= sm["min_size"]}


def entry_cost(sm: dict, spread_cents: float) -> float:
    """Capital minimo para ENTRAR a un mercado: el que compra min_size shares a
    dos lados. Debajo de eso la orden no califica y el capital no puntua nada —
    no hay media entrada."""
    return sm["min_size"] * rewards.capital_for_two_sided(1.0, sm["mid"], spread_cents)


def allocate(summaries: list, bankroll: float, spread_cents: float,
             chunk: float = ALLOC_CHUNK) -> list:
    """Reparto voraz por reward marginal POR DOLAR.

    Es la forma honesta de repartir $500: los rewards son concavos en el capital
    (tu parte satura), asi que concentrar todo en el mejor mercado no es optimo,
    pero espolvorear en veinte tampoco: cada mercado tiene que cruzar solo el
    piso de $1/dia.

    El primer paso de cada mercado NO es un bloque cualquiera: tiene que llegar
    de golpe al min_size o la orden no califica. Por eso los pasos son de
    tamano distinto y se comparan por ganancia por dolar, no por ganancia bruta.
    """
    alloc = {s["condition_id"]: 0.0 for s in summaries}
    by_id = {s["condition_id"]: s for s in summaries}
    remaining = bankroll
    while remaining > 0:
        best, best_gain, best_step = None, 0.0, 0.0
        for cid, sm in by_id.items():
            step = chunk if alloc[cid] > 0 else max(chunk, entry_cost(sm, spread_cents))
            if step > remaining:
                continue
            cur = market_yield(sm, alloc[cid], spread_cents)["est_daily"] if alloc[cid] > 0 else 0.0
            nxt = market_yield(sm, alloc[cid] + step, spread_cents)
            if not nxt["qualifies"]:
                continue
            gain = (nxt["est_daily"] - cur) / step      # comparable entre pasos desiguales
            if gain > best_gain:
                best, best_gain, best_step = cid, gain, step
        if best is None:
            break
        alloc[best] += best_step
        remaining -= best_step

    out = []
    for cid, cap in alloc.items():
        if cap <= 0:
            continue
        y = market_yield(by_id[cid], cap, spread_cents)
        y.update({k: by_id[cid][k] for k in ("slug", "question", "daily_pool",
                                             "mid", "min_size", "max_spread",
                                             "book_q_min", "n", "zero_frac")})
        y["paid"] = y["est_daily"] >= MIN_PAYOUT_USD   # piso de pago de la plataforma
        # Estimado que NO se puede creer: el libro estaba vacio en buena parte
        # de las muestras, asi que la razon our_q/(book_q+our_q) tiende a 1.
        y["suspect"] = by_id[cid]["zero_frac"] >= SUSPECT_ZERO_FRAC
        out.append(y)
    out.sort(key=lambda x: -x["est_daily"])
    return out


def report(pattern: str, bankroll: float, spread_cents: float) -> dict:
    """Imprime el veredicto y devuelve el resumen."""
    cfg, samples = load(pattern)
    summaries = [s for s in (summarize_market(c, cfg, r) for c, r in samples.items()) if s]
    if not summaries:
        print("Sin datos. ¿Corrio el probe? (python -m pm.probe --once)")
        return {}

    n_samples = sum(s["n"] for s in summaries)
    print(f"\n{'='*78}")
    print(f"  FASE 0 — VEREDICTO   |   {len(summaries)} mercados, {n_samples} observaciones")
    print(f"  Capital ${bankroll:,.0f}   ·   cotizando a {spread_cents}¢ del midpoint")
    print(f"{'='*78}\n")

    alloc = allocate(summaries, bankroll, spread_cents)
    if not alloc:
        print("  Ningun mercado admite nuestro tamano minimo. Veredicto: NO.\n")
        return {"verdict": "no", "markets": []}

    print(f"  {'mercado':<34} {'cap$':>6} {'shares':>8} {'pool$':>7} {'est$/dia':>9}  estado")
    print(f"  {'-'*34} {'-'*6} {'-'*8} {'-'*7} {'-'*9}  ------")
    for a in alloc[:20]:
        estado = "DUDOSO" if a["suspect"] else ("cobra" if a["paid"] else "< $1")
        print(f"  {(a['slug'] or '')[:34]:<34} {a['capital']:>6.0f} {a['size_shares']:>8.0f} "
              f"{a['daily_pool']:>7.0f} {a['est_daily']:>9.3f}  {estado}")

    firmes = [a for a in alloc if a["paid"] and not a["suspect"]]
    dudosos = [a for a in alloc if a["suspect"]]
    total = sum(a["est_daily"] for a in alloc)
    payable = sum(a["est_daily"] for a in firmes)
    used = sum(a["capital"] for a in firmes)
    print()
    print(f"  Capital colocado (firme):     ${used:,.0f} de ${bankroll:,.0f}")
    print(f"  Estimado bruto (todo):        ${total:,.2f}/dia")
    print(f"  Estimado CREIBLE Y COBRABLE:  ${payable:,.2f}/dia  =  ${payable*30:,.2f}/mes")
    if used > 0:
        print(f"  Rendimiento sobre capital:    {payable*365/used*100:,.1f}% anual (solo rewards)")
    if dudosos:
        print()
        print(f"  ⚠ {len(dudosos)} mercado(s) DUDOSO(s): el libro calificado estuvo vacio en")
        print(f"    >={SUSPECT_ZERO_FRAC:.0%} de las muestras, asi que el estimador nos daria casi todo")
        print( "    el pool. Un pool que nadie reclama casi nunca es un regalo — suele ser")
        print( "    min_size inalcanzable o un mercado por cerrar. Excluidos del total.")
    print()

    asks = [s["ask_sum_min"] for s in summaries if s["ask_sum_min"]]
    bids = [s["bid_sum_max"] for s in summaries if s["bid_sum_max"]]
    if asks and bids:
        print(f"  Vigilante de arb: min(yes_ask+no_ask)={min(asks):.4f} · "
              f"max(yes_bid+no_bid)={max(bids):.4f}")
        n_arb = sum(1 for a in asks if a < 1.0)
        print(f"  Oportunidades de arb observadas: {n_arb}")
    print()

    if n_samples < MIN_SAMPLES:
        print(f"  NOTA: {n_samples} observaciones es muy poco para decidir (minimo {MIN_SAMPLES}).")
        print( "  Lo de abajo es una foto, no evidencia. Dejar correr el probe unos dias.\n")

    if payable <= 0:
        verdict = ("NO. Nada cruza el piso de $1/dia. El capital no alcanza para "
                   "competir con la profundidad que ya esta en el libro.")
    elif payable * 30 < 15:
        verdict = (f"MARGINAL. ${payable*30:,.0f}/mes no paga el riesgo operativo "
                   "ni el tiempo. Solo tiene sentido si es escalon a mas capital.")
    else:
        verdict = (f"VIABLE. ${payable*30:,.0f}/mes en rewards, ANTES de restar la "
                   "seleccion adversa. Pasar a Fase 1 con tamano minimo.")
    print(f"  >>> {verdict}\n")
    print("  Recordatorio: esto NO incluye el costo real del market making —")
    print("  te ejecutan cuando el precio se mueve en tu contra. Eso se mide en")
    print("  la Fase 2 con el replay, no aca.\n")

    return {"verdict": verdict, "est_daily": payable, "markets": alloc}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Veredicto de la Fase 0")
    ap.add_argument("--glob", default=os.path.join("pm_data", "*.jsonl*"))
    ap.add_argument("--bankroll", type=float, default=500.0)
    ap.add_argument("--spread", type=float, default=1.0, help="centavos del midpoint")
    args = ap.parse_args(argv)
    report(args.glob, args.bankroll, args.spread)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
