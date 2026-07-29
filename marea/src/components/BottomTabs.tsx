import { LayoutGrid, Search, PieChart, Radio } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { S } from "@/lib/strings";
import { useApp, type TabId } from "@/state/store";
import { contarVivos } from "@/domain/live";

/**
 * Cuatro destinos, no cinco.
 *
 * `Perfil` subió al header: es ajuste, no navegación, y ocupaba un quinto de la
 * zona del pulgar para algo que se visita una vez por semana. `Cartera` y
 * `Tabla` se alcanzan desde ahí por la misma razón.
 *
 * Lo que ganó el hueco es `Live`, que es lo único de la app con urgencia real:
 * si algo se define hoy, hoy es cuando importa.
 */
function tabsDe(): { id: TabId; label: string; Icon: LucideIcon }[] {
  return [
    { id: "markets", label: S.tabs.markets, Icon: LayoutGrid },
    { id: "live", label: S.tabs.live, Icon: Radio },
    { id: "search", label: S.tabs.search, Icon: Search },
    { id: "portfolio", label: S.tabs.portfolio, Icon: PieChart },
  ];
}

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
  const TABS = tabsDe();
  // el contador sale del feed que ya está cargado: no se pide nada extra por él
  const vivos = state.markets.status === "data" ? contarVivos(state.markets.data) : 0;

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
          const contador = id === "live" && vivos > 0 ? vivos : 0;
          return (
            <li key={id} role="presentation" className="flex-1">
              <button
                type="button"
                role="tab"
                aria-selected={active}
                aria-current={active ? "page" : undefined}
                // el contador es información, no adorno: entra en el nombre
                // accesible en vez de quedarse como un número suelto que el
                // lector de pantalla anuncia sin contexto
                aria-label={contador > 0 ? `${label}: ${S.tabs.liveCount(contador)}` : undefined}
                data-tab={id}
                onClick={() => actions.setTab(id)}
                className={cn(
                  "flex min-h-touch w-full flex-col items-center justify-center gap-0.5 py-2",
                  // inactivo en `text2`, no en `muted`: un icono de navegación
                  // es un control, y el color más apagado del sistema es para
                  // texto secundario, no para algo que se toca
                  active ? "text-teal" : "text-text2",
                )}
              >
                <span className="relative">
                  <Icon
                    aria-hidden
                    className="h-[22px] w-[22px]"
                    strokeWidth={active ? 2.5 : 2}
                  />
                  {contador > 0 ? (
                    <span
                      aria-hidden
                      data-testid="live-contador"
                      className="absolute -right-2.5 -top-1.5 min-w-[17px] rounded-pill px-1 text-center font-sans text-[10px] font-bold leading-[17px] text-[color:var(--teal-ink)]"
                      // relleno sólido con el token vivo: es la única insignia
                      // de la barra y tiene que leerse de reojo. Sin alfa de
                      // Tailwind sobre `var()` (R-017)
                      style={{ backgroundColor: "var(--live)" }}
                    >
                      {contador > 9 ? "9+" : contador}
                    </span>
                  ) : null}
                </span>
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

/** Los destinos vigentes de la barra. Lo usan las pruebas de navegación. */
export const tabIds = (): TabId[] => tabsDe().map((tab) => tab.id);
