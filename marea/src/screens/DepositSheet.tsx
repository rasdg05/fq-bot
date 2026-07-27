import * as React from "react";
import { CreditCard, ArrowDownToLine } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Sheet } from "@/components/ui/sheet";
import { ErrorState } from "@/components/StateViews";
import { Button } from "@/components/ui/button";
import { S } from "@/lib/strings";
import { FLAGS } from "@/lib/flags";
import { canDeposit } from "@/domain/eligibility";
import { isPointsMode } from "@/lib/flags";
import { formatStake } from "@/lib/units";
import { shortAddress } from "@/lib/format";
import { useApp } from "@/state/store";
import { cn } from "@/lib/cn";

function Option({
  icon: Icon,
  title,
  body,
  onClick,
  disabled,
  loading,
  testId,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  testId: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "flex w-full items-start gap-3 rounded-card border border-line2 bg-panel p-4 text-left transition-colors",
        disabled ? "opacity-50" : "hover:border-teal",
      )}
    >
      <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-teal-soft text-teal">
        <Icon aria-hidden className="h-[18px] w-[18px]" />
      </span>
      <span className="min-w-0">
        <span className="block text-[15px] font-semibold text-text">
          {loading ? S.deposit.starting : title}
        </span>
        <span className="mt-0.5 block text-[13px] leading-relaxed text-text2">
          {body}
        </span>
      </span>
    </button>
  );
}

/**
 * Depósito en hoja inferior. Se abre en contexto —nunca antes de dejar
 * explorar (R-002)— y siempre se puede cerrar. Si el proveedor de tarjeta está
 * caído, lo decimos y dejamos el camino de transferencia abierto (RT/9).
 */
export function DepositSheet() {
  const { state, actions } = useApp();
  const [done, setDone] = React.useState<"onramp" | "transfer" | null>(null);
  const [toppedUp, setToppedUp] = React.useState<boolean | null>(null);
  const points = isPointsMode();

  const onrampDisabled = FLAGS.deposit_provider !== "onramp";
  const providerDown =
    state.depositError?.code === "E_DEPOSIT_PROVIDER_UNAVAILABLE";

  // la elegibilidad limita depositar, nunca explorar (R-002)
  const gate = FLAGS.eligibility_enforced
    ? canDeposit(state.country, 0, { depositedUsd: 0 })
    : ({ allowed: true, remainingUsd: Infinity } as const);
  const blocked = gate.allowed === false;

  const handle = React.useCallback(
    async (kind: "onramp" | "transfer") => {
      const ok = await actions.startDeposit(kind);
      if (ok) setDone(kind);
    },
    [actions],
  );

  const close = React.useCallback(
    (open: boolean) => {
      if (!open) {
        setDone(null);
        setToppedUp(null);
        actions.closeDeposit();
      }
    },
    [actions],
  );

  /**
   * Modo puntos: no hay depósito que hacer. La hoja recarga y, sobre todo,
   * declara que esto no es dinero — no en la letra chica, en el cuerpo (R-026).
   */
  if (points) {
    return (
      <Sheet
        open={state.depositOpen}
        onOpenChange={close}
        title={S.points.topUp}
        description={S.points.disclaimer}
      >
        <div data-testid="points-sheet" className="space-y-3 pb-2">
          <div className="rounded-card border border-line2 bg-panel px-4 py-4">
            <p className="text-[12px] uppercase tracking-wide text-muted">
              {S.points.title}
            </p>
            <p className="mt-1 font-display text-prob font-semibold text-text tabular-nums">
              {formatStake(state.points.balance)}
            </p>
          </div>

          <div className="rounded-card border border-line2 bg-panel px-4 py-4">
            <p className="text-[15px] font-semibold text-text">{S.points.why}</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-text2">
              {S.points.whyBody}
            </p>
          </div>

          {toppedUp === false ? (
            <p
              data-testid="points-topup-unavailable"
              role="status"
              className="rounded-card border border-line bg-panel2 px-4 py-3 text-[13px] text-text2"
            >
              {S.points.topUpUnavailable}
            </p>
          ) : null}
          {toppedUp === true ? (
            <p
              data-testid="points-topup-done"
              role="status"
              className="rounded-card border border-line bg-panel2 px-4 py-3 text-[13px] text-text2"
            >
              {S.points.topUpDone}
            </p>
          ) : null}

          <Button
            size="lg"
            data-testid="points-topup"
            onClick={() => setToppedUp(actions.topUpPoints())}
          >
            {S.points.topUp}
          </Button>
          <Button variant="ghost" size="lg" onClick={() => close(false)}>
            {S.deposit.close}
          </Button>
        </div>
      </Sheet>
    );
  }

  return (
    <Sheet
      open={state.depositOpen}
      onOpenChange={close}
      title={S.deposit.title}
      description={S.deposit.subtitle}
    >
      <div data-testid="deposit-sheet" className="space-y-3 pb-2">
        {blocked ? (
          <div
            data-testid="deposit-blocked"
            role="status"
            className="rounded-card border border-line bg-panel2 px-4 py-4"
          >
            <p className="text-[15px] font-semibold text-text">
              {S.deposit.blockedTitle}
            </p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-text2">
              {gate.allowed === false ? gate.message : ""}
            </p>
            <Button
              size="lg"
              variant="secondary"
              className="mt-4"
              data-testid="deposit-blocked-explore"
              onClick={() => close(false)}
            >
              {S.deposit.keepExploring}
            </Button>
          </div>
        ) : null}

        {!blocked && state.depositError ? (
          <div className="-mx-4">
            <ErrorState
              error={state.depositError}
              onRetry={
                state.depositError.retryable ? () => void handle("onramp") : undefined
              }
              testId="deposit-error"
            />
          </div>
        ) : null}

        {blocked ? null : (
        <Option
          testId="deposit-onramp"
          icon={CreditCard}
          title={S.deposit.card}
          body={
            onrampDisabled || providerDown
              ? S.deposit.providerDown
              : S.deposit.cardBody
          }
          disabled={onrampDisabled || providerDown}
          loading={state.depositBusy}
          onClick={() => void handle("onramp")}
        />
        )}

        {blocked ? null : (
        <Option
          testId="deposit-transfer"
          icon={ArrowDownToLine}
          title={S.deposit.crypto}
          body={
            state.wallet
              ? `${S.deposit.cryptoBody} (${shortAddress(state.wallet.address)})`
              : S.deposit.cryptoBody
          }
          loading={state.depositBusy}
          onClick={() => void handle("transfer")}
        />
        )}

        {blocked ? null : (
        <p className="px-1 pt-1 text-[12px] leading-relaxed text-muted">
          {S.deposit.minNote}
        </p>
        )}

        {done ? (
          <p
            data-testid="deposit-started"
            className="rounded-card border border-line bg-panel2 px-4 py-3 text-[13px] leading-relaxed text-text2"
          >
            {done === "onramp"
              ? S.deposit.startedOnramp
              : S.deposit.startedTransfer}
          </p>
        ) : null}

        {blocked ? null : (
          <Button variant="ghost" size="lg" onClick={() => close(false)}>
            {S.deposit.close}
          </Button>
        )}
      </div>
    </Sheet>
  );
}
