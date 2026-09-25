import * as React from "react";
import type { Market } from "@/domain/types";
import { MarketCard } from "@/components/MarketCard";
import { CarruselDestacados } from "@/components/CarruselDestacados";
import { Chip, ChipRow } from "@/components/ui/chip";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { useApp } from "@/state/store";
import { hasEdge } from "@/domain/edge";
import { CATEGORIAS_VISIBLES, COLOR_CATEGORIA, ICONO_CATEGORIA } from "@/lib/categoria";
import { FRESCURA_SALDO_MS } from "@/domain/saldo";

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
    // ¿hay sesión viva? Si la hay, el saldo y las posiciones vuelven solos
    void actions.cargarCuenta(FRESCURA_SALDO_MS);
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
        {CATEGORIAS_VISIBLES.map((id) => (
          <Chip
            key={id}
            active={category === id}
            color={COLOR_CATEGORIA[id]}
            icon={ICONO_CATEGORIA[id]}
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
            <section aria-labelledby="hot-heading" className="pt-2">
              {/* el encabezado se queda para el lector de pantalla y se va de
                  la pantalla: el badge HOT de cada card ya dice lo mismo, y
                  36 px de cromo son un quinto de un mercado */}
              <h2 id="hot-heading" className="sr-only">
                {S.feed.hotNow}
              </h2>
              {/* en horizontal: los mismos mercados calientes, sin empujar el
                  resto del catálogo fuera de la primera pantalla */}
              <CarruselDestacados
                markets={hot}
                vivos={state.vivos}
                onOpen={actions.openMarket}
                etiqueta={S.feed.hotNow}
              />
            </section>
          ) : null}

          {rest.length > 0 ? (
            <section aria-labelledby="all-heading" className="pt-5">
              <h2 id="all-heading" className="sr-only">
                {S.feed.sectionAll}
              </h2>
              {/* por secciones: con setenta mercados, una lista plana obliga a
                  leer cada título para saber de qué va. Agrupados por liga o
                  categoría, el ojo salta a lo suyo */}
              <div className="space-y-6">
                {agrupar(rest).map((grupo) => (
                  <SeccionMercados
                    key={grupo.clave}
                    grupo={grupo}
                    renderCard={(market) => (
                      <MarketCard
                        key={market.id}
                        market={market}
                        pulso={state.vivos[market.id]}
                        onOpen={actions.openMarket}
                      />
                    )}
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

interface Grupo {
  clave: string;
  titulo: string;
  categoria: Market["category"];
  markets: Market[];
}

/**
 * Agrupa por liga (deportes) o por categoría (lo demás). El orden de las
 * secciones sigue al de las pestañas, y dentro de deportes manda la liga con
 * más partidos: es la que más se está jugando.
 */
function agrupar(markets: Market[]): Grupo[] {
  const grupos = new Map<string, Grupo>();
  for (const market of markets) {
    const clave = market.liga ?? market.category;
    const grupo = grupos.get(clave) ?? {
      clave,
      titulo: market.liga ?? S.categories[market.category],
      categoria: market.category,
      markets: [],
    };
    grupo.markets.push(market);
    grupos.set(clave, grupo);
  }
  const orden = (categoria: Market["category"]) => {
    const i = CATEGORIAS_VISIBLES.indexOf(categoria);
    return i === -1 ? CATEGORIAS_VISIBLES.length : i;
  };
  return [...grupos.values()].sort(
    (a, b) =>
      orden(a.categoria) - orden(b.categoria) ||
      b.markets.length - a.markets.length ||
      a.titulo.localeCompare(b.titulo, "es"),
  );
}

/** Cuántas cards se ven de entrada por sección. El resto, a un toque. */
const VISIBLES_POR_SECCION = 4;

function SeccionMercados({
  grupo,
  renderCard,
}: {
  grupo: Grupo;
  renderCard: (market: Market) => React.ReactNode;
}) {
  const [abierta, setAbierta] = React.useState(false);
  const color = COLOR_CATEGORIA[grupo.categoria];
  const Icono = ICONO_CATEGORIA[grupo.categoria];
  const ocultas = grupo.markets.length - VISIBLES_POR_SECCION;
  const visibles = abierta ? grupo.markets : grupo.markets.slice(0, VISIBLES_POR_SECCION);

  return (
    <div data-testid="seccion-mercados" data-seccion={grupo.clave}>
      <div className="flex items-center gap-2.5 px-4 pb-2.5">
        <span
          aria-hidden
          className="grid h-7 w-7 place-items-center rounded-[9px]"
          style={{ backgroundColor: `color-mix(in srgb, ${color} 20%, transparent)` }}
        >
          <Icono className="h-4 w-4" style={{ color }} strokeWidth={2.4} />
        </span>
        <h3 className="font-display text-[19px] font-semibold tracking-[-0.01em] text-text">
          {grupo.titulo}
        </h3>
        <span className="ml-auto text-[12px] font-medium text-muted">
          {S.feed.cuantos(grupo.markets.length)}
        </span>
      </div>
      <div className="space-y-2 px-4">{visibles.map(renderCard)}</div>
      {ocultas > 0 ? (
        <div className="px-4 pt-2">
          <button
            type="button"
            data-testid="seccion-ver-mas"
            onClick={() => setAbierta((valor) => !valor)}
            className="min-h-touch w-full rounded-ctl border border-line2 bg-panel text-[14px] font-semibold text-teal transition-colors hover:bg-panel2"
          >
            {abierta ? S.feed.verMenos : S.feed.verMas(ocultas)}
          </button>
        </div>
      ) : null}
    </div>
  );
}
