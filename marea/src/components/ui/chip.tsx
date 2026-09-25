import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

export interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
  /**
   * Color de la raya cuando esta pestaña manda, como `var(--cat-…)`. Sin él la
   * raya es teal, que es lo que le toca a "Todas": no es una categoría, es su
   * ausencia. Nunca es el portador del estado — ver abajo.
   */
  color?: string;
  /** Glifo de la categoría, en su color. */
  icon?: LucideIcon;
}

/**
 * Pestaña de categoría.
 *
 * Volvió a ser pastilla, ahora con color: la que manda se rellena con el color
 * de su categoría (lavado, con el texto en `--text`) y las demás van en gris
 * sobre `--panel2`. Con veinte ligas y cinco monedas el feed tiene de qué
 * presumir, y una fila de palabras grises no invitaba a tocar ninguna.
 *
 * El estado activo no depende sólo del color —cambia el peso y el relleno
 * (R-005)— y el target sigue midiendo 44 px de alto: la pastilla visible es de
 * 34 y el aire de alrededor es parte del botón (R-010).
 */
export const Chip = React.forwardRef<HTMLButtonElement, ChipProps>(
  ({ className, active, color, icon: Icono, children, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={active}
      data-active={active || undefined}
      className={cn(
        "group relative flex min-h-touch shrink-0 items-center whitespace-nowrap text-[14px] tracking-[-0.01em]",
        active ? "font-bold text-text" : "font-medium text-text2",
        className,
      )}
      /* el color viaja como custom property: la pastilla lo consume para el
         relleno y el borde. Quien no distinga los tonos ve igual cuál manda,
         por el peso y porque sólo ella tiene relleno de color */
      style={
        active
          ? ({ "--chip-raya": color ?? "var(--teal)" } as React.CSSProperties)
          : undefined
      }
      {...props}
    >
      <span
        className={cn(
          "flex h-[34px] items-center gap-1.5 rounded-pill px-3.5 transition-colors",
          active
            ? "bg-[color:color-mix(in_srgb,var(--chip-raya)_22%,var(--panel))] ring-1 ring-[color:color-mix(in_srgb,var(--chip-raya)_55%,transparent)]"
            : "bg-panel2 group-hover:text-text",
        )}
      >
        {Icono ? (
          <Icono
            aria-hidden
            className="h-3.5 w-3.5"
            strokeWidth={2.4}
            style={{ color: color ?? "var(--teal)" }}
          />
        ) : null}
        {children}
      </span>
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
