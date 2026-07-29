import * as React from "react";
import type { Market } from "@/domain/types";
import { CategoryBadge } from "@/components/ui/CategoryBadge";
import { Badge } from "@/components/ui/badge";
import { EscudoOutcome } from "@/components/ui/EscudoOutcome";
import { cn } from "@/lib/cn";
import { S } from "@/lib/strings";
import { pct } from "@/lib/format";
import { formatStake } from "@/lib/units";
import { esVivo } from "@/domain/live";
import { hasEdge } from "@/domain/edge";
import { BINARY_OUTCOMES, rankedOutcomes } from "@/domain/parimutuel";

/** Cuántos destacados. Menos de tres no es un carrusel; más de cinco no se ve. */
export const MAX_DESTACADOS = 5;

/**
 * Los destacados, por orden de por qué destacan.
 *
 * No es "los de más pozo": un feed que abre con los cinco mercados más grandes
 * abre igual todos los días. El orden mezcla urgencia (lo que se define hoy),
 * tracción (HOT) y desacuerdo con otra casa (Edge), y desempata por pozo.
 */
export function destacados(markets: Market[], ahora: number = Date.now()): Market[] {
  const puntua = (m: Market) =>
    (m.status === "live" ? 8 : 0) +
    (esVivo(m, ahora) ? 4 : 0) +
    (m.hot ? 2 : 0) +
    (hasEdge(m) ? 1 : 0);

  const candidatos = markets
    .filter((m) => puntua(m) > 0)
    .sort((a, b) => puntua(b) - puntua(a) || b.volume - a.volume);

  /**
   * Como mucho dos por categoría.
   *
   * Sin este tope, una jornada de Liga MX llenaba los cinco huecos con cinco
   * partidos: el carrusel decía "hay futbol" cinco veces y no decía que
   * también hay cripto y economía. La urgencia manda en el orden, pero cinco
   * urgencias del mismo tema son una sola noticia repetida.
   */
  const porCategoria = new Map();
  const elegidos = [];
  for (const market of candidatos) {
    const usados = porCategoria.get(market.category) ?? 0;
    if (usados >= 2) continue;
    porCategoria.set(market.category, usados + 1);
    elegidos.push(market);
    if (elegidos.length === MAX_DESTACADOS) break;
  }
  // si el catálogo entero es de un tema, mejor repetir que enseñar un hueco
  if (elegidos.length < Math.min(MAX_DESTACADOS, candidatos.length)) {
    for (const market of candidatos) {
      if (elegidos.length === MAX_DESTACADOS) break;
      if (!elegidos.includes(market)) elegidos.push(market);
    }
  }
  return elegidos;
}

/**
 * Carrusel de destacados.
 *
 * Existe porque la primera pantalla decidía todo con una lista: honesta y
 * fría. Un producto que se abre a diario necesita algo que cambie al abrirlo,
 * y esto es lo que cambia.
 *
 * El scroll es nativo con `scroll-snap`: sin librería, sin listener de
 * arrastre y con el gesto que el teléfono ya sabe hacer. Los puntos se leen
 * del `scrollLeft`, así que nunca se desincronizan del contenido — no hay dos
 * fuentes de verdad para "en cuál voy".
 */
export function FeaturedCarousel({
  markets,
  onOpen,
}: {
  markets: Market[];
  onOpen: (market: Market) => void;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [activo, setActivo] = React.useState(0);

  const alScroll = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const primera = el.firstElementChild as HTMLElement | null;
    if (!primera) return;
    // el paso es el ancho de una pieza más su hueco, medido del DOM y no
    // asumido: si el ancho cambia con el viewport, el punto sigue acertando
    const paso = primera.getBoundingClientRect().width + 8;
    setActivo(Math.min(markets.length - 1, Math.round(el.scrollLeft / paso)));
  }, [markets.length]);

  if (markets.length === 0) return null;

  return (
    <section
      aria-label={S.feed.destacados}
      data-testid="featured-carousel"
      className="pt-2"
    >
      <div
        ref={ref}
        onScroll={alScroll}
        className="flex snap-x snap-mandatory gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {markets.map((market) => (
          <FeaturedCard key={market.id} market={market} onOpen={onOpen} />
        ))}
      </div>

      {markets.length > 1 ? (
        <div
          aria-hidden
          data-testid="featured-dots"
          className="flex justify-center gap-1.5 pt-1.5"
        >
          {markets.map((market, i) => (
            <span
              key={market.id}
              className={cn(
                "h-1.5 rounded-pill transition-all",
                // el activo es más ancho además de más claro: el estado no
                // depende sólo del color (R-005)
                i === activo ? "w-4 bg-teal" : "w-1.5 bg-line2",
              )}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function FeaturedCard({
  market,
  onOpen,
}: {
  market: Market;
  onOpen: (market: Market) => void;
}) {
  const pool = market.pool;
  const [lider] = pool
    ? rankedOutcomes(pool, market.outcomes ?? [...BINARY_OUTCOMES])
    : [];

  return (
    <button
      type="button"
      onClick={() => onOpen(market)}
      aria-label={`${S.market.openDetail}: ${market.title}`}
      // `data-testid` propio a propósito: la puerta de densidad mide el ritmo
      // de la lista, y una pieza del carrusel entrando en esa cuenta la
      // falsearía (scripts/densidad.mjs)
      data-testid="featured-card"
      data-market-id={market.id}
      className="flex w-[78%] shrink-0 snap-start flex-col gap-1.5 rounded-card border border-line2 bg-panel px-3.5 py-3 text-left shadow-card"
    >
      <span className="flex items-center gap-1.5">
        <CategoryBadge category={market.category} />
        {market.status === "live" ? (
          <Badge tone="live" dot>
            {S.badges.live}
          </Badge>
        ) : market.hot ? (
          <Badge tone="hot">{S.badges.hot}</Badge>
        ) : null}
      </span>

      {/* alto fijo de dos líneas: con `mt-auto` las piezas de título corto
          abrían un hueco de 20 px antes del número y la banda entera crecía
          para acomodar la más alta. Dos líneas reservadas siempre y todas las
          piezas miden igual */}
      <span className="line-clamp-2 h-[38px] font-display text-[15px] font-semibold leading-[19px] text-text">
        {market.title}
      </span>

      <span className="flex items-baseline gap-1.5">
        <span className="font-display text-[28px] font-semibold leading-none tabular-nums text-text">
          {pct(lider ? lider.probability : market.probability)}
          <span className="ml-0.5 align-top text-[0.4em] font-bold text-text2">%</span>
        </span>
        <EscudoOutcome market={market} label={lider?.label} className="self-center" />
        <span className="min-w-0 truncate text-[12px] font-semibold text-text2">
          {lider?.label ?? S.market.yes}
        </span>
      </span>

      <span className="truncate text-[11px] leading-tight text-muted">
        {S.market.pot} {formatStake(market.volume)}
      </span>
    </button>
  );
}
