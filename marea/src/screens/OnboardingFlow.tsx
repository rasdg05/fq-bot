import * as React from "react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { useApp } from "@/state/store";
import { isPointsMode } from "@/lib/flags";
import { formatStake } from "@/lib/units";
import { WELCOME_GRANT } from "@/domain/points";

/**
 * P0 tiene un techo, no una duración fija. Un splash existe para tapar trabajo
 * real; si la app ya está lista, esperar es tiempo muerto que se paga en LCP.
 * Avanzamos en cuanto el shell pintó, con un mínimo para que no dé un flashazo,
 * y nunca más allá del techo (R-021).
 */
export const SPLASH_MAX_MS = 1500;
export const SPLASH_MIN_MS = 350;
/** Compatibilidad con el presupuesto declarado: el techo es lo que se valida. */
export const SPLASH_MS = SPLASH_MAX_MS;

/**
 * Onboarding value-first, P0–P4. Cinco pasos, ninguno bloqueante, sin KYC y sin
 * frase semilla en el camino (R-002). Sólo llegar al feed cierra el onboarding
 * (R-015): si la wallet falla, el usuario se queda aquí con un error accionable.
 */
export function OnboardingFlow() {
  const { state, actions } = useApp();
  const step = state.onboardingStep;

  // P0 — avanza en cuanto pintó el primer frame, con mínimo y techo
  React.useEffect(() => {
    if (step !== "p0") return;
    const advance = () => actions.goToOnboardingStep("p1");
    const ceiling = setTimeout(advance, SPLASH_MAX_MS);
    const floor = setTimeout(() => {
      // tras el primer frame ya no hay nada que tapar: seguimos
      requestAnimationFrame(() => {
        clearTimeout(ceiling);
        advance();
      });
    }, SPLASH_MIN_MS);
    return () => {
      clearTimeout(ceiling);
      clearTimeout(floor);
    };
  }, [step, actions]);

  // P2 → P3 en cuanto la wallet existe
  React.useEffect(() => {
    if (step === "p2" && state.wallet) actions.goToOnboardingStep("p3");
  }, [step, state.wallet, actions]);

  if (step === "done") return null;

  return (
    <div
      data-testid="onboarding"
      data-step={step}
      className="fixed inset-0 z-40 flex flex-col bg-bg"
      style={{ paddingTop: "var(--safe-t)", paddingBottom: "var(--safe-b)" }}
    >
      <div className="mx-auto flex w-full max-w-[520px] flex-1 flex-col px-6">
        {step === "p0" ? <Splash /> : null}
        {step === "p1" ? <StepPromise /> : null}
        {step === "p2" ? <StepWallet /> : null}
        {step === "p3" ? <StepReady /> : null}
      </div>
    </div>
  );
}

function Splash() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4">
      <svg
        viewBox="0 0 24 24"
        aria-hidden
        className="h-12 w-12 fill-none stroke-teal"
        strokeWidth="1.4"
        strokeLinecap="round"
      >
        <path d="M2 14c2.6 0 2.6-3 5.2-3s2.6 3 5.2 3 2.6-3 5.2-3 2.6 3 4.4 3" />
        <path d="M12 3.5c3.9 0 6.2 2.4 6.2 5.1 0 2.2-1.8 3.8-3.9 3.8-1.7 0-3-1.2-3-2.7 0-1.2.9-2.1 2-2.1" />
      </svg>
      <p className="font-display text-[22px] font-semibold tracking-tight text-text">
        {S.brand.name}
      </p>
    </div>
  );
}

/**
 * P1 — la promesa. Un solo CTA, abajo.
 *
 * Jugando con puntos no hace falta wallet: pedirla sería fricción por costumbre,
 * no por necesidad. En ese modo P1 lleva directo al feed (R-028).
 */
function StepPromise() {
  const { actions } = useApp();
  const points = isPointsMode();
  return (
    <>
      <div className="flex flex-1 flex-col justify-center">
        <h1 className="font-display text-[34px] font-semibold leading-[1.1] tracking-tight text-text">
          {S.onboarding.p1Title}
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-text2">
          {S.onboarding.p1Body}
        </p>
        {points ? (
          <p
            data-testid="onboarding-points-note"
            className="mt-5 rounded-card border border-line bg-panel px-4 py-3 text-[14px] leading-relaxed text-text2"
          >
            {S.points.welcome(formatStake(WELCOME_GRANT))} {S.points.disclaimer}
          </p>
        ) : null}
      </div>
      <div className="pb-6">
        <Button
          size="lg"
          data-testid="onboarding-start"
          onClick={() =>
            points ? actions.finishOnboarding("explore") : actions.goToOnboardingStep("p2")
          }
        >
          {S.onboarding.p1Cta}
        </Button>
      </div>
    </>
  );
}

/** P2 — wallet: crear es primario, conectar secundario. Sin semilla, sin KYC. */
function StepWallet() {
  const { state, actions } = useApp();
  return (
    <>
      <div className="flex flex-1 flex-col justify-center">
        <h1 className="font-display text-[30px] font-semibold leading-[1.15] tracking-tight text-text">
          {S.onboarding.p2Title}
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-text2">
          {S.onboarding.p2Body}
        </p>
        {state.walletError ? (
          <div className="mt-6 -mx-2">
            <ErrorState
              error={state.walletError}
              onRetry={() => void actions.createWallet()}
              testId="onboarding-wallet-error"
            />
          </div>
        ) : null}
      </div>
      <div className="space-y-2 pb-6">
        <Button
          size="lg"
          data-testid="onboarding-create-wallet"
          loading={state.walletBusy === "create"}
          loadingLabel={S.wallet.creating}
          onClick={() => void actions.createWallet()}
        >
          {S.onboarding.p2Primary}
        </Button>
        <Button
          size="lg"
          variant="ghost"
          data-testid="onboarding-connect-wallet"
          loading={state.walletBusy === "connect"}
          loadingLabel={S.wallet.connecting}
          onClick={() => void actions.connectWallet()}
        >
          {S.onboarding.p2Secondary}
        </Button>
      </div>
    </>
  );
}

/** P3 — wallet lista: depositar o explorar. Explorar nunca cuesta nada (R-002). */
function StepReady() {
  const { actions } = useApp();
  return (
    <>
      <div className="flex flex-1 flex-col justify-center">
        <h1 className="font-display text-[30px] font-semibold leading-[1.15] tracking-tight text-text">
          {S.onboarding.p3Title}
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-text2">
          {S.onboarding.p3Body}
        </p>
      </div>
      <div className="space-y-2 pb-6">
        <Button
          size="lg"
          data-testid="onboarding-deposit"
          onClick={() => {
            actions.finishOnboarding("deposit");
            actions.openDeposit("onboarding_p3");
          }}
        >
          {S.onboarding.p3Primary}
        </Button>
        <Button
          size="lg"
          variant="secondary"
          data-testid="onboarding-explore"
          onClick={() => actions.finishOnboarding("explore")}
        >
          {S.onboarding.p3Secondary}
        </Button>
      </div>
    </>
  );
}
