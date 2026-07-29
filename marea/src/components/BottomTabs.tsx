import { LayoutGrid, Search, PieChart, Trophy, Wallet, User } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { S } from "@/lib/strings";
import { useApp, type TabId } from "@/state/store";
import { isPointsMode } from "@/lib/flags";

/**
 * En modo puntos la cartera no existe —no hay dinero que guardar— y su lugar lo
 * toma la tabla, que es lo que hace que la gente vuelva mañana a defender su
 * racha. Con dinero real vuelve la cartera.
 */
function tabsDe(puntos: boolean): { id: TabId; label: string; Icon: LucideIcon }[] {
  return [
    { id: "markets", label: S.tabs.markets, Icon: LayoutGrid },
    { id: "search", label: S.tabs.search, Icon: Search },
    { id: "portfolio", label: S.tabs.portfolio, Icon: PieChart },
    puntos
      ? { id: "tabla" as TabId, label: S.tabla.title, Icon: Trophy }
      : { id: "wallet" as TabId, label: S.tabs.wallet, Icon: Wallet },
    { id: "profile", label: S.tabs.profile, Icon: User },
  ];
}

/**
 * Navegación inferior: 5 destinos, `Mercados` por defecto. Vive abajo porque
 * es donde llega el pulgar; ninguna acción crítica queda en una esquina
 * superior (R-010). Cada target mide 44 px de alto como mínimo.
 *
 * El fondo es sólido a propósito: un color declarado como `var(--token)` no
 * admite modificador de opacidad en Tailwind: la declaración se descarta, no
 * se pinta fondo y la barra queda transparente sobre el contenido (R-017).
 */
export function BottomTabs() {
  const { state, actions } = useApp();
  const TABS = tabsDe(isPointsMode());

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

/** Los destinos vigentes según el motor. Lo usan las pruebas de navegación. */
export const tabIds = (puntos: boolean): TabId[] => tabsDe(puntos).map((tab) => tab.id);
