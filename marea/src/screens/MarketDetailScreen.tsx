import * as React from "react";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import type { Market } from "@/domain/types";
import { formatEdgePp, hasEdge } from "@/domain/edge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/StateViews";
import { cn } from "@/lib/cn";
import { S } from "@/lib/strings";
import { FLAGS } from "@/lib/flags";
import { compactUsd, pct, closesIn, fechaCorta } from "@/lib/format";
import { useApp } from "@/state/store";
import { formatStake, stakePresets } from "@/lib/units";
import { isPointsMode } from "@/lib/flags";
import {
  BINARY_OUTCOMES,
  formatMultiplier,
  isBinary,
  quote,
  rankedOutcomes,
} from "@/domain/parimutuel";

/**
 * Detalle de mercado. Una sola zona de decisión: lado → monto → operar, toda
 * en el tercio inferior. El criterio de resolución se lee antes de cualquier
 * CTA de operar (R-013). Sin saldo, el CTA abre el depósito en contexto: nunca
 * hay un muro previo (R-002).
 */
export function MarketDetailScreen({ market }: { market: Market }) {
  const { state, actions } = useApp();
  const AMOUNTS = React.useMemo(() => stakePresets(), []);
  const [side, setSide] = React.useState<string>("si");
  const [amount, setAmount] = React.useState(AMOUNTS[1]);

  // el binario se pinta con sus dos lados enfrentados y N con una lista
  // ordenada. Es la misma matemática y el mismo pozo: cambia cómo se ve, no
  // cómo se paga
  const outcomes = market.outcomes ?? [...BINARY_OUTCOMES];
  const binario = market.pool ? isBinary(market.pool) : outcomes.length === 2;
  const ranked = market.pool ? rankedOutcomes(market.pool, outcomes, amount) : [];
  const comision = market.pool
    ? `${(market.pool.feeBps / 100).toFixed(0)}%`
    : "";

  const points = isPointsMode();
  const balance = points ? state.points.balance : (state.wallet?.balance ?? 0);
  const needsFunds = balance < amount;
  const [compartido, setCompartido] = React.useState(false);
  const closed = market.status === "resolved";
  const closes = closesIn(market.closesAt);
  const fechaCierre = fechaCorta(market.closesAt);
  const showEdge = hasEdge(market) && market.edge !== null;
  const marketPct = pct(market.probability);
  // cotización real del pozo, incluyendo la apuesta que está por hacerse (R-023)
  const priced = market.pool ? quote(market.pool, side, amount) : null;
  const mareaPct =
    market.mareaProbability !== undefined ? pct(market.mareaProbability) : null;

  return (
    <div data-testid="market-detail" className="pb-6">
      <div className="flex items-center gap-1 px-2 pt-2">
        <button
          type="button"
          onClick={actions.closeMarket}
          aria-label={S.common.back}
          className="grid h-touch w-touch place-items-center rounded-full text-text2 hover:text-text"
        >
          <ArrowLeft aria-hidden className="h-5 w-5" />
        </button>
      </div>

      <div className="px-4">
        <div className="flex flex-wrap items-center gap-2">
          {market.status === "live" ? (
            <Badge tone="live" dot>
              {S.badges.live}
            </Badge>
          ) : null}
          {market.status === "closing_soon" ? (
            <Badge tone="hot">{S.badges.closingSoon}</Badge>
          ) : null}
          {market.country || market.region === "latam" ? (
            <Badge tone="latam">{market.country ?? S.badges.latam}</Badge>
          ) : null}
          <span className="text-[12px] font-medium text-muted">
            {S.categories[market.category]}
          </span>
        </div>

        <h1 className="mt-3 font-display text-[24px] font-semibold leading-snug text-text">
          {market.title}
        </h1>

        {/* nodo dominante: la probabilidad (R-004) */}
        <div className="mt-6 flex items-end gap-4">
          <div data-dominant="probability">
            <div
              data-role="probability"
              className="font-display font-semibold tabular-nums text-text text-prob-lg"
            >
              {marketPct}
              <span className="ml-1 align-top text-[0.35em] font-bold text-text2">
                %
              </span>
            </div>
            <div className="mt-1 text-[12px] font-medium uppercase tracking-wide text-muted">
              {market.pool ? S.market.hereLabel : S.market.probability}
            </div>
          </div>
          {showEdge ? (
            <Badge tone="edge" className="mb-3" data-testid="edge-badge-detail">
              {S.market.edgeCardWith(
                market.edgeLabel ?? S.market.mareaProbability,
                formatEdgePp(market.edge as number),
              )}
            </Badge>
          ) : null}
        </div>

        {/* segundo ancla: la lectura comparada, con su porqué al lado */}
        {showEdge && mareaPct ? (
          <div className="mt-4 rounded-card border border-line bg-panel px-4 py-3">
            <p
              data-testid="edge-detail-line"
              className="font-mono text-[14px] font-semibold text-text tabular-nums"
            >
              {market.edgeLabel
                ? S.market.edgeDetailWith(
                    marketPct,
                    market.edgeLabel,
                    mareaPct,
                    formatEdgePp(market.edge as number),
                  )
                : S.market.edgeDetail(
                    marketPct,
                    mareaPct,
                    formatEdgePp(market.edge as number),
                  )}
            </p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-text2">
              {market.mareaBasis ?? S.market.edgeExplainer}
            </p>
          </div>
        ) : null}

        <dl className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-card border border-line2 bg-panel px-4 py-3">
            <dt className="text-[12px] uppercase tracking-wide text-muted">
              {/* en mercado propio no es volumen operado: es el pozo */}
              {market.pool ? S.market.pot : S.market.volume}
            </dt>
            <dd className="mt-0.5 font-mono text-[15px] font-semibold text-text tabular-nums">
              {market.pool ? formatStake(market.volume) : compactUsd(market.volume)}
            </dd>
          </div>
          <div className="rounded-card border border-line2 bg-panel px-4 py-3">
            <dt className="text-[12px] uppercase tracking-wide text-muted">
              {S.market.closes}
            </dt>
            <dd className="mt-0.5 font-mono text-[15px] font-semibold text-text tabular-nums">
              {closes ?? S.badges.closed}
            </dd>
            {/* la fecha exacta, no sólo "en 4 d": saber qué día cierra cambia
                la decisión de entrar, y "en 4 d" obliga a hacer la cuenta */}
            {fechaCierre ? (
              <dd
                data-testid="cierra-el"
                className="mt-0.5 text-[11px] leading-tight text-muted"
              >
                {S.market.cierraEl(fechaCierre)}
              </dd>
            ) : null}
          </div>
        </dl>

        {market.pool ? (
          <section
            data-testid="pool-breakdown"
            className="mt-4 rounded-card border border-line2 bg-panel px-4 py-3"
          >
            <h2 className="text-[12px] font-bold uppercase tracking-wide text-muted">
              {S.market.poolTitle}
            </h2>
            <p className="mt-1.5 text-[14px] leading-relaxed text-text2">
              {binario
                ? S.market.poolBody(
                    formatStake(market.pool.outcomes.si ?? 0),
                    formatStake(market.pool.outcomes.no ?? 0),
                    comision,
                  )
                : S.market.poolBodyN(
                    ranked
                      .map((o) => S.market.poolShare(o.label, formatStake(o.staked)))
                      .join("; "),
                    comision,
                  )}
            </p>
          </section>
        ) : null}

        {/* compartir es el canal de crecimiento más barato que tenemos: la
            liga lleva vista previa con la pregunta y la probabilidad */}
        <button
          type="button"
          data-testid="market-share"
          onClick={() => void compartirMercado(market, setCompartido)}
          className="mt-4 min-h-[44px] w-full rounded-card border border-line2 bg-panel text-[14px] font-semibold text-teal"
        >
          {compartido ? S.market.compartido : S.market.compartir}
        </button>

        {/* el criterio de resolución va ANTES del CTA de operar (R-013) */}
        <section
          data-testid="resolution-summary"
          className="mt-4 rounded-card border border-line2 bg-panel px-4 py-3"
        >
          <h2 className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-wide text-muted">
            <ShieldCheck aria-hidden className="h-4 w-4" />
            {S.market.resolution}
          </h2>
          <p className="mt-1.5 text-[14px] leading-relaxed text-text2">
            {market.resolution_summary}
          </p>

          {/* si ya resolvió, se dice qué salió y con qué lectura: el resultado
              no aparece de la nada (R-040) */}
          {market.outcome ? (
            <div
              data-testid="market-outcome"
              className="mt-3 border-t border-line pt-3"
            >
              <p className="text-[13px] font-bold text-text">
                {S.market.resolvedAs(
                  outcomes.find((o) => o.id === market.outcome)?.label ??
                    market.outcome,
                )}
              </p>
              {market.settlementEvidence ? (
                <p className="mt-1 text-[13px] leading-snug text-text2">
                  {market.settlementEvidence}
                </p>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>

      {/* zona de decisión única, en el alcance del pulgar (R-010) */}
      <section
        data-testid="decision-zone"
        aria-label={binario ? S.market.chooseSide : S.market.chooseOutcome}
        className="mt-6 border-t border-line2 bg-panel2 px-4 pt-5"
      >
        {binario ? (
          // los dos lados enfrentados: quien apuesta ve contra qué apuesta
          <div className="flex gap-3">
            <Button
              variant={side === "si" ? "yes" : "secondary"}
              size="lg"
              aria-pressed={side === "si"}
              data-testid="side-si"
              onClick={() => setSide("si")}
            >
              {S.market.yes} · {marketPct}%
            </Button>
            <Button
              variant={side === "no" ? "no" : "secondary"}
              size="lg"
              aria-pressed={side === "no"}
              data-testid="side-no"
              onClick={() => setSide("no")}
            >
              {S.market.no} · {100 - Number(marketPct)}%
            </Button>
          </div>
        ) : (
          // con N respuestas se listan todas, ordenadas por probabilidad, cada
          // una con su porcentaje y su pago. Ninguna se esconde: mostrar sólo
          // las favoritas sería mostrar medio mercado (R-063)
          <ul data-testid="outcome-list" className="flex flex-col gap-2">
            {ranked.map((outcome) => {
              const elegido = side === outcome.id;
              return (
                <li key={outcome.id}>
                  <button
                    type="button"
                    aria-pressed={elegido}
                    data-testid={`outcome-${outcome.id}`}
                    onClick={() => setSide(outcome.id)}
                    className={cn(
                      "flex min-h-touch w-full items-center justify-between gap-3 rounded-card border px-4 py-3 text-left transition-colors",
                      elegido
                        ? "border-teal bg-teal-soft"
                        : "border-line2 bg-panel",
                    )}
                  >
                    <span
                      className={cn(
                        "text-[15px] font-semibold",
                        elegido ? "text-teal" : "text-text",
                      )}
                    >
                      {outcome.label}
                    </span>
                    <span className="flex items-baseline gap-3 tabular-nums">
                      <span className="font-mono text-[15px] font-bold text-text">
                        {pct(outcome.probability)}%
                      </span>
                      <span className="text-[13px] font-medium text-text2">
                        {S.market.pays} {formatMultiplier(outcome.multiplier)}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <div className="mt-4">
          <p className="mb-2 text-[12px] font-bold uppercase tracking-wide text-muted">
            {S.market.amount}
          </p>
          <div className="flex gap-2">
            {AMOUNTS.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={amount === value}
                onClick={() => setAmount(value)}
                className={cn(
                  "min-h-touch flex-1 rounded-pill border text-[15px] tabular-nums transition-colors",
                  amount === value
                    ? "border-teal bg-teal-soft font-bold text-teal"
                    : "border-line2 font-medium text-text2",
                )}
              >
                {formatStake(value)}
              </button>
            ))}
          </div>
        </div>

        {state.tradeError ? (
          <div className="mt-4">
            <ErrorState
              error={state.tradeError}
              onRetry={() => void actions.submitTrade(market, side, amount)}
              testId="trade-error"
            />
          </div>
        ) : null}

        <div className="mt-5 pb-2">
          {needsFunds ? (
            <Button
              size="lg"
              data-testid="detail-deposit-cta"
              onClick={() => actions.openDeposit("market_detail")}
            >
              {points ? S.points.topUp : S.header.deposit}
            </Button>
          ) : (
            <Button
              size="lg"
              data-testid="detail-trade-cta"
              disabled={closed}
              loading={state.tradeBusy}
              loadingLabel={S.market.tradePreparing}
              onClick={() => void actions.submitTrade(market, side, amount)}
            >
              {market.pool ? S.market.betCta : S.market.tradeCta} {formatStake(amount)}
            </Button>
          )}
          {priced && !closed ? (
            <p
              data-testid="payout-hint"
              className="mt-3 text-center text-[13px] font-semibold text-text"
            >
              {S.market.payoutHint(
                formatMultiplier(priced.multiplier),
                formatStake(priced.toWin),
              )}
            </p>
          ) : null}
          <p className="mt-2 text-center text-[12px] leading-relaxed text-muted">
            {closed ? S.market.tradeDisabledReason : S.market.maxLoss}
          </p>
          {points ? (
            <p
              data-testid="points-disclaimer"
              className="mt-2 text-center text-[12px] leading-relaxed text-muted"
            >
              {S.points.disclaimer}
            </p>
          ) : null}
          {!market.pool && FLAGS.trade_execution_mode === "aggregated" ? (
            <p
              data-testid="aggregation-notice"
              className="mt-2 text-center text-[12px] leading-relaxed text-muted"
            >
              {S.market.aggregatedNotice}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

/**
 * Comparte el mercado. En móvil abre la hoja nativa (WhatsApp, Telegram); si el
 * navegador no la trae, copia la liga y lo dice. Nunca deja al usuario sin
 * saber qué pasó.
 */
async function compartirMercado(
  market: import("@/domain/types").Market,
  avisar: (valor: boolean) => void,
) {
  const enlace = `${globalThis.location?.origin ?? ""}/m/${encodeURIComponent(market.id)}`;
  const texto = S.market.compartirTexto(
    market.title,
    `${Math.round(market.probability * 100)}%`,
  );
  try {
    const nav = globalThis.navigator as Navigator & {
      share?: (datos: { title: string; text: string; url: string }) => Promise<void>;
    };
    if (nav?.share) {
      await nav.share({ title: market.title, text: texto, url: enlace });
      return;
    }
    await nav.clipboard?.writeText(`${texto}\n${enlace}`);
    avisar(true);
    setTimeout(() => avisar(false), 2_000);
  } catch {
    /* si el usuario cancela la hoja nativa no pasa nada */
  }
}
