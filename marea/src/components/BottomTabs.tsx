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
 * El fondo es sólido a propósito: un color declarado como `var(--token)` no
 * admite modificador de opacidad en Tailwind: la declaración se descarta, no
 * se pinta fondo y la barra queda transparente sobre el contenido (R-017).
 */
export function BottomTabs() {
  const { state, actions } = useApp();

  return (
    <nav
      aria-label={S.tabs.navegacion}
      data-testid="bottom-tabs"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-line2 bg-bg"
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
                  "flex min-h-touch w-full flex-col items-center justify-center gap-0.5 py-2",
                  active ? "text-teal" : "text-muted",
                )}
              >
                <Icon
                  aria-hidden
                  className="h-[22px] w-[22px]"
                  strokeWidth={active ? 2.4 : 1.8}
                />
                {/* el estado activo también cambia el peso: no depende del color (R-005) */}
                <span
                  className={cn(
                    "text-[11px]",
                    active ? "font-bold" : "font-medium",
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
