import type { AppError } from "@/domain/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { S } from "@/lib/strings";
import { AlertTriangle } from "lucide-react";

/**
 * Los cuatro estados de un listado viven aquí, para que ninguna pantalla
 * invente el suyo y todas se vean igual (R-006).
 */

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={S.feed.loading}
      data-testid="list-skeleton"
      // el mismo espaciado que el feed real: si el hueco entre esqueletos no
      // es el hueco entre cards, la página salta aunque cada pieza mida bien
      className="space-y-2 px-4"
    >
      {Array.from({ length: rows }).map((_, index) => (
        // altura idéntica a la card real (vault/CARD_SPEC.md). Un esqueleto que
        // no mide igual es un salto de layout disfrazado, así que este número
        // baja cada vez que la card adelgaza: 148 → 159 → 143.
        // `npm run densidad` lo verifica en el navegador y falla si se olvida
        <Skeleton key={index} className="h-[143px] w-full rounded-card" />
      ))}
      <span className="sr-only">{S.feed.loading}</span>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  ctaLabel,
  onCta,
  testId = "empty-state",
}: {
  title: string;
  body?: string;
  ctaLabel?: string;
  onCta?: () => void;
  testId?: string;
}) {
  return (
    <div
      data-testid={testId}
      className="mx-4 rounded-card border border-dashed border-line px-5 py-10 text-center"
    >
      <p className="font-display text-[19px] leading-snug text-text">{title}</p>
      {body ? <p className="mt-2 text-[14px] text-text2">{body}</p> : null}
      {ctaLabel && onCta ? (
        <Button className="mt-5" variant="secondary" onClick={onCta}>
          {ctaLabel}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Error dentro de un listado: mensaje en español y `Reintentar` sólo si el
 * error es reintentable (R-008). El código técnico nunca es el mensaje.
 */
export function ErrorState({
  error,
  onRetry,
  testId = "error-state",
}: {
  error: AppError;
  onRetry?: () => void;
  testId?: string;
}) {
  return (
    <div
      role="alert"
      data-testid={testId}
      data-error-code={error.code}
      className="mx-4 rounded-card border border-line bg-panel2 px-5 py-8 text-center"
    >
      <AlertTriangle
        aria-hidden
        className="mx-auto mb-3 h-6 w-6 text-[color:var(--dn)]"
      />
      <p className="text-[15px] leading-relaxed text-text">
        {error.user_message_es}
      </p>
      {error.retryable && onRetry ? (
        <Button className="mt-5" variant="secondary" onClick={onRetry}>
          {S.common.retry}
        </Button>
      ) : null}
    </div>
  );
}
