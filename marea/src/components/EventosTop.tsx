import type { MarketCategory } from "@/domain/types";
import { cn } from "@/lib/cn";
import { COLOR_CATEGORIA, ICONO_CATEGORIA } from "@/lib/categoria";
import { S } from "@/lib/strings";

export interface Hub {
  /** La clave de la sección a la que lleva (`data-seccion`). */
  clave: string;
  titulo: string;
  categoria: MarketCategory;
  mercados: number;
  /** Lo que hay en juego en la sección, ya formateado (`12,400 pts`). */
  enJuego: string;
}

/**
 * «Eventos top»: las secciones más grandes del feed como tarjetas de acceso,
 * el patrón de los hubs de Kalshi («Midterms Hub», «Commodities»).
 *
 * No es otro filtro: tocar un hub **lleva** a su sección. Así no hay un estado
 * más que sincronizar con las pestañas, y volver es simplemente subir.
 *
 * Cada hub es un botón de 44 px de alto como mínimo (R-010), con su color de
 * categoría acompañado de glifo y palabra: el color nunca va solo (R-005).
 */
export function EventosTop({ hubs }: { hubs: Hub[] }) {
  if (hubs.length < 2) return null;

  const ir = (clave: string) => {
    // `CSS.escape` falta en algunos entornos (jsdom, WebViews viejos): las
    // claves son ligas y categorías, así que basta con escapar las comillas
    const escapar = globalThis.CSS?.escape ?? ((t: string) => t.replace(/["\\]/g, "\\$&"));
    const destino = document.querySelector<HTMLElement>(`[data-seccion="${escapar(clave)}"]`);
    if (!destino) return;
    const reducido = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    destino.scrollIntoView({ behavior: reducido ? "auto" : "smooth", block: "start" });
    // el foco viaja con la vista: quien navega con teclado o lector llega al
    // mismo sitio que quien mira
    destino.querySelector<HTMLElement>("h3")?.focus({ preventScroll: true });
  };

  return (
    <section aria-labelledby="eventos-top" className="pt-1">
      <h2
        id="eventos-top"
        className="px-4 pb-2.5 font-display text-[19px] font-semibold text-text"
      >
        {S.feed.eventosTop}
      </h2>
      <div
        data-testid="eventos-top"
        className={cn(
          "flex snap-x gap-2 overflow-x-auto px-4 pb-0.5",
          "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        )}
      >
        {hubs.map((hub) => {
          const color = COLOR_CATEGORIA[hub.categoria];
          const Icono = ICONO_CATEGORIA[hub.categoria];
          return (
            <button
              key={hub.clave}
              type="button"
              data-testid="hub"
              data-hub={hub.clave}
              aria-label={`${S.feed.hubIr(hub.titulo)}, ${S.feed.hubDetalle(hub.mercados, hub.enJuego)}`}
              onClick={() => ir(hub.clave)}
              /* compacto a propósito: 60 px de alto, ícono a la izquierda y dos
                 líneas a la derecha. La versión alta (ícono arriba) costaba
                 ~120 px de feed, que es casi una tarjeta de mercado entera */
              className={cn(
                "flex min-h-touch w-[15rem] shrink-0 snap-start items-center gap-3 rounded-card",
                "border border-line2 bg-panel px-3 py-2.5 text-left",
                "transition-[background-color,transform] duration-[120ms] ease-out",
                "hover:bg-panel2 active:scale-[.98]",
              )}
              /* el lavado de la categoría a la izquierda, como el brillo de los
                 hubs de Kalshi; el color va acompañado de glifo y título */
              style={{
                backgroundImage: `radial-gradient(90% 140% at 0% 50%, color-mix(in srgb, ${color} 16%, transparent), transparent 70%)`,
              }}
            >
              <span
                aria-hidden
                className="grid h-9 w-9 shrink-0 place-items-center rounded-[11px]"
                style={{ backgroundColor: `color-mix(in srgb, ${color} 22%, transparent)` }}
              >
                <Icono className="h-[18px] w-[18px]" style={{ color }} strokeWidth={2.4} />
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate text-[15px] font-semibold leading-tight text-text">
                  {hub.titulo}
                </span>
                {/* lo que hay en juego primero: es la cifra que dice qué tan
                    grande es el evento. La cuenta de mercados va detrás */}
                <span className="truncate font-mono text-[12px] font-medium text-muted">
                  {S.feed.hubCifras(hub.enJuego, hub.mercados)}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
