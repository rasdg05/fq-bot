/** Formateo consistente. La probabilidad siempre se lee como entero de 0 a 100. */
export function pct(probability: number): string {
  return String(Math.round(probability * 100));
}

export function usd(amount: number): string {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "USD",
    currencyDisplay: "narrowSymbol",
    maximumFractionDigits: amount % 1 === 0 ? 0 : 2,
  }).format(amount);
}

export function compactUsd(amount: number): string {
  // es-MX pone el símbolo después en notación compacta ("184.3 k$"): lo armamos
  // a mano para que se lea como precio y no como unidad
  const compact = new Intl.NumberFormat("es-MX", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(amount);
  return `$${compact.replace(/\s/g, "")}`;
}

export function shortAddress(address: string): string {
  if (address.length <= 12) return address;
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}

export function closesIn(iso?: string, now: number = Date.now()): string | null {
  if (!iso) return null;
  const delta = new Date(iso).getTime() - now;
  if (Number.isNaN(delta)) return null;
  // el llamador antepone "Cierra": aquí sólo va el plazo, nunca el estado
  if (delta <= 0) return null;
  const hours = Math.floor(delta / 3_600_000);
  if (hours < 1) return `en ${Math.max(1, Math.floor(delta / 60_000))} min`;
  if (hours < 24) return `en ${hours} h`;
  return `en ${Math.floor(hours / 24)} d`;
}

/**
 * `12 de agosto`. La fecha de cierre en palabras, sin año cuando es este año:
 * el año sobra en un mercado que cierra en semanas y ocupa sitio en una línea
 * que ya va apretada.
 */
export function fechaCorta(iso?: string, ahora = new Date()): string | null {
  if (!iso) return null;
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return null;
  const mismoAnio = fecha.getUTCFullYear() === ahora.getUTCFullYear();
  return new Intl.DateTimeFormat("es-MX", {
    day: "numeric",
    month: "long",
    ...(mismoAnio ? {} : { year: "numeric" }),
    timeZone: "UTC",
  }).format(fecha);
}
