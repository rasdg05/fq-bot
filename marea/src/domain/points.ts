/**
 * Puntos. La Fase 1 del producto se juega con puntos, no con dinero: valida el
 * apetito y la UX sin tocar custodia ni regulación
 * (`marca/vision_apuestas_wallet.md` §6).
 *
 * La honestidad aquí es el producto: los puntos **no se cambian por dinero**,
 * y eso está en el código, no sólo en el copy (R-026). Si algún día se pueden
 * canjear, deja de ser paper betting y vuelve a abrir todo `COMPLIANCE.md`.
 */

export const WELCOME_GRANT = 1_000;
export const DAILY_GRANT = 100;

export type PointsReason =
  | "bienvenida"
  | "recarga_diaria"
  | "apuesta"
  | "liquidacion"
  | "devolucion";

export interface PointsEntry {
  id: string;
  /** Positivo suma, negativo resta. */
  amount: number;
  reason: PointsReason;
  at: string;
  marketId?: string;
}

export interface PointsLedger {
  balance: number;
  entries: PointsEntry[];
}

export function emptyLedger(): PointsLedger {
  return { balance: 0, entries: [] };
}

export function grantWelcome(ledger: PointsLedger, at = new Date().toISOString()): PointsLedger {
  // la bienvenida se entrega una sola vez: no es una llave para farmear puntos
  if (ledger.entries.some((entry) => entry.reason === "bienvenida")) return ledger;
  return apply(ledger, {
    id: `w-${at}`,
    amount: WELCOME_GRANT,
    reason: "bienvenida",
    at,
  });
}

export function apply(ledger: PointsLedger, entry: PointsEntry): PointsLedger {
  const balance = ledger.balance + entry.amount;
  if (balance < 0) {
    // sin crédito, nunca. Es la promesa de juego responsable de la marca
    throw new Error("saldo insuficiente: los puntos no se prestan");
  }
  return { balance, entries: [entry, ...ledger.entries] };
}

export function canStake(ledger: PointsLedger, amount: number): boolean {
  return amount > 0 && ledger.balance >= amount;
}

/**
 * Invariante de la Fase 1. Existe como función y no como comentario para que
 * cualquier intento de canje tenga que borrar código, no sólo cambiar copy.
 */
export function canCashOut(): false {
  return false;
}

/** Cuánto se puede recargar hoy sin que el juego pierda sentido. */
export function dailyTopUp(
  ledger: PointsLedger,
  now = new Date(),
): number {
  const today = now.toISOString().slice(0, 10);
  const claimed = ledger.entries.some(
    (entry) => entry.reason === "recarga_diaria" && entry.at.slice(0, 10) === today,
  );
  if (claimed) return 0;
  // la recarga es para quien se quedó sin puntos, no un ingreso pasivo
  return ledger.balance < DAILY_GRANT ? DAILY_GRANT - ledger.balance : 0;
}
