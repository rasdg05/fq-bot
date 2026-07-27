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
import { compactUsd, pct, usd, closesIn } from "@/lib/format";
import { useApp } from "@/state/store";

const AMOUNTS = [5, 10, 25, 50];

/**
 * Detalle de mercado. Una sola zona de decisión: lado → monto → operar, toda
 * en el tercio inferior. El criterio de resolución se lee antes de cualquier
 * CTA de operar (R-013). Sin saldo, el CTA abre el depósito en contexto: nunca
 * hay un muro previo (R-002).
 */
export function MarketDetailScreen({ market }: { market: Market }) {
  const { state, actions } = useApp();
  const [side, setSide] = React.useState<"si" | "no">("si");
  const [amount, setAmount] = React.useState(AMOUNTS[1]);

  const balance = state.wallet?.balance ?? 0;
  const needsFunds = balance < amount;
  const closed = market.status === "resolved";
  const closes = closesIn(market.closesAt);
  const showEdge = hasEdge(market) && market.edge !== null;
  const marketPct = pct(market.probability);
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
          {market.region === "latam" ? (
            <Badge tone="latam">{S.badges.latam}</Badge>
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
              {S.market.probability}
            </div>
          </div>
          {showEdge ? (
            <Badge tone="edge" className="mb-3" data-testid="edge-badge-detail">
              {S.market.edgeCard(formatEdgePp(market.edge as number))}
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
              {S.market.edgeDetail(
                marketPct,
                mareaPct,
                formatEdgePp(market.edge as number),
              )}
            </p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-text2">
              {S.market.edgeExplainer}
            </p>
          </div>
        ) : null}

        <dl className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-card border border-line2 bg-panel px-4 py-3">
            <dt className="text-[12px] uppercase tracking-wide text-muted">
              {S.market.volume}
            </dt>
            <dd className="mt-0.5 font-mono text-[15px] font-semibold text-text tabular-nums">
              {compactUsd(market.volume)}
            </dd>
          </div>
          <div className="rounded-card border border-line2 bg-panel px-4 py-3">
            <dt className="text-[12px] uppercase tracking-wide text-muted">
              {S.market.closes}
            </dt>
            <dd className="mt-0.5 font-mono text-[15px] font-semibold text-text tabular-nums">
              {closes ?? "—"}
            </dd>
          </div>
        </dl>

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
        </section>
      </div>

      {/* zona de decisión única, en el alcance del pulgar (R-010) */}
      <section
        data-testid="decision-zone"
        aria-label={S.market.chooseSide}
        className="mt-6 border-t border-line2 bg-panel2 px-4 pt-5"
      >
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
                {usd(value)}
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
              {S.header.deposit}
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
              {S.market.tradeCta} {usd(amount)}
            </Button>
          )}
          <p className="mt-3 text-center text-[12px] leading-relaxed text-muted">
            {closed ? S.market.tradeDisabledReason : S.market.maxLoss}
          </p>
          {FLAGS.trade_execution_mode === "aggregated" ? (
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
