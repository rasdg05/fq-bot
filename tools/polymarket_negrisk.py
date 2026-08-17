# -*- coding: utf-8 -*-
"""
Coherencia de conjunto completo (`neg_risk`) — paso 4, el último mecanismo vivo.

El paso 3 mató la recalibración: no le ganamos al precio del venue con un mapa
`f(p_mercado)`. Quedaban dos mecanismos que **no** requieren ser más listo que el
mercado. Éste es el primero, y es el más limpio de los dos porque **no necesita
modelo de nada**:

En un evento `neg_risk` los resultados son mutuamente excluyentes y exhaustivos —
exactamente uno ocurre. Por lo tanto **ΣP(YES) sobre todas las patas debe ser 1**.

    Σp > 1  →  comprar NO en TODAS las patas paga (Σp − 1)
    Σp < 1  →  comprar YES en TODAS las patas paga (1 − Σp)

Verificado en el dato antes de medir nada: de 38,502 eventos cerrados con ≥2
patas resueltas, el **97.9% tiene exactamente un SÍ**. El supuesto se sostiene.

## El coste es lo que decide, y escala con N

Capturar exige tocar **las N patas**, cada una cruzando media horquilla
(0.95 pp, medido en el paso 2):

    coste = N × 0.95 pp        beneficio = |Σp − 1|

**El coste crece con N; la incoherencia no.** Con la mediana de 3 patas hacen
falta >2.85 pp de desviación; con 11 patas, >10.45 pp. Ésa es toda la
aritmética, y es la que mata la idea.

## Las dos trampas, y son grandes

**a) Patas faltantes fabrican un arb enorme.** Si sólo ves 2 de 7 patas, Σp sale
bajísimo y parece un arbitraje del 26%. **Medido: las observaciones incompletas
dan una desviación mediana fingida de −26.00 pp.** Aquí sólo cuentan los eventos
donde **todas** las patas vivas en ese instante tienen precio. Nunca se rellena
una pata que falta: se descarta la observación entera.

**b) La asincronía infla la desviación.** Un row group de `trades.parquet` abarca
~8 DÍAS. Tomar "el último precio de cada pata en el row group" suma la pata A del
lunes con la B del jueves, y eso no es incoherencia sino desfase. Medido barriendo
el tope de frescura:

    cap 1440 min → |dev| mediana 1.90 pp   (n=2,579)
    cap  240 min → 1.50 pp
    cap   60 min → 1.20 pp
    cap   15 min → 1.00 pp                 (n=69)
    cap    5 min → 1.00 pp                 (n=29)

Converge a ~1.0 pp. **Cerca de la mitad de la desviación aparente era desfase**,
y quien no exija simultaneidad reporta el doble del mispricing real.

Uso:
  python -m tools.polymarket_negrisk --markets markets.parquet --row-groups 40
"""
from __future__ import annotations

import argparse

import numpy as np

N_MIN_CONCLUYENTE = 30

# Media horquilla medida en el paso 2 (`polymarket_spread.py`, estimador adverso).
HALF_SPREAD_PP = 0.95

# Topes de frescura del barrido. El más flojo es DELIBERADO: sesga a favor de la
# tesis, así que si ni siquiera él la salva, el veredicto es robusto.
STALENESS_CAPS_MIN = (5, 15, 60, 240, 1440)


def legs_alive_at(neg_risk_markets, moment):
    """Patas que existían y no habían cerrado en ese instante.

    Es el denominador de la completitud. Usar el conteo de patas de HOY sobre un
    instante del pasado contaría como "faltante" una pata que aún no existía.
    """
    alive = neg_risk_markets[
        (neg_risk_markets["created_at"] <= moment) & (neg_risk_markets["end_date"] >= moment)
    ]
    return alive.groupby("event_id").size().rename("n_expected")


def event_snapshot(trades, neg_risk_markets, *, moment_ts, staleness_cap_min):
    """Σp por evento en un instante, SOLO con eventos de patas completas.

    `trades` debe traer market_id, event_id, p, timestamp, y venir ordenado.
    Devuelve un frame con n_obs, n_expected, sum_p, stale_max — sin filtrar por
    completitud, para que quien llame pueda CONTAR lo que descarta.
    """
    import pandas as pd

    past = trades[trades["timestamp"] <= moment_ts]
    if past.empty:
        return pd.DataFrame(
            columns=["event_id", "n_obs", "sum_p", "stale_max", "n_expected"]
        )
    last = past.groupby("market_id", as_index=False).last()
    last = last.assign(stale_min=(moment_ts - last["timestamp"]) / 60.0)
    fresh = last[last["stale_min"] <= staleness_cap_min]
    expected = legs_alive_at(neg_risk_markets, pd.Timestamp(moment_ts, unit="s", tz="UTC"))
    grouped = fresh.groupby("event_id").agg(
        n_obs=("p", "size"), sum_p=("p", "sum"), stale_max=("stale_min", "max")
    )
    return grouped.join(expected, how="inner").reset_index()


def keep_complete(snapshots, min_legs=2):
    """Sólo eventos con TODAS las patas vivas presentes. La trampa (a)."""
    return snapshots[
        (snapshots["n_obs"] == snapshots["n_expected"]) & (snapshots["n_expected"] >= min_legs)
    ].copy()


def score(complete, *, half_spread_pp=HALF_SPREAD_PP):
    """Desviación, coste y neto. El coste escala con el número de patas."""
    out = complete.copy()
    out["dev_pp"] = (out["sum_p"] - 1.0) * 100.0
    out["cost_pp"] = out["n_expected"] * half_spread_pp
    out["net_pp"] = out["dev_pp"].abs() - out["cost_pp"]
    return out


def fake_arb_of_incomplete(snapshots):
    """Cuánto arbitraje FABRICA no exigir patas completas.

    Existe para que el número viva en el reporte, no en la memoria de nadie.
    """
    incomplete = snapshots[
        (snapshots["n_obs"] < snapshots["n_expected"]) & (snapshots["n_expected"] >= 2)
    ]
    if len(incomplete) == 0:
        return None
    return {
        "n": int(len(incomplete)),
        "dev_pp_median": float(((incomplete["sum_p"] - 1.0) * 100).median()),
        "legs_seen": float(incomplete["n_obs"].median()),
        "legs_expected": float(incomplete["n_expected"].median()),
    }


def verdict(scored, *, min_n=N_MIN_CONCLUYENTE) -> dict:
    if len(scored) < min_n:
        return {"decidible": False, "n": int(len(scored)),
                "razon": f"n={len(scored)} < {min_n}: no concluye"}
    return {
        "decidible": True,
        "n": int(len(scored)),
        "n_eventos": int(scored["event_id"].nunique()),
        "dev_pp_median": float(scored["dev_pp"].abs().median()),
        "cost_pp_median": float(scored["cost_pp"].median()),
        "net_pp_median": float(scored["net_pp"].median()),
        "frac_rentable": float((scored["net_pp"] > 0).mean()),
        "sobrevive": bool(scored["net_pp"].median() > 0),
        "overround_pp": float(scored["dev_pp"].median()),
        "frac_sum_mayor_1": float((scored["dev_pp"] > 0).mean()),
    }


def format_report(por_cap, scored_tight, fake, veredicto, *, tight_cap) -> str:
    lines = []
    add = lines.append
    add("=" * 78)
    add("COHERENCIA DE CONJUNTO COMPLETO (neg_risk) — POLYMARKET")
    add("=" * 78)
    add("En un evento neg_risk exactamente un resultado ocurre → Σp debe ser 1.")
    add(f"Capturarlo cuesta N × {HALF_SPREAD_PP:.2f}pp (media horquilla, paso 2), y")
    add("el coste escala con N mientras la incoherencia no.")
    add("")

    if fake:
        add("-- TRAMPA (a): lo que FABRICA no exigir patas completas --")
        add(f"  observaciones incompletas   {fake['n']:,}")
        add(f"  desviación mediana FINGIDA  {fake['dev_pp_median']:+.2f} pp"
            f"   (se vieron {fake['legs_seen']:.0f} de {fake['legs_expected']:.0f} patas)")
        add("  Estas observaciones se DESCARTAN. Una pata que falta no se rellena.")
        add("")

    add("-- TRAMPA (b): cuánto de la desviación era ASINCRONÍA --")
    add(f"  {'cap frescura':>14} {'n obs':>8} {'n evts':>7} {'|dev| mediana':>14}")
    for cap, data in por_cap:
        if data is None or len(data) == 0:
            add(f"  {str(cap) + ' min':>14}  sin muestra")
            continue
        add(f"  {str(cap) + ' min':>14} {len(data):>8,} {data['event_id'].nunique():>7,} "
            f"{data['dev_pp'].abs().median():>13.2f}pp")
    add("  Converge al apretar: quien no exija simultaneidad reporta el doble.")
    add("")

    if scored_tight is not None and len(scored_tight):
        add(f"-- CON FRESCURA <= {tight_cap} min, POR NÚMERO DE PATAS --")
        add(f"  {'patas':>7} {'n obs':>7} {'n evts':>7} {'|dev| med':>10} {'coste':>8} "
            f"{'net med':>9} {'% net>0':>9}")
        import pandas as pd
        bucketed = scored_tight.assign(
            _b=pd.cut(scored_tight["n_expected"], [1, 2, 3, 5, 11, 200],
                      labels=["2", "3", "4-5", "6-11", "12+"])
        )
        for bucket, group in bucketed.groupby("_b", observed=True):
            mark = "  << n<30, NO CONCLUYE" if len(group) < N_MIN_CONCLUYENTE else ""
            add(f"  {str(bucket):>7} {len(group):>7,} {group['event_id'].nunique():>7,} "
                f"{group['dev_pp'].abs().median():>9.2f}pp {group['cost_pp'].mean():>7.2f}pp "
                f"{group['net_pp'].median():>8.2f}pp {(group['net_pp'] > 0).mean():>8.1%}{mark}")
        add("")

    if veredicto["decidible"]:
        add("-- VEREDICTO --")
        add(f"  n = {veredicto['n']:,} observaciones sobre "
            f"{veredicto['n_eventos']:,} eventos")
        add(f"  incoherencia mediana   {veredicto['dev_pp_median']:.2f} pp")
        add(f"  coste mediano          {veredicto['cost_pp_median']:.2f} pp")
        add(f"  NETO mediano           {veredicto['net_pp_median']:+.2f} pp")
        add(f"  rentable en            {veredicto['frac_rentable']:.1%} de las observaciones")
        estado = "SOBREVIVE" if veredicto["sobrevive"] else "NO SOBREVIVE"
        add(f"  → {estado}")
        add("")
        add(f"  El sobre-redondeo existe: Σp>1 en {veredicto['frac_sum_mayor_1']:.1%} de los")
        add(f"  casos, mediana {veredicto['overround_pp']:+.2f}pp. Es real y es MENOR que el")
        add("  coste de cobrarlo — que es exactamente por qué sigue ahí.")
    else:
        add(f"-- SIN VEREDICTO: {veredicto['razon']} --")
    add("=" * 78)
    return "\n".join(lines)


def main(argv=None) -> int:
    import pandas as pd

    from tools.polymarket_spread import TRADE_COLUMNS, normalize_yes, sample_row_groups

    parser = argparse.ArgumentParser(description="Coherencia neg_risk en Polymarket")
    parser.add_argument("--markets", required=True)
    parser.add_argument("--row-groups", type=int, default=40)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--targets-per-rg", type=int, default=8)
    parser.add_argument("--tight-cap", type=int, default=15, help="minutos")
    args = parser.parse_args(argv)

    markets = pd.read_parquet(
        args.markets, columns=["id", "event_id", "neg_risk", "created_at", "end_date"]
    )
    markets["id"] = markets["id"].astype(str)
    neg = markets[(markets["neg_risk"] == 1) & markets["event_id"].notna()].copy()
    leg_of = neg.set_index("id")["event_id"]
    print(f"universo neg_risk: {len(neg):,} mercados en {neg['event_id'].nunique():,} eventos")

    parquet, groups = sample_row_groups(args.row_groups, year=args.year)
    caps = sorted(set(STALENESS_CAPS_MIN) | {args.tight_cap})
    buckets: dict[int, list] = {c: [] for c in caps}
    raw_for_fake: list = []

    for i, rg in enumerate(groups, 1):
        chunk = normalize_yes(parquet.read_row_group(rg, columns=TRADE_COLUMNS).to_pandas())
        chunk["market_id"] = chunk["market_id"].astype(str)
        chunk = chunk[chunk["market_id"].isin(leg_of.index)]
        if chunk.empty:
            continue
        chunk = chunk.sort_values(["timestamp", "log_index"])
        chunk["event_id"] = chunk["market_id"].map(leg_of)

        lo, hi = int(chunk["timestamp"].min()), int(chunk["timestamp"].max())
        for moment in np.linspace(lo + (hi - lo) * 0.1, hi, args.targets_per_rg):
            moment = int(moment)
            for cap in caps:
                snaps = event_snapshot(chunk, neg, moment_ts=moment, staleness_cap_min=cap)
                if len(snaps) == 0:
                    continue
                if cap == max(caps):
                    raw_for_fake.append(snaps)
                complete = keep_complete(snaps)
                if len(complete):
                    buckets[cap].append(score(complete).assign(t=moment))
        if i % 5 == 0 or i == len(groups):
            print(f"  leidos {i}/{len(groups)} row groups", flush=True)

    por_cap = []
    scored_tight = None
    for cap in caps:
        data = pd.concat(buckets[cap], ignore_index=True) if buckets[cap] else None
        por_cap.append((cap, data))
        if cap == args.tight_cap:
            scored_tight = data

    fake = fake_arb_of_incomplete(pd.concat(raw_for_fake, ignore_index=True)) if raw_for_fake else None
    veredicto = verdict(scored_tight) if scored_tight is not None else {
        "decidible": False, "n": 0, "razon": "sin muestra"
    }
    print()
    print(format_report(por_cap, scored_tight, fake, veredicto, tight_cap=args.tight_cap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
