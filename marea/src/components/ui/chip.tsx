import * as React from "react";
import { cn } from "@/lib/cn";

export interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
}

/**
 * Chip de categoría. 44 px de alto y 8 px de separación en la fila (R-010);
 * el estado activo no depende solo del color: cambia peso y borde.
 */
export const Chip = React.forwardRef<HTMLButtonElement, ChipProps>(
  ({ className, active, children, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={active}
      data-active={active || undefined}
      className={cn(
        "min-h-touch shrink-0 whitespace-nowrap rounded-pill border px-4 text-[14px] transition-colors",
        // el activo va con relleno sólido, no con un tinte: una fila de chips
        // donde el elegido apenas se distingue obliga a leerlos todos para
        // saber qué filtro está puesto. El peso cambia además del color (R-005)
        active
          ? "border-teal bg-teal font-bold text-teal-ink"
          : "border-line2 bg-panel font-medium text-text2 hover:border-line",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  ),
);
Chip.displayName = "Chip";

export function ChipRow({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [hayMas, setHayMas] = React.useState(false);

  // sin esto la fila se corta a la derecha y nada lo insinúa: a simple vista
  // Marea tendría cuatro categorías. El degradado sólo aparece si de verdad
  // queda algo por ver, para no prometer contenido que no existe
  const revisar = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setHayMas(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  }, []);

  React.useEffect(() => {
    revisar();
    const el = ref.current;
    if (!el) return;
    // `ResizeObserver` no existe en todos los entornos. Un adorno que insinúa
    // scroll no puede tumbar el feed si falta: degrada a no pintar el
    // degradado, que es exactamente lo que pasaba antes (R-009)
    const Observador = globalThis.ResizeObserver;
    const observador = Observador ? new Observador(revisar) : undefined;
    observador?.observe(el);
    globalThis.addEventListener?.("resize", revisar);
    return () => {
      observador?.disconnect();
      globalThis.removeEventListener?.("resize", revisar);
    };
  }, [revisar, children]);

  return (
    <div className={cn("relative", className)}>
      <div
        ref={ref}
        role="tablist"
        onScroll={revisar}
        className={cn(
          // scroll horizontal contenido: la fila desborda, la página nunca (V11)
          "flex gap-2 overflow-x-auto px-4 pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        )}
        {...props}
      >
        {children}
      </div>
      {hayMas ? (
        <div
          aria-hidden
          data-testid="chip-row-mas"
          className="pointer-events-none absolute inset-y-0 right-0 w-14 bg-gradient-to-l from-bg to-transparent"
        />
      ) : null}
    </div>
  );
}
