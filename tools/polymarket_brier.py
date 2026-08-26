# -*- coding: utf-8 -*-
"""
Brier advantage — ¿le ganamos al precio de Polymarket? (paso 3)

Los pasos 1 y 2 midieron el COSTE y salieron a favor: hay oferta (32,085 mercados
en 2026) y la horquilla no la mata (1.90pp adversos vs 4pp de breakeven). Todo
colgaba de un edge de 2pp **supuesto**. Esto lo ataca de frente.

La vara correcta para un mercado de predicción no es el win rate ni el R: es si
tu probabilidad está **mejor calibrada que el precio del venue**. Eso es el Brier
advantage, y se traduce directo a puntos de edge para compararlo con el
breakeven de 0.95pp que dejó el paso 2.

## El bug que este archivo existe para no repetir

La primera medición ponderó por TRADE y encontró un sesgo precioso: el tramo
0.35-0.80 sobrevalorado 4-5pp, monótono, sobre millones de trades. Habría sido
el hallazgo del año.

**Era un artefacto.** Un mercado que va de 0.60 a 0 genera enorme volumen en la
caída, así que ponderar por trade sobre-muestrea el camino "estaba caro y
resolvió NO". Con **una observación por mercado**:

    ponderado por trade     sesgo global  -2.25 pp   (y -4/-5pp en el medio)
    por mercado, a 24h      sesgo global  -1.35 pp   (buckets con signos alternos)
    por mercado, a 1h       sesgo global  +0.22 pp   <- cero

El sesgo se evaporó. Por eso aquí **la unidad de observación es el MERCADO** y
la n que se reporta es la de mercados, nunca la de trades: los trades del mismo
mercado no son observaciones independientes, y tratarlos como tales infla la n
por tres órdenes de magnitud y fabrica significancia.

## La segunda trampa: el 0.50 no es un desenlace

De 1,777,818 mercados "cerrados", **327,496 tienen precio final exactamente
0.50** — eso no es una resolución, es el valor por defecto de "sin información"
(anulado, sin liquidar, o metadata vieja). Solo el 72.4% tiene resolución
limpia. Usar el resto como outcome envenena el Brier entero.

## Métricas

    Brier            mean((p - y)^2)          más bajo es mejor
    skill            1 - Brier/Brier_base     vs predecir la tasa base
    Brier advantage  Brier_mercado - Brier_modelo    positivo = le ganas
    edge realizado   mean((y - p_mkt)*dir)*100  en PUNTOS, comparable al breakeven

`edge realizado` es la que decide: es literalmente lo que ganarías por acción
comprando al precio del mercado cuando tu modelo discrepa. Se compara contra el
breakeven medido en el paso 2 (spread/2 = 0.95pp).

## La recalibración se ajusta SOLO fuera de muestra

Cualquier mapa `p_modelo = f(p_mercado)` ajustado sobre todo el histórico gana
en muestra por construcción. Aquí el ajuste es **walk-forward por tiempo**: cada
pliegue se prueba con un mapa ajustado solo con lo anterior. Sin eso, esto sería
una máquina de fabricar edge inexistente — el mismo error que `marea` documentó
cuando el escalado de Platt EMPEORÓ de 3.49pp a 6.22pp fuera de muestra.

Uso:
  python -m tools.polymarket_brier --markets markets.parquet --row-groups 60
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass

import numpy as np

N_MIN_CONCLUYENTE = 30

# Un mercado "cerrado" cuyo precio final no está pegado a 0 o a 1 no resolvió:
# el 0.50 exacto es el valor por defecto de "sin información".
RESOLUTION_EPS = 0.01


@dataclass
class BrierResult:
    n_markets: int
    brier: float
    brier_base: float
    bias_pp: float

    @property
    def skill(self) -> float:
        return 1.0 - self.brier / self.brier_base if self.brier_base > 0 else float("nan")

    @property
    def thin(self) -> bool:
        return self.n_markets < N_MIN_CONCLUYENTE


def parse_final_price(raw):
    """`outcome_prices` llega doblemente codificado: "['0.0005', '0.9995']"."""
    try:
        value = ast.literal_eval(raw)
        if isinstance(value, str):
            value = ast.literal_eval(value)
        return float(value[0])
    except Exception:
        return float("nan")


def clean_resolutions(markets):
    """Solo mercados con desenlace inequívoco. Devuelve (frame, descartados)."""
    frame = markets.copy()
    frame["p_final"] = frame["outcome_prices"].map(parse_final_price)
    closed = frame[frame["closed"] == 1]
    resolved = closed[
        (closed["p_final"] < RESOLUTION_EPS) | (closed["p_final"] > 1 - RESOLUTION_EPS)
    ].copy()
    resolved["y"] = (resolved["p_final"] > 1 - RESOLUTION_EPS).astype(int)
    descartados = {
        "cerrados": int(len(closed)),
        "resueltos": int(len(resolved)),
        "sin_desenlace": int(len(closed) - len(resolved)),
        "en_050_exacto": int((closed["p_final"].round(2) == 0.50).sum()),
    }
    return resolved, descartados


def market_snapshots(trades, resolved, *, lead_hours, tolerance_hours, vol_min=0.0):
    """UNA observación por mercado: el trade más cercano a `lead_hours` del cierre.

    Esta función es la vacuna contra el bug de arriba. Si alguna vez alguien la
    reemplaza por "usa todos los trades", el sesgo falso vuelve.
    """
    import pandas as pd

    meta = resolved.set_index(resolved["id"].astype(str))[["y", "end_date", "volume"]]
    work = trades.join(meta, on="market_id", how="inner")
    work = work[work["volume"] >= vol_min]
    stamps = pd.to_datetime(work["timestamp"], unit="s", utc=True)
    work = work.assign(lead_h=(work["end_date"] - stamps).dt.total_seconds() / 3600.0)
    work = work[work["lead_h"] > 0]
    work = work.assign(_dist=(work["lead_h"] - lead_hours).abs())
    snaps = work.sort_values("_dist").groupby("market_id", as_index=False).first()
    return snaps[snaps["_dist"] <= tolerance_hours].drop(columns="_dist")


def brier_of(prices, outcomes) -> BrierResult:
    prices = np.asarray(prices, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if len(prices) == 0:
        return BrierResult(0, float("nan"), float("nan"), float("nan"))
    base_rate = outcomes.mean()
    return BrierResult(
        n_markets=len(prices),
        brier=float(((prices - outcomes) ** 2).mean()),
        brier_base=float(((base_rate - outcomes) ** 2).mean()),
        bias_pp=float((outcomes.mean() - prices.mean()) * 100),
    )


def calibration_table(snapshots, bins=None):
    """Calibración con n EN MERCADOS. Los buckets con n<30 salen marcados."""
    import pandas as pd

    bins = bins or [0, .02, .05, .10, .20, .35, .50, .65, .80, .90, .95, .98, 1.0]
    work = snapshots.assign(_bucket=pd.cut(snapshots["p"], bins))
    rows = []
    for bucket, group in work.groupby("_bucket", observed=True):
        rows.append({
            "bucket": str(bucket),
            "n_markets": len(group),
            "p_mean": float(group["p"].mean()),
            "freq": float(group["y"].mean()),
            "bias_pp": float((group["y"].mean() - group["p"].mean()) * 100),
            "thin": len(group) < N_MIN_CONCLUYENTE,
        })
    return pd.DataFrame(rows)


def fit_recalibration(p_train, y_train, n_bins=8):
    """Mapa p_mercado -> p_modelo por binning isotónico-lite.

    Deliberadamente simple: si un mapa de 8 parámetros no le gana al mercado
    fuera de muestra, uno de 800 tampoco lo hará por buenas razones.
    """
    p_train = np.asarray(p_train, dtype=float)
    y_train = np.asarray(y_train, dtype=float)
    edges = np.quantile(p_train, np.linspace(0, 1, n_bins + 1))
    edges = np.unique(edges)
    if len(edges) < 3:
        return lambda p: np.asarray(p, dtype=float)
    idx = np.clip(np.digitize(p_train, edges[1:-1]), 0, len(edges) - 2)
    targets = np.array([
        y_train[idx == b].mean() if (idx == b).sum() >= N_MIN_CONCLUYENTE
        else np.nan
        for b in range(len(edges) - 1)
    ])
    # Un bin con muestra chica NO se ajusta: se deja pasar el precio del mercado.
    def apply(p):
        p = np.asarray(p, dtype=float)
        b = np.clip(np.digitize(p, edges[1:-1]), 0, len(edges) - 2)
        out = targets[b]
        return np.where(np.isnan(out), p, out)

    return apply


def walk_forward_advantage(snapshots, *, n_folds=4, time_col="end_date"):
    """Walk-forward por tiempo: cada pliegue se prueba con lo ANTERIOR.

    Devuelve (resultado_mercado, resultado_modelo, edge_pp, n_oos).
    """
    ordered = snapshots.sort_values(time_col).reset_index(drop=True)
    n = len(ordered)
    if n < N_MIN_CONCLUYENTE * 2:
        return None

    cuts = np.linspace(0, n, n_folds + 2).astype(int)
    p_mkt_oos, p_mod_oos, y_oos = [], [], []
    for k in range(1, len(cuts) - 1):
        train = ordered.iloc[: cuts[k]]
        test = ordered.iloc[cuts[k] : cuts[k + 1]]
        if len(train) < N_MIN_CONCLUYENTE or len(test) == 0:
            continue
        mapper = fit_recalibration(train["p"], train["y"])
        p_mkt_oos.append(test["p"].to_numpy(dtype=float))
        p_mod_oos.append(mapper(test["p"]))
        y_oos.append(test["y"].to_numpy(dtype=float))

    if not y_oos:
        return None
    p_mkt = np.concatenate(p_mkt_oos)
    p_mod = np.concatenate(p_mod_oos)
    y = np.concatenate(y_oos)
    return (
        brier_of(p_mkt, y),
        brier_of(p_mod, y),
        realized_edge_pp(p_mkt, p_mod, y),
        len(y),
    )


def realized_edge_pp(p_market, p_model, outcomes, threshold=0.0):
    """Lo que de verdad ganarías, en puntos por acción.

    Compras YES si el modelo dice que está barato, NO si dice que está caro.
    edge = mean((y - p_mkt) * direccion). Se compara con el breakeven del paso 2.
    """
    p_market = np.asarray(p_market, dtype=float)
    p_model = np.asarray(p_model, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    diff = p_model - p_market
    trade = np.abs(diff) > threshold
    if trade.sum() == 0:
        return {"edge_pp": float("nan"), "n_trades": 0, "frac_traded": 0.0}
    direction = np.sign(diff[trade])
    pnl = (outcomes[trade] - p_market[trade]) * direction
    return {
        "edge_pp": float(pnl.mean() * 100),
        "n_trades": int(trade.sum()),
        "frac_traded": float(trade.mean()),
        # error estandar: sin esto, un edge de 0.5pp con n=300 parece un hallazgo
        "se_pp": float(pnl.std(ddof=1) / np.sqrt(len(pnl)) * 100),
    }


def format_report(descartes, por_lead, wf, *, breakeven_pp, vol_min) -> str:
    lines = []
    add = lines.append
    add("=" * 78)
    add("BRIER ADVANTAGE — ¿LE GANAMOS AL PRECIO DE POLYMARKET?")
    add("=" * 78)
    add(f"corte: mercados resueltos con vol >= ${vol_min:,.0f}")
    add("")
    add("-- HIGIENE: el 0.50 no es un desenlace --")
    add(f"  cerrados                {descartes['cerrados']:,}")
    add(f"  con resolución limpia   {descartes['resueltos']:,} "
        f"({descartes['resueltos'] / max(descartes['cerrados'], 1):.1%})")
    add(f"  DESCARTADOS             {descartes['sin_desenlace']:,} "
        f"(de esos, {descartes['en_050_exacto']:,} en 0.50 exacto)")
    add("")
    add("-- EL MERCADO CONTRA SÍ MISMO (una observación por MERCADO) --")
    add(f"  {'lead':>8} {'n mkts':>8} {'Brier':>8} {'skill':>8} {'sesgo':>9}")
    for lead, res in por_lead:
        mark = "  << n<30, NO CONCLUYE" if res.thin else ""
        add(f"  {lead:>8} {res.n_markets:>8,} {res.brier:>8.4f} {res.skill:>+8.3f} "
            f"{res.bias_pp:>+8.2f}pp{mark}")
    add("")
    if wf is None:
        add("-- WALK-FORWARD: muestra insuficiente para pliegues OOS --")
    else:
        mkt, mod, edge, n_oos = wf
        add(f"-- ¿UNA RECALIBRACIÓN LE GANA? (walk-forward, n_oos={n_oos:,} mercados) --")
        add(f"  Brier del MERCADO      {mkt.brier:.4f}")
        add(f"  Brier del MODELO       {mod.brier:.4f}")
        add(f"  Brier advantage        {mkt.brier - mod.brier:+.4f}  "
            f"({'el modelo gana' if mod.brier < mkt.brier else 'el MERCADO gana'})")
        add("")
        add(f"  edge realizado         {edge['edge_pp']:+.2f} pp  ± {edge['se_pp']:.2f} (1 EE)")
        add(f"  breakeven (paso 2)     {breakeven_pp:.2f} pp")
        ic_low = edge["edge_pp"] - 1.96 * edge["se_pp"]
        ic_high = edge["edge_pp"] + 1.96 * edge["se_pp"]
        add(f"  IC95% del edge         [{ic_low:+.2f}, {ic_high:+.2f}] pp")
        vive = ic_low > breakeven_pp
        add(f"  → {'SUPERA el breakeven con IC95% > 0' if vive else 'NO supera el breakeven'}")
    add("")
    add("-- POR QUÉ LA n ES DE MERCADOS Y NO DE TRADES --")
    add("  La primera versión ponderó por trade y encontró un sesgo de -4/-5pp")
    add("  en el tramo 0.35-0.80. Era un ARTEFACTO: un mercado que cae de 0.60 a")
    add("  0 genera enorme volumen en la caída, así que ponderar por trade")
    add("  sobre-muestrea 'estaba caro y resolvió NO'. Por mercado, el sesgo a 1h")
    add("  es +0.22pp. Los trades del mismo mercado no son independientes.")
    add("=" * 78)
    return "\n".join(lines)


def main(argv=None) -> int:
    import pandas as pd

    from tools.polymarket_spread import TRADE_COLUMNS, normalize_yes, sample_row_groups

    parser = argparse.ArgumentParser(description="Brier advantage sobre Polymarket")
    parser.add_argument("--markets", required=True)
    parser.add_argument("--row-groups", type=int, default=60)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--vol-min", type=float, default=100_000.0)
    parser.add_argument("--breakeven-pp", type=float, default=0.95,
                        help="spread/2 medido en el paso 2")
    args = parser.parse_args(argv)

    markets = pd.read_parquet(
        args.markets,
        columns=["id", "closed", "outcome_prices", "volume", "end_date", "created_at"],
    )
    resolved, descartes = clean_resolutions(markets)
    print(f"resolución limpia: {descartes['resueltos']:,} de {descartes['cerrados']:,} cerrados")

    parquet, groups = sample_row_groups(args.row_groups, year=args.year)
    leads = (("~1h", 1.0, 2.0), ("~6h", 6.0, 6.0), ("~24h", 24.0, 24.0))

    # Se reduce POR row group: 56 row groups crudos son ~6.6 GB en RAM, y el
    # snapshot que sobrevive son unos miles de filas. Concatenar primero y
    # filtrar después revienta la máquina sin necesidad.
    acumulado: dict[str, list] = {label: [] for label, _, _ in leads}
    for i, rg in enumerate(groups, 1):
        chunk = normalize_yes(parquet.read_row_group(rg, columns=TRADE_COLUMNS).to_pandas())
        chunk["market_id"] = chunk["market_id"].astype(str)
        for label, lead, tol in leads:
            acumulado[label].append(market_snapshots(
                chunk, resolved, lead_hours=lead, tolerance_hours=tol, vol_min=args.vol_min
            ))
        del chunk
        if i % 10 == 0 or i == len(groups):
            print(f"  leidos {i}/{len(groups)} row groups", flush=True)

    por_lead = []
    snaps_24 = None
    for label, lead, _ in leads:
        snaps = pd.concat(acumulado[label], ignore_index=True)
        # Un mercado puede aparecer en varios row groups: se queda el trade MÁS
        # cercano al lead objetivo. Sin esto, el mercado entraría dos veces y
        # volvería el bug de la n inflada por la puerta de atrás.
        snaps = (snaps.assign(_d=(snaps["lead_h"] - lead).abs())
                      .sort_values("_d")
                      .groupby("market_id", as_index=False).first()
                      .drop(columns="_d"))
        por_lead.append((label, brier_of(snaps["p"], snaps["y"])))
        if label == "~24h":
            snaps_24 = snaps

    print("\n-- calibración por bucket a ~24h (n en MERCADOS) --")
    print(calibration_table(snaps_24).to_string(index=False))

    wf = walk_forward_advantage(snaps_24)
    print()
    print(format_report(descartes, por_lead, wf,
                        breakeven_pp=args.breakeven_pp, vol_min=args.vol_min))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
