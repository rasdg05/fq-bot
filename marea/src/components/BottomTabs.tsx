import { LayoutGrid, Search, PieChart, User } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { S } from "@/lib/strings";
import { useApp, type TabId } from "@/state/store";

/**
 * Exactamente cuatro destinos, siempre los mismos.
 *
 * La tabla y la cartera salieron de la barra: no son destinos de navegación,
 * son cosas que se consultan. Viven dentro de Perfil, que es donde uno va a
 * ver lo suyo. Cuatro pestañas dejan cada target en 97 px de ancho a 390 px,
 * y sobre todo dejan de convertir la barra en un menú.
 */
const TABS: { id: TabId; label: string; Icon: LucideIcon }[] = [
  { id: "markets", label: S.tabs.markets, Icon: LayoutGrid },
  { id: "search", label: S.tabs.search, Icon: Search },
  { id: "portfolio", label: S.tabs.portfolio, Icon: PieChart },
  { id: "profile", label: S.tabs.profile, Icon: User },
];

/**
 * Navegación inferior: 4 destinos, `Mercados` por defecto. Vive abajo porque
 * es donde llega el pulgar; ninguna acción crítica queda en una esquina
 * superior (R-010). Cada target mide 44 px de alto como mínimo.
 *
 * El fondo es esmerilado: `color-mix` sobre `--bg` más `backdrop-blur`. No se
 * usa el modificador de opacidad de Tailwind, porque sobre un color declarado
 * como `var(--token)` la declaración se descarta y la barra queda transparente
 * sobre el contenido (R-017); `color-mix` sí se pinta.
 */
export function BottomTabs() {
  const { state, actions } = useApp();
  // cuántos mercados están corriendo ahora mismo. Va sobre Mercados y no como
  // quinto destino: la barra son cuatro y eso no se toca — lo que hace falta
  // saber es que hay algo pasando, no un sitio nuevo al que ir
  const vivos =
    state.markets.status === "data"
      ? state.markets.data.filter((m) => m.status === "live").length
      : 0;

  return (
    <nav
      aria-label={S.tabs.navegacion}
      data-testid="bottom-tabs"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-line2 bg-[color:color-mix(in_srgb,var(--bg)_82%,transparent)] backdrop-blur-xl backdrop-saturate-150"
      style={{ paddingBottom: "var(--safe-b)" }}
    >
      {/* un `role="tab"` sin `tablist` que lo contenga deja al lector de
          pantalla sin saber cuántas pestañas hay ni en cuál está. Era el único
          hallazgo crítico de axe, y salía en las cinco pantallas.
          `role="presentation"` en los `li` porque una lista dentro de un
          tablist tampoco es una estructura válida */}
      <ul
        role="tablist"
        aria-label={S.tabs.navegacion}
        className="mx-auto flex w-full max-w-[520px] items-stretch"
      >
        {TABS.map(({ id, label, Icon }) => {
          const active = state.tab === id;
          return (
            <li key={id} role="presentation" className="flex-1">
              <button
                type="button"
                role="tab"
                aria-selected={active}
                aria-current={active ? "page" : undefined}
                data-tab={id}
                onClick={() => actions.setTab(id)}
                className={cn(
                  "flex min-h-touch w-full flex-col items-center justify-center gap-1 pb-1.5 pt-2 transition-colors",
                  active ? "text-text" : "text-muted hover:text-text2",
                )}
              >
                <span className="relative">
                  <Icon
                    aria-hidden
                    className="h-[21px] w-[21px]"
                    strokeWidth={active ? 2.1 : 1.6}
                  />
                  {id === "markets" && vivos > 0 ? (
                    <span
                      // el número no entra en el nombre accesible de la pestaña:
                      // "4 Mercados" no es un destino. Quien no ve la insignia se
                      // entera igual — cada card viva se anuncia con su badge LIVE
                      aria-hidden
                      data-testid="tab-vivos"
                      className="absolute -right-2.5 -top-1 rounded-pill bg-live px-1 font-mono text-[10px] font-bold leading-[14px] text-bg"
                    >
                      {vivos}
                    </span>
                  ) : null}
                </span>
                {/* el estado activo también cambia el peso: no depende del color (R-005) */}
                <span
                  className={cn(
                    "text-[11px] tracking-[-0.005em]",
                    active ? "font-semibold" : "font-medium",
                  )}
                >
                  {label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Los destinos de la barra. Lo usan las pruebas de navegación. */
export const tabIds = (): TabId[] => TABS.map((tab) => tab.id);
