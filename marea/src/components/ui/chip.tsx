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
 * Rediseño 2026-10-01 (RasDG: «los menús se ven mal»). Antes todas las
 * pestañas eran pastillas rellenas y la activa sólo sumaba un anillo de color:
 * la fila entera pesaba igual y nada mandaba. Ahora, el patrón de las
 * interfaces de mercado serias:
 *
 *  - **Inactivas sin relleno**: texto en `--text2`, que se aclara al pasar.
 *  - **La activa, invertida**: pastilla en `--text` con el texto en `--bg`.
 *    Es el máximo contraste disponible en los dos temas, y se reconoce sin
 *    distinguir ningún color (R-005): cambian relleno, tono y peso a la vez.
 *  - El glifo conserva su color de categoría: es el único acento de la fila.
 *
 * Radio de 10 px y no píldora entera: a 32 px de alto la píldora se ve como
 * botón de juguete. El target sigue midiendo 44 px: la pastilla visible es de
 * 32 y el aire de alrededor es parte del botón (R-010).
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
          ? ({ "--chip-acento": color ?? "var(--teal)" } as React.CSSProperties)
          : undefined
      }
      {...props}
    >
      <span
        className={cn(
          "flex h-8 items-center gap-1.5 rounded-[10px] px-3 transition-[background-color,color] duration-150",
          active ? "bg-text text-bg" : "group-hover:bg-panel2 group-hover:text-text",
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

  /**
   * La pestaña activa siempre queda a la vista y fuera del degradado: si es la
   * última que asoma, el degradado de «hay más» la tapaba a medias justo
   * cuando acababa de elegirse. Se desplaza la fila, nunca la página.
   */
  React.useEffect(() => {
    const el = ref.current;
    const activa = el?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!el || !activa) return;
    const MARGEN = 56; // el ancho del degradado (`w-14`)
    const izquierda = activa.offsetLeft - el.offsetLeft;
    const derecha = izquierda + activa.offsetWidth;
    if (derecha > el.scrollLeft + el.clientWidth - MARGEN) {
      el.scrollLeft = derecha - el.clientWidth + MARGEN;
    } else if (izquierda < el.scrollLeft) {
      el.scrollLeft = Math.max(0, izquierda - 16);
    }
    revisar();
  }, [children, revisar]);

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
