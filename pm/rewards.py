# -*- coding: utf-8 -*-
"""
================================================================================
  PM REWARDS - la matematica del programa de Liquidity Rewards de Polymarket
  by RasDG_Sol + Claude

  Puro: recibe libros, devuelve numeros. Sin red, sin estado, sin claves.
  Es la pieza que contesta la UNICA pregunta que decide si el bot vale la pena:
  con $X de capital cotizando en un mercado, ¿cuanto nos toca del pool diario?

  Formulas (docs.polymarket.com/programs/liquidity-rewards, ago-2026):

    1) Puntaje de una orden (regla cuadratica en la distancia al midpoint):
         S(v, s) = ((v - s) / v)^2 · b
       v = max_spread del mercado en centavos, s = distancia de la orden al
       midpoint ajustado en centavos, b = multiplicador in-game (1 por default).
       Ojo con la no-linealidad: al DOBLE de distancia, un CUARTO de puntos.

    2) Q_one = Σ S·BidSize(YES) + Σ S·AskSize(NO)
    3) Q_two = Σ S·AskSize(YES) + Σ S·BidSize(NO)
       Los dos "lados" no son bid/ask: son las dos formas de estar largo o corto
       del evento. Comprar NO equivale a vender YES -> se puede estar en los DOS
       lados usando solo efectivo, sin inventario de shares. Con $500 eso es todo.

    4) Q_min: premia estar en los dos lados.
         midpoint en [0.10, 0.90]:  max(min(Q_one, Q_two), max(Q_one, Q_two)/c)
         midpoint fuera del rango:  min(Q_one, Q_two)   <- un solo lado NO puntua
       c = 3.0 (factor de escala vigente en todos los mercados).

    5) Q_normal = Q_min / Σ Q_min de todos los makers  (por muestra, cada minuto)
    6) Q_epoch  = Σ Q_normal sobre las muestras de la epoca
    7) Q_final  = Q_epoch / Σ Q_epoch  ->  reward = Q_final · pool del mercado

  SESGO DEL ESTIMADOR (importante, y a favor):
  el libro publico agrega a todos los makers en un solo nivel de precio, no
  sabemos quien puso que. Al tratar al libro entero como UN maker calculamos
  Q_min(agregado), y por la desigualdad min(Σ) >= Σ min, eso es MAYOR O IGUAL a
  la suma de los Q_min individuales reales. Es decir: SOBREestimamos a la
  competencia -> SUBestimamos nuestra parte. El error empuja al "no". Para una
  decision de si arriesgar $500, ese es el sesgo correcto.
================================================================================
"""
from typing import Iterable, Optional, Sequence, Tuple

# Factor de escala del ajuste de un solo lado. Constante en todos los mercados
# segun la doc; se deja parametrizable por si cambia.
DEFAULT_C = 3.0

# Fuera de esta banda de midpoint, cotizar un solo lado NO puntua.
TWO_SIDED_ONLY_BELOW = 0.10
TWO_SIDED_ONLY_ABOVE = 0.90

Level = Tuple[float, float]  # (precio, tamano en shares)


def score_order(max_spread_cents: float, spread_cents: float, b: float = 1.0) -> float:
    """S(v, s) = ((v - s) / v)^2 · b. Cero si la orden esta fuera del max spread
    (o si el mercado no tiene max spread configurado)."""
    if max_spread_cents <= 0:
        return 0.0
    if spread_cents < 0:
        spread_cents = 0.0
    if spread_cents >= max_spread_cents:
        return 0.0
    return ((max_spread_cents - spread_cents) / max_spread_cents) ** 2 * b


def _levels(raw: Optional[Iterable]) -> list:
    """Normaliza niveles de libro a [(precio, tamano)]. Acepta objetos del
    cliente (.price/.size), dicts o tuplas. Descarta lo que no parsee: un libro
    mal formado no debe tumbar la corrida de una semana."""
    out = []
    for lv in raw or []:
        try:
            if isinstance(lv, (tuple, list)):
                p, s = float(lv[0]), float(lv[1])
            elif isinstance(lv, dict):
                p, s = float(lv["price"]), float(lv["size"])
            else:
                p, s = float(lv.price), float(lv.size)
        except (TypeError, ValueError, KeyError, IndexError, AttributeError):
            continue
        if s > 0:
            out.append((p, s))
    return out


def best_bid(bids: Optional[Iterable], min_size: float = 0.0) -> Optional[float]:
    """Mejor bid con tamano >= min_size (el corte que usa el midpoint ajustado)."""
    lv = [p for p, s in _levels(bids) if s >= min_size]
    return max(lv) if lv else None


def best_ask(asks: Optional[Iterable], min_size: float = 0.0) -> Optional[float]:
    """Mejor ask con tamano >= min_size."""
    lv = [p for p, s in _levels(asks) if s >= min_size]
    return min(lv) if lv else None


def adjusted_midpoint(bids, asks, min_size: float = 0.0) -> Optional[float]:
    """Midpoint ajustado por el corte de tamano: promedio del mejor bid y el
    mejor ask que superan min_size. None si falta un lado."""
    b = best_bid(bids, min_size)
    a = best_ask(asks, min_size)
    if b is None or a is None:
        return None
    return (b + a) / 2.0


def _side_points(levels, reference: Optional[float], max_spread_cents: float,
                 min_size: float, b: float = 1.0) -> float:
    """Σ S(v, s)·size sobre los niveles que califican (tamano >= min_size y
    dentro del max spread). `reference` es el midpoint contra el que se mide la
    distancia, en el espacio de precios de ESE token."""
    if reference is None:
        return 0.0
    total = 0.0
    for p, s in _levels(levels):
        if s < min_size:
            continue
        spread_cents = abs(reference - p) * 100.0
        total += score_order(max_spread_cents, spread_cents, b) * s
    return total


def side_scores(yes_bids, yes_asks, no_bids, no_asks, mid_yes: Optional[float],
                max_spread_cents: float, min_size: float, b: float = 1.0):
    """Devuelve (Q_one, Q_two) del libro tal como se observa.

    mid_yes es el midpoint ajustado del token YES; el del NO es su complemento
    (1 - mid_yes), porque los dos libros son el mismo evento visto al reves.
    """
    mid_no = None if mid_yes is None else 1.0 - mid_yes
    q_one = (_side_points(yes_bids, mid_yes, max_spread_cents, min_size, b)
             + _side_points(no_asks, mid_no, max_spread_cents, min_size, b))
    q_two = (_side_points(yes_asks, mid_yes, max_spread_cents, min_size, b)
             + _side_points(no_bids, mid_no, max_spread_cents, min_size, b))
    return q_one, q_two


def q_min(q_one: float, q_two: float, midpoint: Optional[float],
          c: float = DEFAULT_C) -> float:
    """Ecuacion 4. En las colas (midpoint < 0.10 o > 0.90) exige los dos lados;
    en el centro tolera un solo lado dividido por c."""
    if midpoint is None:
        return 0.0
    two_sided = min(q_one, q_two)
    if midpoint < TWO_SIDED_ONLY_BELOW or midpoint > TWO_SIDED_ONLY_ABOVE:
        return two_sided
    if c <= 0:
        return two_sided
    return max(two_sided, max(q_one, q_two) / c)


def our_q_min(size_shares: float, spread_cents: float, midpoint: Optional[float],
              max_spread_cents: float, min_size: float, b: float = 1.0,
              c: float = DEFAULT_C) -> float:
    """Q_min de NUESTRA cotizacion si ponemos `size_shares` en los dos lados a
    `spread_cents` del midpoint, usando solo efectivo (bid en YES + bid en NO).

    Un bid en YES puntua en Q_one y un bid en NO puntua en Q_two -> la
    cotizacion queda simetrica y min(Q_one, Q_two) = S·size, que es el maximo
    puntaje posible para ese capital. Ordenes por debajo de min_size no
    califican: devuelve 0.
    """
    if size_shares < min_size or size_shares <= 0:
        return 0.0
    s = score_order(max_spread_cents, spread_cents, b) * size_shares
    return q_min(s, s, midpoint, c)


def capital_for_two_sided(size_shares: float, midpoint: float,
                          spread_cents: float) -> float:
    """Efectivo (pUSD) que inmoviliza cotizar `size_shares` en los dos lados.

    bid YES a (mid - s) + bid NO a (1 - mid - s) => size · (1 - 2s).
    Regla de bolsillo que sale de aca: **$1 de capital ~ 1 share de profundidad
    calificada a dos lados**, casi independiente del precio del mercado.
    """
    s = spread_cents / 100.0
    price_yes = max(midpoint - s, 0.0)
    price_no = max(1.0 - midpoint - s, 0.0)
    return size_shares * (price_yes + price_no)


def estimate_daily_reward(daily_pool: float, book_q_min: float,
                          our_q: float) -> float:
    """Reward diario estimado = pool · nuestra parte del puntaje.

    Aproximacion deliberadamente simple: la formula real normaliza por muestra
    y despues por epoca, pero si nuestra cotizacion y el libro son estables a lo
    largo del dia las dos normalizaciones se cancelan y queda la razon directa.
    La varianza real se mide con la MEDIANA sobre las muestras de la Fase 0, no
    con esta formula sola.
    """
    denom = book_q_min + our_q
    if denom <= 0:
        return 0.0
    return daily_pool * (our_q / denom)


def sweep_spreads(daily_pool: float, book_q_min: float, capital_usd: float,
                  midpoint: Optional[float], max_spread_cents: float,
                  min_size: float, spreads_cents: Sequence[float] = (0.5, 1.0, 2.0, 3.0),
                  c: float = DEFAULT_C) -> list:
    """Barre distancias al midpoint y devuelve, para cada una, el tamano que
    cabe con `capital_usd`, nuestro Q_min y el reward diario estimado.

    Sirve para ver el trade-off central del market making: mas pegado al
    midpoint puntua mucho mas (cuadratico) pero te ejecutan mas seguido, que es
    donde vive el costo real (seleccion adversa).
    """
    out = []
    if midpoint is None or capital_usd <= 0:
        return out
    for sc in spreads_cents:
        if sc >= max_spread_cents > 0:
            continue
        unit = capital_for_two_sided(1.0, midpoint, sc)
        size = capital_usd / unit if unit > 0 else 0.0
        oq = our_q_min(size, sc, midpoint, max_spread_cents, min_size, c=c)
        out.append({
            "spread_cents": sc,
            "size_shares": size,
            "qualifies": size >= min_size,
            "our_q_min": oq,
            "est_daily_usd": estimate_daily_reward(daily_pool, book_q_min, oq),
        })
    return out
