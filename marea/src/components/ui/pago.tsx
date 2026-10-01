import { cn } from "@/lib/cn";
import { S } from "@/lib/strings";

/**
 * El pago de un lado: `paga 1.94×`.
 *
 * La cifra **nunca** se corta (CARD_SPEC, R-063): un `1.9…` no es un número.
 * Lo que cede es la palabra «paga», que no dice nada que `1.94×` no diga ya —
 * se esconde cuando la tarjeta mide menos de lo que el texto completo pide,
 * con una *container query* sobre la tarjeta (`.cq-card`, en `index.css`), no
 * con un breakpoint de pantalla: la misma tarjeta vive a 358 px en el feed y a
 * 333 en el carrusel, y lo que importa es su ancho, no el del teléfono.
 *
 * Antes eran tres `<span>` copiados con `truncate`, y a 320 px recortaban la
 * cifra entera. El texto accesible no cambia: el lector oye el pago completo
 * en la etiqueta de la pill.
 */
export function Pago({ multiplier, className }: { multiplier: string; className?: string }) {
  return (
    <span
      data-testid="pago"
      className={cn(
        "mt-0.5 whitespace-nowrap font-mono text-mult font-medium tabular-nums text-muted",
        className,
      )}
    >
      <span className="pago-palabra">{S.market.pagaPalabra} </span>
      {multiplier}
    </span>
  );
}
