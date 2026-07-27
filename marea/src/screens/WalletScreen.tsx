import * as React from "react";
import { Copy, Check } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { usd, shortAddress } from "@/lib/format";
import { useApp } from "@/state/store";

/**
 * Cartera. Saldo 0 no bloquea nada: el copy lo dice explícito (R-002).
 */
export function WalletScreen() {
  const { state, actions } = useApp();
  const [copied, setCopied] = React.useState(false);
  const wallet = state.wallet;

  const copy = React.useCallback(async () => {
    if (!wallet) return;
    try {
      await navigator.clipboard?.writeText(wallet.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* sin portapapeles: la dirección sigue visible y seleccionable */
    }
  }, [wallet]);

  return (
    <div data-testid="wallet-screen" className="pb-6">
      <h1 className="px-4 pb-4 pt-5 font-display text-[24px] font-semibold text-text">
        {S.wallet.title}
      </h1>

      {state.walletError ? (
        <div className="pb-4">
          <ErrorState
            error={state.walletError}
            onRetry={() => void actions.createWallet()}
            testId="wallet-error"
          />
        </div>
      ) : null}

      {wallet ? (
        <div className="space-y-4 px-4">
          <Card className="p-5">
            <p className="text-[12px] uppercase tracking-wide text-muted">
              {S.header.balance}
            </p>
            <p className="mt-1 font-display text-prob font-semibold text-text tabular-nums">
              {usd(wallet.balance)}
            </p>
            {wallet.balance <= 0 ? (
              <p className="mt-2 text-[14px] leading-relaxed text-text2">
                {S.wallet.balanceZeroBody}
              </p>
            ) : null}
            <Button
              size="lg"
              className="mt-5"
              data-testid="wallet-deposit-cta"
              onClick={() => actions.openDeposit("wallet_tab")}
            >
              {S.header.deposit}
            </Button>
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[12px] uppercase tracking-wide text-muted">
                  {S.wallet.address}
                </p>
                <p className="mt-0.5 truncate font-mono text-[14px] text-text">
                  {shortAddress(wallet.address)}
                </p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => void copy()}>
                {copied ? (
                  <Check aria-hidden className="h-4 w-4" />
                ) : (
                  <Copy aria-hidden className="h-4 w-4" />
                )}
                {copied ? S.wallet.copied : S.wallet.copy}
              </Button>
            </div>
            <p className="mt-4 text-[12px] uppercase tracking-wide text-muted">
              {S.wallet.chain}
            </p>
            <p className="mt-0.5 text-[14px] text-text">{wallet.chain}</p>
          </Card>
        </div>
      ) : (
        <div className="space-y-3 px-4">
          <Card className="p-5">
            <p className="font-display text-[18px] font-semibold text-text">
              {S.onboarding.p2Title}
            </p>
            <p className="mt-1.5 text-[14px] leading-relaxed text-text2">
              {S.onboarding.p2Body}
            </p>
            <Button
              size="lg"
              className="mt-5"
              loading={state.walletBusy === "create"}
              loadingLabel={S.wallet.creating}
              onClick={() => void actions.createWallet()}
            >
              {S.wallet.create}
            </Button>
            <Button
              size="lg"
              variant="ghost"
              className="mt-2"
              loading={state.walletBusy === "connect"}
              loadingLabel={S.wallet.connecting}
              onClick={() => void actions.connectWallet()}
            >
              {S.wallet.connect}
            </Button>
          </Card>
        </div>
      )}
    </div>
  );
}
