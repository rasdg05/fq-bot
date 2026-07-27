/**
 * Recolector diario de la superficie de volatilidad implícita.
 *
 * La historia de la superficie por vencimiento **no existe** en ningún endpoint
 * público: sólo se puede ver el estado de hoy. Así que empezamos a guardarla
 * hoy. Cada día que no corre es un dato que no se recupera (R-037).
 *
 * Guarda un archivo por día en `data/iv/`, chico y append-only:
 * para cada moneda y cada vencimiento, la volatilidad en el dinero y la sonrisa
 * a ±10 %. Con eso se puede, más adelante, usar la volatilidad del plazo que
 * corresponde a cada pregunta en vez de un índice a 30 días.
 *
 *   npm run collect:iv
 */
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const CURRENCIES = ["BTC", "ETH"];
const OUT_DIR = join("data", "iv");

interface ChainRow {
  instrument_name: string;
  mark_iv?: number;
  underlying_price?: number;
  open_interest?: number;
}

interface ExpirySnapshot {
  /** Ticker del vencimiento tal como lo publica el venue, p. ej. `28AUG26`. */
  expiry: string;
  /** Días naturales hasta el vencimiento. */
  dias: number;
  /** Volatilidad implícita en el dinero, en tanto por uno. */
  atm: number;
  /** Volatilidad 10 % abajo del precio: la parte cara de la sonrisa. */
  abajo10: number | null;
  /** Volatilidad 10 % arriba del precio. */
  arriba10: number | null;
  /** Contratos abiertos: dice cuánto peso tiene ese vencimiento. */
  interesAbierto: number;
  /** Cuántos instrumentos sostienen el punto. */
  n: number;
}

interface DaySnapshot {
  fecha: string;
  tomadoEn: string;
  fuente: string;
  monedas: Record<
    string,
    { subyacente: number; vencimientos: ExpirySnapshot[] } | { error: string }
  >;
}

/** `28AUG26` → fecha. Deribit vence a las 08:00 UTC. */
function parseExpiry(ticker: string): Date | null {
  const match = ticker.match(/^(\d{1,2})([A-Z]{3})(\d{2})$/);
  if (!match) return null;
  const months = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(" ");
  const month = months.indexOf(match[2]);
  if (month < 0) return null;
  return new Date(
    Date.UTC(2000 + Number(match[3]), month, Number(match[1]), 8, 0, 0),
  );
}

/**
 * Volatilidad a una distancia dada del precio, interpolando entre los dos
 * strikes vecinos. Sin interpolar, el punto salta según qué strikes existan.
 */
function ivAtMoneyness(
  points: { strike: number; iv: number }[],
  target: number,
): number | null {
  if (points.length === 0) return null;
  const sorted = [...points].sort((a, b) => a.strike - b.strike);
  if (target <= sorted[0].strike) return sorted[0].iv;
  if (target >= sorted[sorted.length - 1].strike) return sorted[sorted.length - 1].iv;

  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i].strike >= target) {
      const low = sorted[i - 1];
      const high = sorted[i];
      const span = high.strike - low.strike;
      if (span <= 0) return low.iv;
      const weight = (target - low.strike) / span;
      return low.iv + weight * (high.iv - low.iv);
    }
  }
  return null;
}

async function snapshot(currency: string) {
  const response = await fetch(
    `https://www.deribit.com/api/v2/public/get_book_summary_by_currency` +
      `?currency=${currency}&kind=option`,
  );
  const payload = (await response.json()) as { result?: ChainRow[] };
  const rows = payload.result ?? [];
  if (rows.length === 0) throw new Error(`sin cadena de opciones para ${currency}`);

  const underlying = rows.find((row) => row.underlying_price)?.underlying_price;
  if (!underlying) throw new Error(`sin precio del subyacente para ${currency}`);

  // agrupamos por vencimiento; call y put del mismo strike promedian
  const byExpiry = new Map<string, { strike: number; iv: number; oi: number }[]>();
  for (const row of rows) {
    const [, expiry, strikeText] = row.instrument_name.split("-");
    const strike = Number(strikeText);
    const iv = row.mark_iv;
    // sin volatilidad cotizada el punto no existe: no se rellena con nada
    if (!expiry || !Number.isFinite(strike) || !iv || iv <= 0) continue;
    const list = byExpiry.get(expiry) ?? [];
    list.push({ strike, iv: iv / 100, oi: row.open_interest ?? 0 });
    byExpiry.set(expiry, list);
  }

  const now = Date.now();
  const vencimientos: ExpirySnapshot[] = [];
  for (const [expiry, points] of byExpiry) {
    const when = parseExpiry(expiry);
    if (!when) continue;
    const dias = Math.round((when.getTime() - now) / 86_400_000);
    if (dias < 0) continue;

    // promedio de call y put por strike, que deben coincidir por paridad
    const porStrike = new Map<number, number[]>();
    for (const point of points) {
      porStrike.set(point.strike, [...(porStrike.get(point.strike) ?? []), point.iv]);
    }
    const curva = [...porStrike.entries()].map(([strike, ivs]) => ({
      strike,
      iv: ivs.reduce((sum, value) => sum + value, 0) / ivs.length,
    }));
    const atm = ivAtMoneyness(curva, underlying);
    if (atm === null) continue;

    vencimientos.push({
      expiry,
      dias,
      atm: Math.round(atm * 10_000) / 10_000,
      abajo10: round4(ivAtMoneyness(curva, underlying * 0.9)),
      arriba10: round4(ivAtMoneyness(curva, underlying * 1.1)),
      interesAbierto: Math.round(points.reduce((sum, p) => sum + p.oi, 0)),
      n: curva.length,
    });
  }

  vencimientos.sort((a, b) => a.dias - b.dias);
  return { subyacente: Math.round(underlying * 100) / 100, vencimientos };
}

const round4 = (value: number | null) =>
  value === null ? null : Math.round(value * 10_000) / 10_000;

const fecha = new Date().toISOString().slice(0, 10);
const day: DaySnapshot = {
  fecha,
  tomadoEn: new Date().toISOString(),
  fuente: "Deribit — get_book_summary_by_currency (kind=option), mark_iv",
  monedas: {},
};

for (const currency of CURRENCIES) {
  try {
    day.monedas[currency] = await snapshot(currency);
  } catch (error) {
    // una moneda caída no tira el día entero: se anota y seguimos
    day.monedas[currency] = { error: error instanceof Error ? error.message : String(error) };
  }
}

if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });
const file = join(OUT_DIR, `${fecha}.json`);
writeFileSync(file, `${JSON.stringify(day, null, 1)}\n`);

console.log(`superficie guardada en ${file}`);
for (const [currency, data] of Object.entries(day.monedas)) {
  if ("error" in data) {
    console.log(`  ${currency}: ${data.error}`);
    continue;
  }
  const corto = data.vencimientos.slice(0, 5);
  console.log(
    `  ${currency} @ ${data.subyacente}: ` +
      corto.map((v) => `${v.dias}d ${(v.atm * 100).toFixed(1)}%`).join(" · ") +
      (data.vencimientos.length > corto.length
        ? ` · (+${data.vencimientos.length - corto.length} más)`
        : ""),
  );
}
