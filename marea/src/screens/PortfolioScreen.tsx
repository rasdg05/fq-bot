import * as React from "react";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { useApp } from "@/state/store";
import { cn } from "@/lib/cn";

/**
 * Portafolio. Vacío no es un callejón: siempre ofrece volver al feed (R-006).
 */
export function PortfolioScreen() {
  const { state, actions } = useApp();
  const { positions } = state;

  React.useEffect(() => {
    if (positions.status === "loading") void actions.loadPositions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (positions.status === "loading") {
    return (
      <div className="pt-4">
        <ListSkeleton rows={3} />
      </div>
    );
  }

  if (positions.status === "error") {
    return (
      <div className="pt-6">
        <ErrorState
          error={positions.error}
          onRetry={() => void actions.loadPositions()}
          testId="portfolio-error"
        />
      </div>
    );
  }

  const open = positions.data.filter((p) => p.status === "open");
  const settled = positions.data.filter((p) => p.status !== "open");

  return (
    <div data-testid="portfolio-screen" className="pb-6">
      <h1 className="px-4 pb-1 pt-5 font-display text-[24px] font-semibold text-text">
        {S.portfolio.title}
      </h1>

      {positions.data.length === 0 ? (
        <div className="pt-5">
          <EmptyState
            title={S.portfolio.empty}
            body={S.portfolio.emptyBody}
            ctaLabel={S.portfolio.emptyCta}
            onCta={() => actions.setTab("markets")}
            testId="portfolio-empty"
          />
        </div>
      ) : (
        <div className="space-y-6 pt-4">
          {open.length > 0 ? (
            <Section title={S.portfolio.open} items={open} />
          ) : null}
          {settled.length > 0 ? (
            <Section title={S.portfolio.settled} items={settled} />
          ) : null}
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  items,
}: {
  title: string;
  items: import("@/domain/types").Position[];
}) {
  return (
    <section>
      <h2 className="px-4 pb-2 text-[12px] font-bold uppercase tracking-wide text-muted">
        {title}
      </h2>
      <div className="space-y-3 px-4">
        {items.map((position) => (
          <Card key={position.id} className="p-4" data-testid="position-row">
            <p className="font-display text-[16px] font-semibold leading-snug text-text">
              {position.marketTitle ?? position.market_id}
            </p>
            <div className="mt-3 flex items-end justify-between gap-3">
              <div>
                <p className="text-[12px] uppercase tracking-wide text-muted">
                  {S.portfolio.side}
                </p>
                <p className="mt-0.5 text-[15px] font-bold text-text">
                  {position.side === "si" ? S.market.yes : S.market.no}
                  <span className="ml-2 font-mono text-[13px] font-medium text-text2 tabular-nums">
                    {formatStake(position.size)}
                  </span>
                </p>
              </div>
              <div className="text-right">
                {position.toWin !== undefined ? (
                  <>
                    {/* en parimutuel lo honesto es el pago potencial, no un
                        resultado que no existe hasta que resuelve (R-029) */}
                    <p className="text-[12px] uppercase tracking-wide text-muted">
                      {S.portfolio.toWin}
                    </p>
                    <p
                      data-testid="position-towin"
                      className="mt-0.5 font-mono text-[15px] font-bold tabular-nums text-text"
                    >
                      {formatStake(position.toWin)}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-[12px] uppercase tracking-wide text-muted">
                      {S.portfolio.pnl}
                    </p>
                    {/* el signo acompaña al color: se lee sin él (R-005) */}
                    <p
                      className={cn(
                        "mt-0.5 font-mono text-[15px] font-bold tabular-nums",
                        position.pnl > 0 && "text-[color:var(--up)]",
                        position.pnl < 0 && "text-[color:var(--dn)]",
                        position.pnl === 0 && "text-text2",
                      )}
                    >
                      {position.pnl > 0 ? "+" : position.pnl < 0 ? "−" : ""}
                      {formatStake(Math.abs(position.pnl))}
                    </p>
                  </>
                )}
              </div>
            </div>

            {position.evidence ? (
              <div className="mt-3 border-t border-line pt-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[12px] uppercase tracking-wide text-muted">
                    {S.portfolio.evidence}
                  </p>
                  <span
                    data-testid="position-outcome"
                    className="text-[12px] font-bold uppercase tracking-wide text-text2"
                  >
                    {position.status === "won"
                      ? S.portfolio.won
                      : position.status === "lost"
                        ? S.portfolio.lost
                        : S.portfolio.refunded}
                  </span>
                </div>
                {/* la evidencia se muestra completa: es lo que hace auditable
                    el pago, y esconderla sería pedir fe (R-040) */}
                <p
                  data-testid="position-evidence"
                  className="mt-1 text-[13px] leading-snug text-text2"
                >
                  {position.evidence}
                </p>
              </div>
            ) : null}
          </Card>
        ))}
      </div>
    </section>
  );
}
