import * as React from "react";
import type { Market, MarketCategory } from "@/domain/types";
import { MarketCard } from "@/components/MarketCard";
import { FeaturedCarousel, destacados } from "@/components/FeaturedCarousel";
import { Chip, ChipRow } from "@/components/ui/chip";
import { SectionHeader } from "@/components/ui/SectionHeader";
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

/**
 * Home. Un solo trabajo: descubrir.
 *
 * Arriba, los destacados en carrusel: es lo que cambia al abrir la app, y sin
 * eso la primera pantalla era una lista honesta y fría. Debajo, el feed
 * agrupado por categoría con encabezados que filtran.
 *
 * La agrupación sustituye al par `Hot ahora` / `Todos los mercados`. Aquel
 * corte separaba lo caliente de lo demás, que es una sola pregunta contestada;
 * agrupar por tema contesta la que de verdad se hace al abrir el feed —"¿de
 * qué hay?"— sin obligar a leer la marca de cada card para saber de qué va el
 * bloque. Lo caliente no se pierde: sube al carrusel, que es donde se mira
 * primero.
 *
 * Con un filtro puesto no hay ni carrusel ni agrupación: quien ya eligió
 * `Cripto` no necesita que se lo repitan seis veces.
 *
 * Los cuatro estados del listado son excluyentes: nunca se montan dos a la
 * vez (R-014).
 */
export function HomeScreen() {
  const { state, actions } = useApp();
  const { markets, category } = state;

  React.useEffect(() => {
    if (markets.status === "loading") void actions.loadMarkets();
    // ¿hay sesión viva? Si la hay, el saldo y las posiciones vuelven solos
    void actions.cargarCuenta();
    // sólo al montar: el feed no se recarga solo al cambiar de filtro
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const all = markets.status === "data" ? markets.data : [];
  const filtered = React.useMemo(
    () => (category === "all" ? all : all.filter((m) => m.category === category)),
    [all, category],
  );
  const featured = React.useMemo(
    () => (category === "all" ? destacados(all) : []),
    [all, category],
  );
  /** Los bloques del feed, en el orden en que están declaradas las categorías. */
  const grupos = React.useMemo(() => {
    if (category !== "all") return [];
    return CATEGORIES.map((id) => ({
      id,
      mercados: filtered.filter((m) => m.category === id),
    })).filter((grupo) => grupo.mercados.length > 0);
  }, [filtered, category]);

  /**
   * El pulso de las velas sólo corre si hay velas en pantalla, y se apaga al
   * salir. Un reloj de tres segundos que sigue latiendo en una pantalla sin
   * nada vivo es batería de alguien gastada en nada.
   */
  const hayVelas = all.some((market) => market.live);
  React.useEffect(() => {
    if (!hayVelas) return;
    return actions.seguirVivos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hayVelas]);

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
      {/* lo último que se cargó se sigue viendo, dicho en voz alta. Mostrarlo
          como fresco sería mentir; esconderlo sería dejar la pantalla vacía */}
      {state.datosViejos ? (
        <div
          data-testid="datos-viejos"
          role="status"
          className="mx-4 mt-2 flex items-center justify-between gap-3 rounded-card border border-line2 bg-panel px-3 py-2"
        >
          <span className="text-[12px] leading-snug text-text2">
            {S.frescura.viejo}
          </span>
          <button
            type="button"
            data-testid="datos-viejos-reintentar"
            onClick={() => void actions.loadMarkets()}
            className="min-h-touch shrink-0 px-2 text-[13px] font-semibold text-teal"
          >
            {S.frescura.reintentar}
          </button>
        </div>
      ) : null}

      <ChipRow className="pt-2" aria-label={S.search.byCategory}>
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

      {featured.length > 0 ? (
        <FeaturedCarousel markets={featured} onOpen={actions.openMarket} />
      ) : null}

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
      ) : category === "all" ? (
        grupos.map((grupo) => (
          <Bloque
            key={grupo.id}
            titulo={S.categories[grupo.id]}
            mercados={grupo.mercados}
            onOpen={() => actions.setCategory(grupo.id)}
          />
        ))
      ) : (
        <Bloque titulo={S.categories[category]} mercados={filtered} />
      )}
    </div>
  );
}

function Bloque({
  titulo,
  mercados,
  onOpen,
}: {
  titulo: string;
  mercados: Market[];
  onOpen?: () => void;
}) {
  const { state, actions } = useApp();
  return (
    <section className="pt-3">
      <SectionHeader titulo={titulo} cuenta={mercados.length} onOpen={onOpen} />
      <div className="space-y-2 px-4">
        {mercados.map((market) => (
          <MarketCard
            key={market.id}
            market={market}
            // el latido de la vela viaja hasta la card: sin esto una card de
            // cripto en vivo se queda congelada en el precio de su primer render
            pulso={state.vivos[market.id]}
            onOpen={actions.openMarket}
          />
        ))}
      </div>
    </section>
  );
}
