# -*- coding: utf-8 -*-
"""
Horquilla efectiva de Polymarket — el paso 2 que decide el veredicto.

`polymarket_supply.py` (paso 1) midió que la oferta existe: 32,085 mercados en
2026 con volumen ≥$100k y horizonte ≤7d. Y dejó el bloqueante nombrado: **con
~113 vueltas al año, una horquilla de 4pp anula un edge de 2pp.** Esto mide la
horquilla.

## El problema de método: NO hay libro

El dataset no trae bid/ask. Ni `trades.parquet` ni `quant.parquet` — son
ejecuciones, no cotizaciones. La horquilla COTIZADA no se puede medir aquí y
decir lo contrario sería inventar.

Lo que sí se puede medir es la horquilla **EFECTIVA**: la que de verdad pagó
quien cruzó. Para un taker es la magnitud relevante — es su coste real, no una
cotización que quizá nunca tocó.

## Dos estimadores independientes (a propósito)

**1. Rebote comprador-vendedor** (usa la dirección del taker). En pares de
órdenes adyacentes con lado opuesto, `p_compra − p_venta` estima la horquilla
completa: el comprador pagó el ask, el vendedor pegó al bid. La deriva de precio
contamina cada par, pero es media-cero sobre muchos pares mientras el rebote es
sistemáticamente positivo. Se reporta `frac_neg`: si una fracción grande de
pares sale negativa, el estimador está dominado por deriva y no se cree.

**2. Roll (1984)**: `spread = 2·√(−cov(Δp_t, Δp_{t−1}))`. No usa la dirección —
es un cross-check genuinamente independiente. Indefinido cuando `cov > 0`
(momentum); esa fracción se reporta, no se esconde.

**Si los dos no concuerdan, el resultado es el desacuerdo**, no el promedio.

## El sesgo de Roll, medido y corregido (no supuesto)

Roll asume que el signo del taker es **iid**. En Polymarket NO lo es: la
autocorrelación lag-1 de la dirección sale **+0.234 mediana** (87.5% de los
mercados con ρ₁>0). Es la misma firma de order-splitting que este repo ya validó
como F2. Con `p_t = m_t + (s/2)·q_t` y `q` autocorrelado:

    −cov = (s²/4)·(1 + ρ₂ − 2ρ₁)     ⇒     s = roll_crudo / √(1 + ρ₂ − 2ρ₁)

Con ρ₁ positivo el radicando baja de 1 y **Roll subestima**. Por eso el tool
reporta `roll_crudo` y `roll_corregido` con la ρ medida, y el veredicto usa el
corregido. Con ρ₁≈0.234 el factor es ~0.77: Roll crudo se queda ~23% corto.

## Las trampas del venue

**a) La perspectiva.** Vender YES ≡ comprar NO. En crudo, `taker_direction` sale
89% SELL, que no es desbalance real sino la codificación del venue. Sin
normalizar a perspectiva YES (`p → 1−p` y lado volteado para `token2`) el
estimador mide basura. Verificación: normalizado, los lados quedan ~50/50.

**b) El fraccionamiento de órdenes.** Una orden de taker se llena contra N
makers y produce N filas. Se colapsan por `transaction_hash` porque el precio
que pagó el taker es el VWAP de su orden, no el de su último fill.

> **CORRECCIÓN honesta (2026-08-17).** La primera versión de este encabezado
> afirmaba que sin colapsar el rebote se sesgaba hacia cero. **Es falso, y está
> medido:** el efecto del colapso sobre el rebote es **−0.0%**. Los fills
> consecutivos del mismo lado no producen cambio de lado, así que ya quedaban
> fuera del estimador solos. El colapso se mantiene porque es la definición
> correcta del precio del taker, no porque cambie el número.

## Lo que este número NO es

La horquilla efectiva está condicionada a que **hubo trade**. Cuando el libro se
abre y nadie cruza, ese momento no entra en la muestra. Es por construcción una
**cota INFERIOR** de la horquilla que enfrentarías en un instante arbitrario.
Sirve para matar la tesis (si ya es alta, muerto) y no para bendecirla.

Data (lectura remota por rangos HTTP: no hace falta bajar los 37.5 GB):
  https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data → trades.parquet

Uso:
  python tools/polymarket_spread.py --markets markets.parquet --row-groups 14
  python tools/polymarket_spread.py --markets markets.parquet --edge-pp 2 --local trades.parquet
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np

# Mismo piso que el resto del repo: con muestra chica, ordenar por resultado
# selecciona ruido. Un mercado con menos de esto no aporta estimación.
N_MIN_CONCLUYENTE = 30

TRADES_URL = (
    "https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data"
    "/resolve/main/trades.parquet"
)
TRADE_COLUMNS = [
    "timestamp", "log_index", "market_id", "price", "usd_amount",
    "taker_direction", "transaction_hash", "nonusdc_side",
]

_FLIP = {"BUY": "SELL", "SELL": "BUY"}


@dataclass
class SpreadEstimate:
    """Una estimación con su n y su señal de desconfianza."""

    n_markets: int
    vw_pp: float          # ponderado por volumen — lo que pagaría el capital
    median_pp: float      # sin ponderar — resistente a un mercado gigante
    diagnostic: float     # rebote: frac. de pares negativos. Roll: frac. indefinida
    diagnostic_label: str

    @property
    def thin(self) -> bool:
        return self.n_markets < N_MIN_CONCLUYENTE


def normalize_yes(frame):
    """Todo a perspectiva YES. Sin esto el estimador mide la codificación del
    venue, no la horquilla (trampa (a) del encabezado)."""
    is_no = frame["nonusdc_side"] == "token2"
    out = frame.copy()
    out["p"] = out["price"].where(~is_no, 1.0 - out["price"])
    out["side"] = out["taker_direction"].where(
        ~is_no, out["taker_direction"].map(_FLIP)
    )
    return out


def collapse_taker_orders(frame):
    """Colapsa los N fills de una orden a UNA orden al precio medio ponderado.

    Sin esto el rebote se mide dentro de la propia orden y sale sesgado hacia
    cero (trampa (b)). El colapso típico es ~1.8x.
    """
    work = frame.copy()
    work["_pw"] = work["p"] * work["usd_amount"]
    grouped = work.groupby(
        ["market_id", "transaction_hash", "side"], sort=False, observed=True
    ).agg(
        _pw=("_pw", "sum"),
        usd=("usd_amount", "sum"),
        ts=("timestamp", "min"),
        li=("log_index", "min"),
    ).reset_index()
    # Si una orden movió 0 USD no hay peso: cae fuera, y se nota en la n.
    grouped = grouped[grouped["usd"] > 0].copy()
    grouped["p"] = grouped["_pw"] / grouped["usd"]
    return grouped.drop(columns="_pw").sort_values(["market_id", "ts", "li"])


def bounce_spread(orders, min_pairs: int = N_MIN_CONCLUYENTE):
    """Rebote comprador-vendedor, por mercado. Devuelve un frame por mercado."""
    import pandas as pd

    rows = []
    for market_id, group in orders.groupby("market_id", sort=False, observed=True):
        prices = group["p"].to_numpy()
        is_buy = group["side"].to_numpy() == "BUY"
        if len(prices) < 2:
            continue
        flips = is_buy[:-1] != is_buy[1:]
        if flips.sum() < min_pairs:
            continue
        # est = p_compra - p_venta, en el orden en que hayan caído
        est = np.where(is_buy[:-1], prices[:-1] - prices[1:], prices[1:] - prices[:-1])
        est = est[flips]
        rows.append({
            "market_id": market_id,
            "n_pairs": int(flips.sum()),
            "spread": float(est.mean()),
            "frac_neg": float((est < 0).mean()),
            "usd": float(group["usd"].sum()),
        })
    return pd.DataFrame(rows, columns=["market_id", "n_pairs", "spread", "frac_neg", "usd"])


def roll_spread(orders, min_orders: int = N_MIN_CONCLUYENTE):
    """Estimador de Roll por mercado. `roll` queda NaN donde cov>0."""
    import pandas as pd

    rows = []
    for market_id, group in orders.groupby("market_id", sort=False, observed=True):
        if len(group) < min_orders:
            continue
        deltas = np.diff(group["p"].to_numpy())
        if len(deltas) < 3:
            continue
        cov = float(np.cov(deltas[:-1], deltas[1:])[0, 1])
        rows.append({
            "market_id": market_id,
            "n_orders": int(len(group)),
            "cov": cov,
            # Indefinido con cov>0 (momentum). NaN, no cero: cero sería mentir.
            "roll": float(2.0 * np.sqrt(-cov)) if cov < 0 else float("nan"),
            "usd": float(group["usd"].sum()),
        })
    return pd.DataFrame(rows, columns=["market_id", "n_orders", "cov", "roll", "usd"])


def direction_autocorr(orders, min_orders: int = N_MIN_CONCLUYENTE):
    """ρ₁ y ρ₂ del signo del taker, por mercado.

    Roll supone iid (ρ=0). Medirlo es lo que permite corregirlo en vez de
    arrastrar un sesgo desconocido.
    """
    import pandas as pd

    rows = []
    for market_id, group in orders.groupby("market_id", sort=False, observed=True):
        if len(group) < min_orders:
            continue
        signs = np.where(group["side"].to_numpy() == "BUY", 1.0, -1.0)
        if signs.std() == 0:            # todo un lado: no hay autocorrelación que medir
            continue
        rho1 = float(np.corrcoef(signs[:-1], signs[1:])[0, 1])
        rho2 = (
            float(np.corrcoef(signs[:-2], signs[2:])[0, 1]) if len(signs) > 3 else float("nan")
        )
        rows.append({
            "market_id": market_id, "rho1": rho1, "rho2": rho2,
            "usd": float(group["usd"].sum()),
        })
    return pd.DataFrame(rows, columns=["market_id", "rho1", "rho2", "usd"])


def roll_correction_factor(rho1: float, rho2: float) -> float:
    """√(1 + ρ₂ − 2ρ₁): lo que hay que dividirle a Roll crudo.

    Devuelve NaN si el radicando no es positivo — ahí el modelo de Roll no
    describe la serie y corregir sería inventar.
    """
    if np.isnan(rho1) or np.isnan(rho2):
        return float("nan")
    radicand = 1.0 + rho2 - 2.0 * rho1
    return float(np.sqrt(radicand)) if radicand > 0 else float("nan")


def summarize_bounce(frame) -> SpreadEstimate:
    if len(frame) == 0:
        return SpreadEstimate(0, float("nan"), float("nan"), float("nan"), "pares negativos")
    weights = frame["usd"] / frame["usd"].sum()
    return SpreadEstimate(
        n_markets=len(frame),
        vw_pp=float((frame["spread"] * weights).sum() * 100),
        median_pp=float(frame["spread"].median() * 100),
        diagnostic=float((frame["frac_neg"] * weights).sum()),
        diagnostic_label="pares negativos (deriva)",
    )


def summarize_roll(frame) -> SpreadEstimate:
    if len(frame) == 0:
        return SpreadEstimate(0, float("nan"), float("nan"), float("nan"), "indefinidos")
    defined = frame.dropna(subset=["roll"])
    if len(defined) == 0:
        return SpreadEstimate(0, float("nan"), float("nan"), 1.0, "indefinidos (cov>0)")
    weights = defined["usd"] / defined["usd"].sum()
    return SpreadEstimate(
        n_markets=len(defined),
        vw_pp=float((defined["roll"] * weights).sum() * 100),
        median_pp=float(defined["roll"].median() * 100),
        diagnostic=float(1.0 - len(defined) / len(frame)),
        diagnostic_label="indefinidos (cov>0, momentum)",
    )


def correct_roll(roll: SpreadEstimate, autocorr) -> tuple[SpreadEstimate, float, float]:
    """Aplica la corrección de autocorrelación a Roll. Devuelve (estimado, ρ₁, ρ₂)."""
    if len(autocorr) == 0 or roll.n_markets == 0:
        return roll, float("nan"), float("nan")
    weights = autocorr["usd"] / autocorr["usd"].sum()
    rho1 = float((autocorr["rho1"] * weights).sum())
    rho2 = float((autocorr["rho2"].fillna(0.0) * weights).sum())
    factor = roll_correction_factor(rho1, rho2)
    if np.isnan(factor) or factor <= 0:
        return roll, rho1, rho2
    return (
        SpreadEstimate(
            n_markets=roll.n_markets,
            vw_pp=roll.vw_pp / factor,
            median_pp=roll.median_pp / factor,
            diagnostic=roll.diagnostic,
            diagnostic_label=roll.diagnostic_label,
        ),
        rho1,
        rho2,
    )


def verdict(bounce: SpreadEstimate, roll: SpreadEstimate, edge_pp: float) -> dict:
    """El veredicto se emite contra la horquilla MÁS ALTA de las dos.

    Tomar la más favorable sería elegir el estimador por su resultado, que es
    exactamente la selección por resultado que este repo tiene prohibida.
    """
    candidates = [e.vw_pp for e in (bounce, roll) if not np.isnan(e.vw_pp)]
    if not candidates:
        return {"decidible": False, "razon": "ningún estimador dio número"}
    worst = max(candidates)
    breakeven = 2.0 * edge_pp
    return {
        "decidible": True,
        "spread_adverso_pp": worst,
        "breakeven_pp": breakeven,
        "edge_neto_pp": edge_pp - worst / 2.0,
        "sobrevive": worst < breakeven,
        "margen": breakeven / worst if worst > 0 else float("inf"),
    }


def format_report(
    bounce, roll, roll_corr, veredicto, *, edge_pp, n_trades, n_orders, slice_desc,
    rho1=float("nan"), rho2=float("nan"),
) -> str:
    lines = []
    add = lines.append
    add("=" * 74)
    add("HORQUILLA EFECTIVA — POLYMARKET")
    add("=" * 74)
    add(f"corte: {slice_desc}")
    add(f"trades crudos {n_trades:,} → órdenes de taker {n_orders:,} "
        f"(colapso {n_trades / max(n_orders, 1):.2f}x)")
    add("")
    add(f"  {'estimador':<28} {'n mkts':>8} {'pond.vol':>10} {'mediana':>10}  diagnóstico")
    estimadores = (
        ("rebote (usa dirección)", bounce),
        ("Roll crudo (supone iid)", roll),
        ("Roll corregido por ρ", roll_corr),
    )
    for name, est in estimadores:
        mark = "  << n<30" if est.thin else ""
        add(f"  {name:<28} {est.n_markets:>8,} {est.vw_pp:>9.2f}pp "
            f"{est.median_pp:>9.2f}pp  {est.diagnostic:.1%} {est.diagnostic_label}{mark}")
    add("")
    if not np.isnan(rho1):
        factor = roll_correction_factor(rho1, rho2)
        add(f"-- POR QUÉ SE CORRIGE ROLL --")
        add(f"  autocorrelación de la dirección del taker: ρ₁={rho1:+.3f} · ρ₂={rho2:+.3f}")
        add(f"  Roll supone ρ=0 (flujo iid). Factor √(1+ρ₂−2ρ₁) = {factor:.3f}")
        add("  ρ₁>0 es order-splitting: la MISMA firma que este repo validó como F2.")
        add("  No es un edge — es un sesgo del estimador, y aquí solo se corrige.")
        add("")
    if veredicto["decidible"]:
        add(f"-- VEREDICTO (contra el estimador MÁS ADVERSO, no el más favorable) --")
        add(f"  horquilla adversa      {veredicto['spread_adverso_pp']:.2f} pp")
        add(f"  breakeven (edge {edge_pp:g}pp)  {veredicto['breakeven_pp']:.2f} pp")
        add(f"  edge neto              {veredicto['edge_neto_pp']:+.2f} pp "
            f"(cruzando UNA vez, a resolución)")
        estado = "SOBREVIVE" if veredicto["sobrevive"] else "MUERE"
        add(f"  → el edge supuesto {estado}, con margen {veredicto['margen']:.1f}x")
    add("")
    add("-- LÍMITES DE ESTE NÚMERO --")
    add("  · Es horquilla EFECTIVA (la que se pagó), no cotizada: el dataset no")
    add("    trae libro. Está condicionada a que hubo trade, así que es una COTA")
    add("    INFERIOR de la que enfrentarías en un instante arbitrario.")
    add("  · El `edge` sigue siendo un SUPUESTO. Esto mide el coste, no la señal.")
    add("  · No hay impacto de mercado modelado: al tomar tamaño, la horquilla")
    add("    efectiva sube. `capacity_analysis.py` es el marco para eso.")
    add("=" * 74)
    return "\n".join(lines)


def capturable_market_ids(markets_path, *, vol_min, horizon_max_days, year=None):
    """Los ids del corte que `polymarket_supply` dejó vivo."""
    import pandas as pd

    from tools.polymarket_supply import capturable_universe

    frame = pd.read_parquet(
        markets_path, columns=["id", "question", "volume", "created_at", "end_date", "closed"]
    )
    universe = capturable_universe(frame, vol_min, horizon_max_days)
    if year is not None:
        universe = universe[universe["created_at"].dt.year == year]
    return set(universe["id"].astype(str))


def sample_row_groups(n_wanted, *, url=TRADES_URL, year=2026):
    """Row groups estratificados por mes. Un solo bloque sería una semana
    disfrazada de año."""
    import datetime as dt

    import fsspec
    import pyarrow.parquet as pq

    handle = fsspec.filesystem("http").open(url, block_size=8 * 1024 * 1024)
    parquet = pq.ParquetFile(handle)
    meta = parquet.metadata
    ts_col = [i for i, f in enumerate(parquet.schema_arrow) if f.name == "timestamp"][0]

    by_month: dict[str, list[int]] = {}
    for rg in range(meta.num_row_groups):
        stats = meta.row_group(rg).column(ts_col).statistics
        stamp = dt.datetime.fromtimestamp(stats.min, dt.UTC)
        if year is not None and stamp.year != year:
            continue
        by_month.setdefault(stamp.strftime("%Y-%m"), []).append(rg)

    chosen: list[int] = []
    months = sorted(by_month)
    per_month = max(1, n_wanted // max(len(months), 1))
    for month in months:
        pool = by_month[month]
        step = max(1, len(pool) // per_month)
        chosen.extend(pool[::step][:per_month])
    return parquet, sorted(chosen)


def main(argv=None) -> int:
    import pandas as pd

    parser = argparse.ArgumentParser(description="Horquilla efectiva de Polymarket")
    parser.add_argument("--markets", required=True, help="ruta a markets.parquet")
    parser.add_argument("--local", help="trades.parquet local (si no, lectura remota)")
    parser.add_argument("--row-groups", type=int, default=14)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--vol-min", type=float, default=100_000.0)
    parser.add_argument("--horizon-max", type=float, default=7.0)
    parser.add_argument("--edge-pp", type=float, default=2.0)
    args = parser.parse_args(argv)

    keep = capturable_market_ids(
        args.markets, vol_min=args.vol_min, horizon_max_days=args.horizon_max, year=args.year
    )
    print(f"corte capturable: {len(keep):,} mercados (vol>=${args.vol_min:,.0f}, "
          f"h<={args.horizon_max:g}d, {args.year})")

    url = args.local or TRADES_URL
    if args.local:
        import pyarrow.parquet as pq
        parquet, groups = pq.ParquetFile(url), None
        groups = list(range(min(args.row_groups, parquet.metadata.num_row_groups)))
    else:
        parquet, groups = sample_row_groups(args.row_groups, year=args.year)
    print(f"leyendo {len(groups)} row groups…")

    parts = []
    for i, rg in enumerate(groups, 1):
        chunk = parquet.read_row_group(rg, columns=TRADE_COLUMNS).to_pandas()
        chunk = chunk[chunk["market_id"].astype(str).isin(keep)]
        parts.append(chunk)
        print(f"  [{i}/{len(groups)}] rg {rg}: {len(chunk):,} trades del corte")
    frame = pd.concat(parts, ignore_index=True)

    if frame.empty:
        print("El corte no tiene trades en la muestra. Sin veredicto.")
        return 1

    orders = collapse_taker_orders(normalize_yes(frame))
    bounce = summarize_bounce(bounce_spread(orders))
    roll = summarize_roll(roll_spread(orders))
    roll_corr, rho1, rho2 = correct_roll(roll, direction_autocorr(orders))
    print()
    print(format_report(
        bounce, roll, roll_corr, verdict(bounce, roll_corr, args.edge_pp),
        edge_pp=args.edge_pp, n_trades=len(frame), n_orders=len(orders),
        slice_desc=f"vol>=${args.vol_min:,.0f} · h<={args.horizon_max:g}d · {args.year}",
        rho1=rho1, rho2=rho2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
