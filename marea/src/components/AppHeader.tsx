import { User as UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { Brandmark } from "@/components/ui/brandmark";
import { useApp } from "@/state/store";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { isPointsMode } from "@/lib/flags";

/**
 * Header. Dos estados y nada más.
 *
 * Sin sesión: `Entrar` y `Crear cuenta`, las dos puertas a la vista. Con una
 * sola, quien ya tenía cuenta no sabe por dónde volver.
 *
 * Con sesión: saldo y avatar. El botón de depósito se fue de aquí — el saldo
 * **es** el botón: con saldo cero abre la recarga y con saldo abre la cuenta.
 * Así el header conserva dos elementos y nadie se queda sin camino (V12).
 *
 * La acción que decide sigue viviendo abajo, en la zona del pulgar (R-010).
 */
export function AppHeader() {
  const { state, actions } = useApp();
  const puntos = isPointsMode();
  const balance = puntos ? state.points.balance : (state.wallet?.balance ?? 0);
  /**
   * "Con sesión" aquí es **tener saldo propio**: wallet creada o puntos
   * otorgados. La cuenta de servidor es otro eje —sirve para que lo tuyo siga
   * aquí mañana— y quien entró por puntos todavía no la tiene. Atar el header
   * a la cuenta escondía el saldo justo a quien acaba de empezar.
   */
  const dentro = puntos || state.wallet !== null;
  const sesion = state.cuenta;
  const sinFondos = balance <= 0;
  const inicial = sesion ? sesion.usuario.trim().charAt(0).toUpperCase() : null;

  return (
    <header
      className="sticky top-0 z-30 border-b border-line2 bg-bg"
      style={{ paddingTop: "var(--safe-t)" }}
    >
      {/* 60 px de alto: el logo pide 34 y respira. Es el único sitio del
          producto donde el cromo crece a propósito — lo primero que se lee al
          abrir tiene que ser el nombre */}
      <div className="mx-auto flex h-[60px] w-full max-w-[520px] items-center gap-3 px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <Brandmark className="h-[34px] w-[34px]" />
          <span className="font-display text-[27px] font-bold leading-none tracking-[-0.02em] text-text">
            {S.brand.name}
          </span>
        </div>

        {dentro ? (
          <div className="ml-auto flex items-center gap-2.5">
            <button
              type="button"
              data-testid="header-balance"
              onClick={() =>
                sinFondos ? actions.openDeposit("header") : actions.setTab("portfolio")
              }
              className="flex min-h-touch flex-col items-end justify-center leading-tight"
            >
              {/* con saldo cero la etiqueta deja de nombrar lo que hay y nombra
                  lo que falta: el bloque entero abre la recarga. Es lo que
                  conserva V12 sin meter un tercer elemento en el header */}
              <span
                data-testid={sinFondos ? "header-deposit" : undefined}
                className={cn(
                  "text-[10px] font-bold uppercase tracking-[0.06em]",
                  sinFondos ? "text-teal" : "text-muted",
                )}
              >
                {sinFondos
                  ? puntos
                    ? S.points.topUp
                    : S.header.deposit
                  : S.header.balance}
              </span>
              <span
                className={cn(
                  "font-mono text-[15px] font-semibold tabular-nums",
                  // el saldo en cero se apaga: es la señal de que hay que recargar
                  sinFondos ? "text-muted" : "text-text",
                )}
              >
                {formatStake(balance)}
              </span>
            </button>
            <button
              type="button"
              data-testid="header-avatar"
              aria-label={
                sesion ? S.cuenta.sesionDe(sesion.usuario) : S.tabs.profile
              }
              onClick={() =>
                sesion ? actions.setTab("profile") : actions.abrirCuenta(true, "registro")
              }
              className="relative grid h-touch w-touch shrink-0 place-items-center"
            >
              {/* el círculo mide 32 y el target 44: el aire de alrededor es
                  parte del botón, no un hueco muerto (R-010) */}
              <span className="grid h-8 w-8 place-items-center rounded-full bg-panel2 text-[13px] font-bold text-text2 ring-1 ring-line2">
                {inicial ?? <UserIcon aria-hidden className="h-4 w-4" />}
              </span>
              {/* sin saldo, el punto dice dónde tocar. No es un tercer elemento:
                  vive encima del avatar */}
              {sinFondos ? (
                <span
                  aria-hidden
                  className="absolute bottom-1.5 right-1.5 h-2 w-2 rounded-full bg-teal ring-2 ring-bg"
                />
              ) : null}
            </button>
          </div>
        ) : (
          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              data-testid="header-entrar"
              onClick={() => actions.abrirCuenta(true, "entrar")}
              className="min-h-touch px-2 text-[14px] font-semibold text-text2"
            >
              {S.cuenta.entrarCta}
            </button>
            <Button
              size="sm"
              variant="primary"
              data-testid="header-crear-cuenta"
              onClick={() => actions.abrirCuenta(true, "registro")}
            >
              {S.cuenta.sinCuentaCta}
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}
