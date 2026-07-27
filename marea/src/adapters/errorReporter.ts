import type { AppError } from "@/domain/types";
import { FLAGS } from "@/lib/flags";

/**
 * Puerto de reporte de errores. Igual que la analítica: si el reporter falla,
 * el usuario no se entera y la UX sigue (R-009).
 */
export interface ErrorReporter {
  report(error: AppError): void;
}

export function createMemoryErrorReporter(sink: AppError[] = []): ErrorReporter & {
  errors: AppError[];
} {
  return {
    errors: sink,
    report(error) {
      try {
        if (!FLAGS.error_reporting) return;
        sink.push(error);
      } catch {
        /* nunca escala a la vista (R-009) */
      }
    },
  };
}

export function safeErrorReporter(inner: ErrorReporter): ErrorReporter {
  return {
    report(error) {
      try {
        inner.report(error);
      } catch {
        /* silencio deliberado (R-009) */
      }
    },
  };
}

export const errorReporter = createMemoryErrorReporter();
