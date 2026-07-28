import * as React from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import type { Market } from "@/domain/types";
import { formatEdgePp, hasEdge } from "@/domain/edge";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { compactUsd, pct, closesIn } from "@/lib/format";
import {
  BINARY_OUTCOMES,
  formatMultiplier,
  payoutMultiplier,
  rankedOutcomes,
} from "@/domain/parimutuel";

export type MarketCardVariant = "default" | "edge" | "live" | "compact";

/** Resuelve la variante desde el dato cuando no se fuerza desde la vista. */
export function resolveVariant(market: Market): MarketCardVariant {
  if (market.status === "live") return "live";
  if (hasEdge(market)) return "edge";
  return "default";
}

export interface MarketCardProps {
  market: Market;
  variant?: MarketCardVariant;
  onOpen: (market: Market) => void;
}

/**
 * Card híbrida: descubrimiento tipo Polymarket con la probabilidad como número
 * rey tipo Kalshi. La probabilidad es el único nodo en escala `text-prob`
 * (R-004); el Edge es el segundo ancla y sólo aparece si el dominio lo permite
 * (R-001). Toda la card es un solo target táctil.
 */
export function MarketCard({ market, variant, onOpen }: MarketCardProps) {
  const resolved = variant ?? resolveVariant(market);
  const compact = resolved === "compact";
  const showEdge = hasEdge(market) && market.edge !== null;
  const closes = closesIn(market.closesAt);
  // en mercado propio lo que importa es cuánto paga, no cuánto se ha operado
  const pool = market.pool;
  // los dos resultados con más pozo, sean "Sí/No" o dos de siete candidatos
  const ranked = pool
    ? rankedOutcomes(pool, market.outcomes ?? [...BINARY_OUTCOMES])
    : [];
  const [lider, rival] = ranked;

  const handleOpen = React.useCallback(() => onOpen(market), [onOpen, market]);

  return (
    <Card
      className={cn(
        "overflow-hidden transition-colors",
        // sólo el Edge se gana un borde: es el diferenciador. LIVE ya se lee en
        // su badge y un borde rojo entero le robaba jerarquía (R-004)
        resolved === "edge" && "border-teal",
      )}
      data-testid="market-card"
      data-variant={resolved}
      data-market-id={market.id}
      data-has-edge={showEdge ? "true" : "false"}
    >
      <button
        type="button"
        onClick={handleOpen}
        aria-label={`${S.market.openDetail}: ${market.title}`}
        className={cn(
          "flex w-full flex-col gap-1 text-left",
          compact ? "min-h-touch px-3.5 py-2" : "px-3.5 py-2.5",
        )}
      >
        <div className="flex items-center gap-1.5">
          {market.status === "live" ? (
            <Badge tone="live" dot>
              {S.badges.live}
            </Badge>
          ) : null}
          {market.hot ? <Badge tone="hot">{S.badges.hot}</Badge> : null}
          {/* el país dice más que "LATAM" cuando todo el catálogo es de Latam */}
          {market.country || market.region === "latam" ? (
            <Badge tone="latam">{market.country ?? S.badges.latam}</Badge>
          ) : null}
          <span className="ml-auto shrink-0 text-[11px] font-medium text-muted">
            {S.categories[market.category]}
          </span>
        </div>

        <h3
          className={cn(
            "font-display font-semibold leading-tight text-text",
            compact ? "line-clamp-1 text-[14px]" : "line-clamp-2 text-[15px]",
          )}
        >
          {market.title}
        </h3>

        {/* fila de decisión: los dos resultados más probables, cada uno en
            UNA línea. Se corta la etiqueta con elipsis antes que envolver —
            comprimir no es amputar: el número y el lado nunca se tocan
            (R-063, vault/CARD_SPEC.md) */}
        <div className="flex items-center gap-2.5">
          <div
            data-dominant="probability"
            className="flex min-w-0 flex-[1.25] items-baseline gap-1"
          >
            <span
              data-role="probability"
              className={cn(
                "shrink-0 font-display font-semibold tabular-nums text-text",
                compact ? "text-prob-sm" : "text-prob",
              )}
            >
              {/* el porcentaje es el del resultado que se nombra al lado, no el
                  del Sí. Pintar P(sí) junto a la etiqueta "No" enseñaba 33 %
                  donde el pago era de lado gordo: el número que se muestra
                  tiene que ser del lado que dice ser (I3) */}
              {pct(lider ? lider.probability : market.probability)}
              <span className="ml-0.5 align-top text-[0.4em] font-bold text-text2">
                %
              </span>
            </span>
            <span className="min-w-0 truncate text-[12px] font-semibold text-text2">
              {pool ? (lider?.label ?? S.market.yes) : S.market.probability}
            </span>
            {pool ? (
              <span className="shrink-0 font-mono text-[12px] font-semibold tabular-nums text-muted">
                {formatMultiplier(
                  lider ? lider.multiplier : payoutMultiplier(pool, "si"),
                )}
              </span>
            ) : null}
          </div>

          {/* el contrincante: en binario el No, con N respuestas la segunda */}
          {pool && rival ? (
            <div
              data-testid="card-other-side"
              className="flex min-w-0 flex-1 items-baseline justify-end gap-1"
            >
              <span className="shrink-0 font-display text-[20px] font-semibold tabular-nums text-text2">
                {pct(rival.probability)}
                <span className="ml-0.5 align-top text-[0.4em] font-bold text-muted">
                  %
                </span>
              </span>
              <span className="min-w-0 truncate text-[12px] font-semibold text-text2">
                {rival.label}
              </span>
              <span className="shrink-0 font-mono text-[12px] font-semibold tabular-nums text-muted">
                {formatMultiplier(rival.multiplier)}
              </span>
            </div>
          ) : null}

          {showEdge ? (
            <Badge
              tone="edge"
              className="shrink-0"
              data-testid="edge-badge"
              data-edge-pp={market.edge as number}
            >
              {/* el icono sigue el signo: un Edge negativo no apunta hacia arriba */}
              {(market.edge as number) > 0 ? (
                <TrendingUp aria-hidden className="h-3 w-3" />
              ) : (
                <TrendingDown aria-hidden className="h-3 w-3" />
              )}
              {/* la lectura puede no ser nuestra: se nombra quien la da (R-027) */}
              {S.market.edgeCardWith(
                market.edgeLabel ?? S.market.mareaProbability,
                formatEdgePp(market.edge as number),
              )}
            </Badge>
          ) : null}
        </div>

        {/* meta en una sola línea: la `d` huérfana de "Cierra en 4 d" salía de
            dejar que este nodo envolviera */}
        <span className="block truncate text-[11px] leading-tight text-muted">
          {pool ? `${S.market.pot} ${formatStake(market.volume)}` : compactUsd(market.volume)}
          {closes ? ` · ${S.market.closes} ${closes}` : ` · ${S.badges.closed}`}
        </span>
      </button>
    </Card>
  );
}
