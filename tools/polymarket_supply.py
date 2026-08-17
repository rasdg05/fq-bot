# -*- coding: utf-8 -*-
"""
Oferta capturable de Polymarket — el sondeo barato que decide si vale la pena.

NO mide edge. NO propone estrategia. Contesta UNA pregunta, la única que se
puede contestar sin arriesgar un peso: **¿cuántos mercados de Polymarket tienen
volumen y horizonte suficientes para que un edge sea capturable, y cuánto
capital-tiempo cuesta cada uno?**

Si la respuesta es "trescientos mercados al año", el proyecto se muere aquí y
nos ahorramos el resto. Ese es el punto.

## La aritmética (todo en dólares y puntos de probabilidad)

Compras N acciones a precio `p`; cada una paga $1 si resuelve Sí.
  capital desplegado = N·p
  si tu probabilidad real es p+e (edge `e` en puntos), valor = N·(p+e)
  ganancia          = N·e
  retorno sobre capital, por mercado = e/p          <- NO depende del tamaño

Ese retorno se cobra una vez por vida del mercado. Anualizado:

  retorno_anual = (e/p) · (365/h)        h = horizonte en días

Sobre un universo de mercados, el horizonte que manda es el **ponderado por
volumen** (`h_w = Σ(V·h)/ΣV`), porque el capital se reparte proporcional al
tamaño de cada mercado. De ahí sale la identidad que gobierna todo el análisis:

  retorno_anual = 365·e / (p · h_w)
  capital_pico  = q · Σ(V·h) / 365        q = participación sobre el volumen

La participación `q` **se cancela del retorno**: solo fija la ESCALA (cuánto
capital cabe), no el rendimiento. Por eso `h_w` es el número que decide.

## Por qué esto importa a este repo en particular

El motor de perps muere por coste de EJECUCIÓN: +0.224R bruto en el cube →
−0.510R neto con fees. Aquí el coste tiene otra forma: se cruza el spread UNA
vez si se aguanta hasta la resolución (no hay salida que pagar), y a cambio el
capital queda inmovilizado `h` días. El breakeven no es un win-rate: es

  e > spread/2      (media horquilla, cruzando una sola vez)

y la pregunta de rentabilidad no es "¿gano?" sino "¿gano lo suficiente por
día de capital inmovilizado?".

## Lo que este tool NO puede contestar (y qué archivo sí)

`markets.parquet` no trae libro ni precios de trade: **el spread no se mide
aquí**. Sin spread no hay breakeven, y sin breakeven no hay veredicto. Ese dato
está en `trades.parquet` (32 GB) / `quant.parquet` (21 GB) del mismo dataset.
Este sondeo es el paso 1 de 2, a propósito: cuesta 281 MB en vez de 53 GB.

## Data

  https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data → markets.parquet
  curl -sSL https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data/\
resolve/main/markets.parquet -o markets.parquet

Uso:
  python tools/polymarket_supply.py --markets markets.parquet
  python tools/polymarket_supply.py --markets markets.parquet \
      --vol-min 100000 --horizon-max 7 --edge-pp 2 --avg-price 0.5 --participation 0.02
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field

# n mínima para que un desglose CONCLUYA. Regla de la casa (CLAUDE.md): con
# muestra chica, ordenar por resultado selecciona ruido. No se diluye en el
# promedio: se marca.
N_MIN_CONCLUYENTE = 30

# Columnas que el sondeo consume. `active`/`archived`/`neg_risk` no se usan en
# ningún cálculo: se cargan A PROPÓSITO para que el chequeo de constantes las
# vea. Un detector de columnas muertas que solo mira las columnas que ya usas no
# detecta nada — es justo así como `vp_basis` sobrevivió constante.
COLUMNS = [
    "question", "volume", "created_at", "end_date",
    "closed", "active", "archived", "neg_risk",
]


@dataclass
class Hygiene:
    """Lo que está mal en el dato ANTES de medir nada.

    Existe porque una métrica demasiado limpia es un bug, no un hallazgo. Cada
    fila que se excluye queda CONTADA: excluir en silencio es cómo nació el
    fantasma de julio.
    """

    n_rows: int
    n_horizon_nonpositive: int
    n_volume_zero: int
    n_question_duplicated: int
    constant_columns: dict[str, object] = field(default_factory=dict)

    @property
    def n_usable(self) -> int:
        return self.n_rows - self.n_horizon_nonpositive


@dataclass
class Capacity:
    """Capacidad de un corte del universo. `thin` marca la muestra chica."""

    n: int
    volume_usd: float
    wavg_horizon_days: float
    peak_capital_usd: float
    annual_return: float
    breakeven_spread_pp: float

    @property
    def thin(self) -> bool:
        return self.n < N_MIN_CONCLUYENTE


def constant_columns(frame) -> dict[str, object]:
    """Delata columnas constantes — la lección `vp_basis` (BRIEF E1).

    Una feature que nunca cambia no es una feature: es una columna que alguien
    creyó que medía algo. El snapshot debe delatarla, no enterrarla.
    """
    found: dict[str, object] = {}
    for col in frame.columns:
        series = frame[col].dropna()
        if len(series) == 0:
            continue
        uniques = series.unique()
        if len(uniques) == 1:
            found[col] = uniques[0]
    return found


def hygiene_report(frame) -> Hygiene:
    horizon = horizon_days(frame)
    return Hygiene(
        n_rows=len(frame),
        n_horizon_nonpositive=int((horizon <= 0).sum()),
        n_volume_zero=int((frame["volume"] == 0).sum()),
        n_question_duplicated=int(frame["question"].duplicated().sum()),
        constant_columns=constant_columns(frame),
    )


def horizon_days(frame):
    """Horizonte en días: de la creación al cierre declarado del mercado."""
    return (frame["end_date"] - frame["created_at"]).dt.total_seconds() / 86400.0


def capturable_universe(frame, vol_min: float, horizon_max_days: float):
    """El corte que un operador podría tocar.

    Excluye horizonte no-positivo (dato roto: `end_date` antes de `created_at`).
    La exclusión NO es silenciosa — `hygiene_report` la cuenta, y el reporte la
    imprime encima de cualquier número.
    """
    horizon = horizon_days(frame)
    keep = (horizon > 0) & (horizon <= horizon_max_days) & (frame["volume"] >= vol_min)
    out = frame.loc[keep].copy()
    out["horizon_days"] = horizon.loc[keep]
    return out


def capacity(
    universe,
    *,
    edge_pp: float,
    avg_price: float,
    participation: float,
    span_days: float,
    spread_pp: float = 0.0,
) -> Capacity:
    """Capacidad y retorno anualizado NETO de horquilla.

    `edge_pp`, `avg_price`, `participation` y `spread_pp` son INPUTS, no
    mediciones — igual que `impact_coef` en `capacity_analysis.py`. El valor de
    esto es el marco y la sensibilidad, no un número mágico.

    El neteo importa más aquí que en el motor de perps, y en la dirección
    contraria a la intuición: aguantando a resolución se cruza la horquilla UNA
    sola vez (no hay salida que pagar), así que

        edge_neto = edge − spread/2

    pero ese neteo se multiplica por 365/h_pond igual que el bruto. Con h_pond
    de días, el multiplicador anual es de tres cifras: **el mismo apalancamiento
    temporal que hace atractivo un edge chico convierte una horquilla chica en
    ruina**. Por eso `breakeven_spread_pp` viaja pegado al retorno.
    """
    n = len(universe)
    if n == 0:
        return Capacity(0, 0.0, float("nan"), 0.0, float("nan"), float("nan"))

    volume = universe["volume"].astype(float)
    horizon = universe["horizon_days"].astype(float)
    volume_usd = float(volume.sum())

    # Horizonte ponderado por volumen: el capital se reparte proporcional al
    # tamaño, así que el promedio simple mentiría a favor de los mercados dust.
    wavg_horizon = float((volume * horizon).sum() / volume_usd) if volume_usd > 0 else float("nan")

    # Capital-tiempo: dólares·día que exige el corte, prorrateado a la ventana
    # observada. Es el techo de despliegue, no una promesa de retorno.
    capital_days = float((volume * horizon).sum()) * participation
    peak_capital = capital_days / span_days if span_days > 0 else float("nan")

    # Se cruza la horquilla una vez (se aguanta a resolución): coste = spread/2.
    net_edge = (edge_pp - spread_pp / 2.0) / 100.0
    annual_return = (
        (net_edge / avg_price) * (365.0 / wavg_horizon)
        if avg_price > 0 and wavg_horizon and wavg_horizon > 0
        else float("nan")
    )
    # La horquilla que anula el edge. Si el spread real la supera, no hay
    # estrategia posible en este corte: el veredicto no depende del modelo.
    breakeven_spread = 2.0 * edge_pp
    return Capacity(
        n, volume_usd, wavg_horizon, peak_capital, annual_return, breakeven_spread
    )


def capacity_by_year(frame, *, vol_min, horizon_max_days, **kwargs) -> dict[int, Capacity]:
    """Desglose por año. NUNCA se devuelve un agregado sin esto (BRIEF E9).

    El espejismo de mayo fue un agregado sobre un solo régimen presentado como
    ley. En Polymarket el régimen es el AÑO: 2024 fue la elección de EE. UU.
    (mercados largos), 2026 es el mercado por horas. Promediarlos inventa un
    mercado que no existe.
    """
    universe = capturable_universe(frame, vol_min, horizon_max_days)
    out: dict[int, Capacity] = {}
    for year, chunk in universe.groupby(universe["created_at"].dt.year):
        span = year_span_days(chunk)
        out[int(year)] = capacity(chunk, span_days=span, **kwargs)
    return out


def year_span_days(chunk) -> float:
    """Días observados del año, no 365.

    El último año del dataset está truncado: contar 365 sub-estimaría el
    capital pico repartiendo doce meses de volumen sobre siete.
    """
    created = chunk["created_at"]
    observed = (created.max() - created.min()).total_seconds() / 86400.0
    return max(observed, 1.0)


def format_report(
    hygiene: Hygiene,
    by_year: dict[int, Capacity],
    *,
    vol_min: float,
    horizon_max_days: float,
    edge_pp: float,
    avg_price: float,
    participation: float,
    spread_pp: float = 0.0,
) -> str:
    """Arma el reporte. Falla si le falta el desglose — esa es la vacuna.

    Criterio de aceptación de E9: que sea IMPOSIBLE imprimir un agregado sin
    que salga al lado su desglose por régimen con su n.
    """
    if not by_year:
        raise ValueError(
            "No hay desglose por año: el reporte agregado no se imprime sin él "
            "(BRIEF E9). Revisa el corte — probablemente vol_min u horizon_max "
            "dejaron el universo vacío."
        )

    lines: list[str] = []
    add = lines.append

    add("=" * 74)
    add("OFERTA CAPTURABLE — POLYMARKET")
    add("=" * 74)
    add(
        f"corte: volumen >= ${vol_min:,.0f} · horizonte <= {horizon_max_days:g}d · "
        f"edge {edge_pp:g}pp · spread {spread_pp:g}pp · precio medio {avg_price:g} · "
        f"participación {participation:.1%}"
    )
    if spread_pp == 0:
        add("       SPREAD = 0: el retorno de abajo es BRUTO. No es un resultado.")
    add("")

    add("-- HIGIENE DEL DATO (antes de creerse cualquier número) --")
    add(f"  filas                         {hygiene.n_rows:,}")
    add(
        f"  horizonte <= 0 (EXCLUIDAS)    {hygiene.n_horizon_nonpositive:,}"
        f"  ({hygiene.n_horizon_nonpositive / max(hygiene.n_rows, 1):.2%}) "
        "— end_date antes de created_at"
    )
    add(f"  volumen == 0                  {hygiene.n_volume_zero:,}")
    add(f"  preguntas duplicadas          {hygiene.n_question_duplicated:,}")
    if hygiene.constant_columns:
        add("  COLUMNAS CONSTANTES (no son features, son columnas):")
        for col, value in hygiene.constant_columns.items():
            add(f"    · {col} = {value!r} en todas las filas")
    else:
        add("  columnas constantes           ninguna")
    add("")

    add("-- CAPACIDAD POR AÑO (el año ES el régimen; agregarlos inventa un mercado) --")
    add(
        f"  {'año':>6} {'n':>9} {'volumen':>13} {'h_pond':>9} {'vueltas/año':>12} "
        f"{'capital pico':>14} {'ret. anual':>11}"
    )
    for year in sorted(by_year):
        cap = by_year[year]
        mark = "  << n<30, NO CONCLUYE" if cap.thin else ""
        turns = 365.0 / cap.wavg_horizon_days if cap.wavg_horizon_days > 0 else float("nan")
        add(
            f"  {year:>6} {cap.n:>9,} {cap.volume_usd / 1e6:>11,.0f}M "
            f"{cap.wavg_horizon_days:>8.2f}d {turns:>11.0f}x "
            f"{cap.peak_capital_usd / 1e6:>12,.1f}M {cap.annual_return:>10.1%}{mark}"
        )
    add("")

    gordos = [c for c in by_year.values() if not c.thin]
    if gordos:
        be = max(c.breakeven_spread_pp for c in gordos)
        add(f"-- LA HORQUILLA QUE LO MATA TODO: spread >= {be:g}pp --")
        add("  Con un edge supuesto de "
            f"{edge_pp:g}pp, cualquier horquilla media por encima de {be:g}pp")
        add("  deja el retorno en cero o negativo, en TODOS los años. Y la")
        add("  multiplicación funciona en los dos sentidos: las mismas ~100 vueltas")
        add("  al año que hacen atractivo un edge chico convierten un spread chico")
        add("  en ruina. El spread NO está medido aquí — es el paso 2.")
        add("")

    add("-- CÓMO LEER ESTO --")
    add("  h_pond      horizonte ponderado por VOLUMEN. Manda sobre el mediano:")
    add("              el capital se reparte proporcional al tamaño del mercado.")
    add("  ret. anual  365·edge/(precio·h_pond). NO depende del tamaño de la")
    add("              apuesta: la participación solo fija cuánto capital cabe.")
    add("  cap. pico   techo de despliegue simultáneo con esa participación.")
    add("")
    add("  El `edge` es un SUPUESTO, no una medición: entra por parámetro.")
    add("  `markets.parquet` no trae libro, así que el spread real de este venue")
    add("  no se puede medir aquí — se asume. Medirlo exige trades/quant.parquet")
    add("  (53 GB). Este sondeo es el paso 1 de 2, y a propósito.")
    add("")
    add("  SESGO CONOCIDO: `volume` es acumulado-a-la-fecha. Un mercado largo")
    add("  creado hace poco todavía no acumuló su volumen, así que los cortes de")
    add("  horizonte largo salen sub-contados en el año más reciente. No compares")
    add("  volumen entre años sin acordarte de esto.")
    add("=" * 74)
    return "\n".join(lines)


def load_markets(path: str):
    import pandas as pd

    return pd.read_parquet(path, columns=COLUMNS)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--markets", required=True, help="ruta a markets.parquet")
    parser.add_argument("--vol-min", type=float, default=100_000.0)
    parser.add_argument("--horizon-max", type=float, default=7.0, help="días")
    parser.add_argument("--edge-pp", type=float, default=2.0, help="edge supuesto, en puntos")
    parser.add_argument(
        "--spread-pp", type=float, default=0.0,
        help="horquilla media supuesta, en puntos. Se cruza UNA vez (coste=spread/2)",
    )
    parser.add_argument("--avg-price", type=float, default=0.5)
    parser.add_argument("--participation", type=float, default=0.02)
    args = parser.parse_args(argv)

    frame = load_markets(args.markets)
    hygiene = hygiene_report(frame)
    by_year = capacity_by_year(
        frame,
        vol_min=args.vol_min,
        horizon_max_days=args.horizon_max,
        edge_pp=args.edge_pp,
        spread_pp=args.spread_pp,
        avg_price=args.avg_price,
        participation=args.participation,
    )
    print(
        format_report(
            hygiene,
            by_year,
            vol_min=args.vol_min,
            horizon_max_days=args.horizon_max,
            edge_pp=args.edge_pp,
            spread_pp=args.spread_pp,
            avg_price=args.avg_price,
            participation=args.participation,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
