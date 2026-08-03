# -*- coding: utf-8 -*-
"""
================================================================================
  PM PROBE - Fase 0: medir antes de arriesgar (read-only, sin claves, $0)
  by RasDG_Sol + Claude

  El recolector que contesta la pregunta que ningun prompt puede contestar:
  ¿hay mercados con pool de rewards decente y POCA profundidad calificada
  compitiendo? Si la respuesta es no, nos bajamos sin gastar un peso.

  NO autentica. NO manda ordenes. NO toca dinero. Solo lee endpoints publicos
  del CLOB y escribe una linea JSON por (muestra, mercado).

  Que registra por muestra:
    · midpoint ajustado por el corte de tamano del mercado
    · Q_one / Q_two / Q_min del libro AGREGADO -> la competencia a batir
    · profundidad calificada en shares y en USD dentro del max_spread
    · pool diario (rewards_daily_rate), min_size y max_spread del mercado
    · niveles del libro cerca del midpoint (para el replay de la Fase 2)
    · vigilante de arb: yes_ask+no_ask y yes_bid+no_bid, por si algun dia se
      descuadra de verdad (medido: nunca en 400 mercados, min 1.0010)

  Uso:
    python -m pm.probe --minutes 20 --interval 60 --top 40
    python -m pm.probe --once --top 10          # prueba rapida

  El cliente se inyecta (client=...) para poder testear sin red.
================================================================================
"""
import os
import sys
import gzip
import json
import time
import logging
import argparse
from datetime import datetime, timezone

from pm import rewards

log = logging.getLogger("pm.probe")

HOST = os.environ.get("PM_CLOB_HOST", "https://clob.polymarket.com")
CHAIN_ID = int(os.environ.get("PM_CHAIN_ID", "137"))

# El endpoint /books rebota con 400 "Payload exceeds the limit" pasados ~50
# tokens por request. 40 deja margen.
BOOK_CHUNK = 40

# Niveles a guardar: los que caen dentro del max_spread mas este colchon, en
# centavos. Suficiente para el scoring y para el replay, sin inflar el archivo.
LEVEL_MARGIN_CENTS = 2.0

USDC_E = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"


def make_client():
    """Cliente publico del CLOB. Import perezoso: los tests no necesitan la
    libreria instalada para ejercitar la logica pura."""
    from py_clob_client_v2 import ClobClient
    return ClobClient(host=HOST, chain_id=CHAIN_ID, retry_on_error=True)


# ============================================================
# SELECCION DE MERCADOS
# ============================================================
def _daily_rate(rewards_cfg) -> float:
    """Suma de los pools diarios del mercado. Ignora los que no sean USDC.e
    (hay mercados con rates simbolicos en otros tokens)."""
    total = 0.0
    for r in (rewards_cfg or {}).get("rates") or []:
        try:
            addr = str(r.get("asset_address", "")).lower()
            if addr and addr != USDC_E:
                continue
            total += float(r.get("rewards_daily_rate") or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def select_markets(client, top_n: int = 40, min_daily: float = 1.0) -> list:
    """Mercados binarios abiertos con pool de rewards, ordenados por pool
    descendente. Excluye neg-risk (multi-resultado: otro contrato, otra
    mecanica; fuera del alcance de la v1)."""
    raw = client.get_sampling_markets()
    data = raw.get("data") if isinstance(raw, dict) else raw
    out = []
    for m in data or []:
        try:
            if not (m.get("accepting_orders") and m.get("enable_order_book")):
                continue
            if m.get("closed") or m.get("archived") or m.get("neg_risk"):
                continue
            tokens = m.get("tokens") or []
            if len(tokens) != 2:
                continue
            cfg = m.get("rewards") or {}
            daily = _daily_rate(cfg)
            if daily < min_daily:
                continue
            max_spread = float(cfg.get("max_spread") or 0.0)
            if max_spread <= 0:
                continue
            yes = next((t for t in tokens if str(t.get("outcome", "")).lower() == "yes"), tokens[0])
            no = next((t for t in tokens if t is not yes), tokens[1])
            out.append({
                "condition_id":   m.get("condition_id"),
                "slug":           m.get("market_slug"),
                "question":       (m.get("question") or "")[:120],
                "tags":           m.get("tags") or [],
                "yes_token_id":   yes.get("token_id"),
                "no_token_id":    no.get("token_id"),
                "daily_pool":     daily,
                "min_size":       float(cfg.get("min_size") or 0.0),
                "max_spread":     max_spread,
                "min_order_size": float(m.get("minimum_order_size") or 0.0),
                "tick_size":      float(m.get("minimum_tick_size") or 0.0),
                "end_date":       m.get("end_date_iso"),
            })
        except (TypeError, ValueError, AttributeError) as exc:
            log.debug("mercado descartado: %s", exc)
            continue
    out.sort(key=lambda x: -x["daily_pool"])
    return out[:top_n]


# ============================================================
# LIBROS
# ============================================================
def fetch_books(client, token_ids, chunk: int = BOOK_CHUNK, book_params=None) -> dict:
    """{token_id: book} pidiendo /books por lotes. Un lote que falla no tumba
    la muestra completa: se registra y se sigue.

    `book_params` se inyecta en los tests para no depender de la libreria."""
    if book_params is None:
        from py_clob_client_v2 import BookParams as book_params
    books = {}
    ids = list(token_ids)
    for i in range(0, len(ids), chunk):
        batch = ids[i:i + chunk]
        try:
            for b in client.get_order_books([book_params(token_id=t) for t in batch]):
                tid = getattr(b, "asset_id", None) or (b.get("asset_id") if isinstance(b, dict) else None)
                if tid:
                    books[tid] = b
        except Exception as exc:                      # noqa: BLE001 - red inestable
            log.warning("lote de libros fallido (%d tokens): %s", len(batch), exc)
    return books


def _side(book, key):
    if book is None:
        return []
    return (getattr(book, key, None) if not isinstance(book, dict) else book.get(key)) or []


def _trim(levels, reference, max_spread_cents):
    """Niveles dentro del max_spread + colchon, redondeados. Lista compacta
    [[precio, tamano]] lista para JSON."""
    if reference is None:
        return []
    limit = (max_spread_cents + LEVEL_MARGIN_CENTS) / 100.0
    out = []
    for p, s in rewards._levels(levels):
        if abs(p - reference) <= limit:
            out.append([round(p, 4), round(s, 2)])
    out.sort(key=lambda x: x[0])
    return out


def _qualifying_depth(levels, reference, max_spread_cents, min_size):
    """(shares, usd) que califican: tamano >= min_size y dentro del max spread."""
    if reference is None:
        return 0.0, 0.0
    limit = max_spread_cents / 100.0
    shares = usd = 0.0
    for p, s in rewards._levels(levels):
        if s >= min_size and abs(p - reference) < limit:
            shares += s
            usd += s * p
    return shares, usd


def snapshot(markets, books, ts=None) -> list:
    """Convierte mercados + libros en registros listos para escribir. Puro."""
    ts = ts or datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = []
    for m in markets:
        yb = books.get(m["yes_token_id"])
        nb = books.get(m["no_token_id"])
        if yb is None or nb is None:
            continue
        yes_bids, yes_asks = _side(yb, "bids"), _side(yb, "asks")
        no_bids, no_asks = _side(nb, "bids"), _side(nb, "asks")

        v = m["max_spread"]
        ms = m["min_size"]
        mid = rewards.adjusted_midpoint(yes_bids, yes_asks, ms)
        q_one, q_two = rewards.side_scores(yes_bids, yes_asks, no_bids, no_asks, mid, v, ms)
        book_q = rewards.q_min(q_one, q_two, mid)

        d_shares, d_usd = _qualifying_depth(yes_bids, mid, v, ms)
        d2_shares, d2_usd = _qualifying_depth(no_bids, None if mid is None else 1.0 - mid, v, ms)

        ba_y = rewards.best_ask(yes_asks)
        ba_n = rewards.best_ask(no_asks)
        bb_y = rewards.best_bid(yes_bids)
        bb_n = rewards.best_bid(no_bids)

        records.append({
            "ts":           ts,
            "condition_id": m["condition_id"],
            "slug":         m["slug"],
            "daily_pool":   m["daily_pool"],
            "min_size":     ms,
            "max_spread":   v,
            "mid":          None if mid is None else round(mid, 5),
            "q_one":        round(q_one, 3),
            "q_two":        round(q_two, 3),
            "book_q_min":   round(book_q, 3),
            "qual_bid_shares": round(d_shares + d2_shares, 2),
            "qual_bid_usd":    round(d_usd + d2_usd, 2),
            # vigilante de arb (coste ~cero, por si algun dia se descuadra)
            "ask_sum":    None if (ba_y is None or ba_n is None) else round(ba_y + ba_n, 4),
            "bid_sum":    None if (bb_y is None or bb_n is None) else round(bb_y + bb_n, 4),
            "yes_bids":   _trim(yes_bids, mid, v),
            "yes_asks":   _trim(yes_asks, mid, v),
            "no_bids":    _trim(no_bids, None if mid is None else 1.0 - mid, v),
            "no_asks":    _trim(no_asks, None if mid is None else 1.0 - mid, v),
        })
    return records


# ============================================================
# LAZO
# ============================================================
def run(minutes: float = 20.0, interval: float = 60.0, top_n: int = 40,
        min_daily: float = 1.0, out_path: str = None, client=None) -> str:
    """Muestrea cada `interval` segundos durante `minutes` y escribe JSONL.
    Devuelve la ruta del archivo. Una muestra que falla no corta la corrida."""
    client = client or make_client()
    markets = select_markets(client, top_n=top_n, min_daily=min_daily)
    if not markets:
        log.error("ningun mercado elegible (top=%d, min_daily=%s)", top_n, min_daily)
        return ""
    log.info("mercados seleccionados: %d | pool diario total $%.0f",
             len(markets), sum(m["daily_pool"] for m in markets))

    if not out_path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join("pm_data", f"probe_{stamp}.jsonl.gz")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    opener = (lambda p: gzip.open(p, "at", encoding="utf-8")) if out_path.endswith(".gz") \
        else (lambda p: open(p, "a", encoding="utf-8"))

    tokens = [t for m in markets for t in (m["yes_token_id"], m["no_token_id"])]
    deadline = time.time() + minutes * 60.0
    n_samples = n_records = 0

    with opener(out_path) as fh:
        # Cabecera: la config de los mercados de esta corrida, una sola vez.
        fh.write(json.dumps({"_meta": "markets", "markets": markets,
                             "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                            ensure_ascii=False) + "\n")
        while True:
            t0 = time.time()
            try:
                recs = snapshot(markets, fetch_books(client, tokens))
                for r in recs:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                fh.flush()
                n_samples += 1
                n_records += len(recs)
                log.info("muestra %d: %d mercados", n_samples, len(recs))
            except Exception as exc:                  # noqa: BLE001 - no cortar 7 dias por un 502
                log.warning("muestra fallida: %s", exc)
            if time.time() >= deadline:
                break
            time.sleep(max(0.0, interval - (time.time() - t0)))

    log.info("listo: %s | %d muestras, %d registros", out_path, n_samples, n_records)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fase 0: recolector read-only de Polymarket")
    ap.add_argument("--minutes", type=float, default=20.0, help="duracion de la corrida")
    ap.add_argument("--interval", type=float, default=60.0, help="segundos entre muestras")
    ap.add_argument("--top", type=int, default=40, help="mercados por pool diario")
    ap.add_argument("--min-daily", type=float, default=1.0, help="pool diario minimo en USDC")
    ap.add_argument("--out", default=None, help="ruta del JSONL")
    ap.add_argument("--once", action="store_true", help="una sola muestra y salir")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    path = run(minutes=0.0 if args.once else args.minutes, interval=args.interval,
               top_n=args.top, min_daily=args.min_daily, out_path=args.out)
    return 0 if path else 1


if __name__ == "__main__":
    raise SystemExit(main())
