import * as React from "react";
import { Search as SearchIcon } from "lucide-react";
import type { MarketCategory } from "@/domain/types";
import { MarketCard } from "@/components/MarketCard";
import { Chip, ChipRow } from "@/components/ui/chip";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { useApp } from "@/state/store";

const CATEGORIES: MarketCategory[] = [
  "cripto",
  "economia",
  "deportes",
  "politica",
  "cultura",
  "otros",
];

function normalize(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/** Buscar. Mismo contrato de estados que el feed: nada se inventa aquí. */
export function SearchScreen() {
  const { state, actions } = useApp();
  const [query, setQuery] = React.useState("");
  const { markets } = state;

  React.useEffect(() => {
    if (markets.status === "loading") void actions.loadMarkets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (markets.status === "loading") {
    return (
      <div className="pt-4">
        <ListSkeleton rows={3} />
      </div>
    );
  }
  if (markets.status === "error") {
    return (
      <div className="pt-6">
        <ErrorState
          error={markets.error}
          onRetry={() => void actions.loadMarkets()}
          testId="search-error"
        />
      </div>
    );
  }

  const q = normalize(query.trim());
  const byCategory =
    state.category === "all"
      ? markets.data
      : markets.data.filter((m) => m.category === state.category);
  const results = q
    ? byCategory.filter((m) => normalize(m.title).includes(q))
    : byCategory;

  return (
    <div data-testid="search-screen" className="pb-6">
      <h1 className="px-4 pb-3 pt-5 font-display text-[24px] font-semibold text-text">
        {S.search.title}
      </h1>

      <div className="px-4">
        <div className="flex min-h-touch items-center gap-2 rounded-pill border border-line2 bg-panel px-4">
          <SearchIcon aria-hidden className="h-4 w-4 shrink-0 text-muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={S.search.placeholder}
            aria-label={S.search.title}
            className="w-full bg-transparent py-2 text-[16px] text-text outline-none placeholder:text-muted"
          />
        </div>
      </div>

      <ChipRow className="pt-3" aria-label={S.search.byCategory}>
        <Chip active={state.category === "all"} onClick={() => actions.setCategory("all")}>
          {S.feed.allCategories}
        </Chip>
        {CATEGORIES.map((id) => (
          <Chip
            key={id}
            active={state.category === id}
            onClick={() => actions.setCategory(id)}
          >
            {S.categories[id]}
          </Chip>
        ))}
      </ChipRow>

      {results.length === 0 ? (
        <div className="pt-6">
          <EmptyState
            title={S.search.empty}
            body={S.search.emptyBody}
            ctaLabel={S.feed.emptyCta}
            onCta={() => {
              setQuery("");
              actions.setCategory("all");
            }}
            testId="search-empty"
          />
        </div>
      ) : (
        <div className="space-y-3 px-4 pt-4">
          {results.map((market) => (
            <MarketCard
              key={market.id}
              market={market}
              variant="compact"
              onOpen={actions.openMarket}
            />
          ))}
        </div>
      )}
    </div>
  );
}
