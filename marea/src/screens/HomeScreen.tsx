import * as React from "react";
import type { Market, MarketCategory } from "@/domain/types";
import { MarketCard } from "@/components/MarketCard";
import { Chip, ChipRow } from "@/components/ui/chip";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { useApp } from "@/state/store";
import { hasEdge } from "@/domain/edge";

const CATEGORIES: MarketCategory[] = [
  "cripto",
  "economia",
  "deportes",
  "politica",
  "cultura",
  "otros",
];

function isHot(market: Market): boolean {
  return Boolean(market.hot) || market.status === "live" || hasEdge(market);
}

/**
 * Home. Un solo trabajo: descubrir. `Hot ahora` primero, chips de categoría
 * como filtro, y la lista completa debajo. Los cuatro estados del listado son
 * excluyentes: nunca se montan dos a la vez (R-014).
 */
export function HomeScreen() {
  const { state, actions } = useApp();
  const { markets, category } = state;

  React.useEffect(() => {
    if (markets.status === "loading") void actions.loadMarkets();
    // sólo al montar: el feed no se recarga solo al cambiar de filtro
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const all = markets.status === "data" ? markets.data : [];
  const filtered = React.useMemo(
    () => (category === "all" ? all : all.filter((m) => m.category === category)),
    [all, category],
  );
  const hot = React.useMemo(() => filtered.filter(isHot), [filtered]);
  const rest = React.useMemo(() => filtered.filter((m) => !isHot(m)), [filtered]);

  if (markets.status === "loading") {
    return (
      <div className="pt-4">
        <ListSkeleton rows={4} />
      </div>
    );
  }

  if (markets.status === "error") {
    return (
      <div className="pt-6">
        <ErrorState error={markets.error} onRetry={() => void actions.loadMarkets()} />
      </div>
    );
  }

  return (
    <div data-testid="home-screen" className="pb-6">
      <ChipRow className="pt-3" aria-label={S.search.byCategory}>
        <Chip
          active={category === "all"}
          onClick={() => actions.setCategory("all")}
        >
          {S.feed.allCategories}
        </Chip>
        {CATEGORIES.map((id) => (
          <Chip
            key={id}
            active={category === id}
            onClick={() => actions.setCategory(id)}
          >
            {S.categories[id]}
          </Chip>
        ))}
      </ChipRow>

      {filtered.length === 0 ? (
        <div className="pt-6">
          <EmptyState
            title={S.feed.empty}
            body={category === "all" ? undefined : S.feed.emptyFiltered}
            ctaLabel={category === "all" ? undefined : S.feed.emptyCta}
            onCta={category === "all" ? undefined : () => actions.setCategory("all")}
            testId="feed-empty"
          />
        </div>
      ) : (
        <>
          {hot.length > 0 ? (
            <section aria-labelledby="hot-heading" className="pt-5">
              <h2
                id="hot-heading"
                className="px-4 pb-3 font-display text-[20px] font-semibold text-text"
              >
                {S.feed.hotNow}
              </h2>
              <div className="space-y-3 px-4">
                {hot.map((market) => (
                  <MarketCard
                    key={market.id}
                    market={market}
                    onOpen={actions.openMarket}
                  />
                ))}
              </div>
            </section>
          ) : null}

          {rest.length > 0 ? (
            <section aria-labelledby="all-heading" className="pt-7">
              <h2
                id="all-heading"
                className="px-4 pb-3 font-display text-[20px] font-semibold text-text"
              >
                {S.feed.sectionAll}
              </h2>
              <div className="space-y-3 px-4">
                {rest.map((market) => (
                  <MarketCard
                    key={market.id}
                    market={market}
                    onOpen={actions.openMarket}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
