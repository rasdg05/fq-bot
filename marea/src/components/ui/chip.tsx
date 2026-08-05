import * as React from "react";
import { cn } from "@/lib/cn";

export interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  /**
   * Color de la raya cuando esta pestaña manda, como `var(--cat-…)`. Sin él la
   * raya es teal, que es lo que le toca a "Todas": no es una categoría, es su
   * ausencia. Nunca es el portador del estado — ver abajo.
   */
  color?: string;
}

/**
 * Pestaña de categoría.
 *
 * Dejó de ser una burbuja. Ocho cápsulas con borde en fila son ocho marcos
 * compitiendo por atención antes de que se lea una sola palabra, y el feed
 * empieza con la vista ya cansada. Ahora es texto: la que manda va en blanco y
 * peso fuerte con una raya de 2 px debajo, las demás en gris.
 *
 * El estado activo no depende sólo del color —cambia peso **y** lleva la raya
 * (R-005)— y el target sigue midiendo 44 px de alto.
 */
export const Chip = React.forwardRef<HTMLButtonElement, ChipProps>(
  ({ className, active, color, children, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={active}
      data-active={active || undefined}
      className={cn(
        "relative min-h-touch shrink-0 whitespace-nowrap px-1 text-[17px] transition-colors",
        "after:absolute after:inset-x-1 after:bottom-1.5 after:h-[2px] after:rounded-pill",
        // un `::after` no se puede pintar desde `style`, así que el color viaja
        // como custom property y la clase la consume
        active
          ? "font-bold text-text after:bg-[color:var(--chip-raya)]"
          : "font-semibold text-muted after:bg-transparent",
        className,
      )}
      /* La raya toma el color de la categoría, pero el color no anuncia nada
         por su cuenta: la pestaña que manda ya cambia de peso y de color de
         texto, y la raya está o no está (R-005). Quien no distinga los tonos
         sigue viendo exactamente lo mismo que antes. */
      style={
        active
          ? ({ "--chip-raya": color ?? "var(--teal)" } as React.CSSProperties)
          : undefined
      }
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
          "flex gap-5 overflow-x-auto px-4 pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
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
