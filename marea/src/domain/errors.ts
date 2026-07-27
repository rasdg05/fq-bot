import type { AppError, AppErrorCode } from "./types";

/**
 * Catálogo de errores. Todo error que llega a la UI pasa por aquí, así que
 * nunca hay un mensaje sin traducir ni un stack trace visible (R-008).
 */
const CATALOG: Record<AppErrorCode, { message: string; retryable: boolean }> = {
  E_WALLET_CREATE_FAILED: {
    message: "No pudimos crear tu wallet. Intenta de nuevo en un momento.",
    retryable: true,
  },
  E_WALLET_CONNECT_FAILED: {
    message: "No pudimos conectar tu wallet. Revisa la app de tu wallet e intenta otra vez.",
    retryable: true,
  },
  E_BALANCE_FETCH_FAILED: {
    message: "No pudimos leer tu saldo ahora mismo. Puedes seguir explorando mercados.",
    retryable: true,
  },
  E_DEPOSIT_INIT_FAILED: {
    message: "No pudimos iniciar el depósito. Intenta de nuevo.",
    retryable: true,
  },
  E_DEPOSIT_PROVIDER_UNAVAILABLE: {
    message:
      "El proveedor de tarjeta está fuera de servicio en este momento. Puedes depositar cripto por transferencia mientras tanto.",
    retryable: false,
  },
  E_MARKETS_FETCH_FAILED: {
    message: "No pudimos cargar los mercados. Revisa tu conexión.",
    retryable: true,
  },
  E_MARKET_DETAIL_FAILED: {
    message: "No pudimos abrir este mercado. Intenta de nuevo.",
    retryable: true,
  },
  E_PORTFOLIO_FETCH_FAILED: {
    message: "No pudimos cargar tu portafolio. Intenta de nuevo.",
    retryable: true,
  },
  E_TRADE_INIT_FAILED: {
    message: "No pudimos preparar tu operación. Tu saldo no se movió.",
    retryable: true,
  },
  E_NETWORK: {
    message: "Se cayó la conexión. Revisa tu internet e intenta otra vez.",
    retryable: true,
  },
  E_UNKNOWN: {
    message: "Algo salió mal de nuestro lado. Intenta de nuevo en un momento.",
    retryable: true,
  },
};

export function appError(
  code: AppErrorCode,
  context?: Record<string, unknown>,
): AppError {
  const entry = CATALOG[code] ?? CATALOG.E_UNKNOWN;
  return {
    code,
    user_message_es: entry.message,
    retryable: entry.retryable,
    context,
  };
}

export function isAppError(value: unknown): value is AppError {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    "user_message_es" in value
  );
}

/** Normaliza cualquier excepción a AppError: nada crudo llega a la vista. */
export function toAppError(value: unknown, fallback: AppErrorCode = "E_UNKNOWN"): AppError {
  if (isAppError(value)) return value;
  return appError(fallback, { cause: value instanceof Error ? value.message : String(value) });
}

export const ERROR_CODES = Object.keys(CATALOG) as AppErrorCode[];
