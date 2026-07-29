import { User, Wallet as WalletIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApp } from "@/state/store";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { isPointsMode } from "@/lib/flags";

function Brandmark() {
  // espiral de marea: una sola idea gráfica, hereda el teal de los tokens
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden
      className="h-6 w-6 fill-none stroke-teal"
      strokeWidth="1.6"
      strokeLinecap="round"
    >
      <path d="M2 14c2.6 0 2.6-3 5.2-3s2.6 3 5.2 3 2.6-3 5.2-3 2.6 3 4.4 3" />
      <path d="M12 3.5c3.9 0 6.2 2.4 6.2 5.1 0 2.2-1.8 3.8-3.9 3.8-1.7 0-3-1.2-3-2.7 0-1.2.9-2.1 2-2.1" />
    </svg>
  );
}

/**
 * El avatar del perfil. Con cuenta muestra la inicial elegida por el usuario;
 * sin cuenta, la silueta genérica. No se genera ninguna cara: una foto que el
 * usuario no puso es una identidad que no es suya.
 */
function AvatarPerfil({ usuario }: { usuario?: string }) {
  const inicial = usuario?.trim().charAt(0).toUpperCase();
  return (
    <span
      aria-hidden
      data-testid="header-avatar"
      className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-teal-soft font-display text-[14px] font-semibold text-teal"
    >
      {inicial || <User className="h-4 w-4" strokeWidth={2.2} />}
    </span>
  );
}

/**
 * Header. Marca a la izquierda; saldo, depósito y perfil a la derecha. El
 * perfil vive aquí desde que la barra inferior bajó a cuatro destinos: es
 * ajuste, no navegación, y la zona del pulgar es para lo que se usa a diario
 * (R-010). Los CTA que deciden siguen abajo.
 * Con saldo 0 el header muestra `Depositar`, nunca un muro (V12).
 */
export function AppHeader() {
  const { state, actions } = useApp();
  const wallet = state.wallet;
  // en modo puntos el saldo vive en el ledger, no en la wallet
  const points = isPointsMode();
  const balance = points ? state.points.balance : (wallet?.balance ?? 0);
  const hasAccount = points || wallet !== null;
  const noFunds = balance <= 0;

  return (
    <header
      className="sticky top-0 z-30 border-b border-line2 bg-bg"
      style={{ paddingTop: "var(--safe-t)" }}
    >
      <div className="mx-auto flex h-14 w-full max-w-[520px] items-center gap-3 px-4">
        <div className="flex items-center gap-2">
          <Brandmark />
          <span className="font-display text-[18px] font-semibold tracking-tight text-text">
            {S.brand.name}
          </span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <div className="text-right leading-tight" data-testid="header-balance">
            <div className="text-[11px] uppercase tracking-wide text-muted">
              {S.header.balance}
            </div>
            <div className="font-mono text-[14px] font-semibold text-text tabular-nums">
              {hasAccount ? formatStake(balance) : "—"}
            </div>
          </div>
          {noFunds ? (
            <Button
              size="sm"
              variant="primary"
              data-testid="header-deposit"
              onClick={() => actions.openDeposit("header")}
            >
              <WalletIcon aria-hidden className="h-4 w-4" />
              {points ? S.points.topUp : S.header.deposit}
            </Button>
          ) : null}
          {/* 44 px de target aunque el avatar mida 32: el área táctil no se
              encoge con el adorno (R-010) */}
          <button
            type="button"
            data-testid="header-profile"
            aria-label={S.header.profile}
            aria-current={state.tab === "profile" ? "page" : undefined}
            onClick={() => actions.setTab("profile")}
            className="-mr-2 flex min-h-touch min-w-touch items-center justify-center"
          >
            <AvatarPerfil usuario={state.cuenta?.usuario} />
          </button>
        </div>
      </div>
    </header>
  );
}
