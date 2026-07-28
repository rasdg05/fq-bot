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
import { formatMultiplier, payoutMultiplier } from "@/domain/parimutuel";

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
          "flex w-full flex-col gap-3 text-left",
          compact ? "min-h-touch p-3" : "p-4",
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
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
          <span className="ml-auto text-[12px] font-medium text-muted">
            {S.categories[market.category]}
          </span>
        </div>

        <h3
          className={cn(
            "font-display font-semibold leading-snug text-text",
            compact ? "line-clamp-1 text-[15px]" : "line-clamp-2 text-[17px]",
          )}
        >
          {market.title}
        </h3>

        <div className="flex items-end justify-between gap-3">
          {/* nodo dominante: la probabilidad (R-004) */}
          <div data-dominant="probability">
            <div
              data-role="probability"
              className={cn(
                "font-display font-semibold tabular-nums text-text",
                compact ? "text-prob-sm" : "text-prob",
              )}
            >
              {pct(market.probability)}
              <span className="ml-0.5 align-top text-[0.42em] font-bold text-text2">
                %
              </span>
            </div>
            {/* los dos lados, con su pago. Enseñar sólo uno es enseñar medio
                mercado: quien apuesta necesita ver contra qué apuesta (R-063) */}
            <div className="mt-0.5 text-[12px] font-medium text-muted">
              {pool
                ? `${S.market.yes} · ${S.market.pays} ${formatMultiplier(
                    payoutMultiplier(pool, "si"),
                  )}`
                : S.market.probability}
            </div>
          </div>

          {pool ? (
            <div className="text-right" data-testid="card-other-side">
              <div className="font-display text-[22px] font-semibold tabular-nums text-text2">
                {pct(1 - market.probability)}
                <span className="ml-0.5 align-top text-[0.42em] font-bold text-muted">
                  %
                </span>
              </div>
              <div className="mt-0.5 text-[12px] font-medium text-muted">
                {S.market.no} · {S.market.pays}{" "}
                {formatMultiplier(payoutMultiplier(pool, "no"))}
              </div>
            </div>
          ) : null}

          <div className="flex flex-col items-end gap-1.5">
            {showEdge ? (
              <Badge
                tone="edge"
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
            <span className="text-[12px] text-muted">
              {pool ? `${S.market.pot} ${formatStake(market.volume)}` : compactUsd(market.volume)}
              {closes
                ? ` · ${S.market.closes} ${closes}`
                : ` · ${S.badges.closed}`}
            </span>
          </div>
        </div>
      </button>
    </Card>
  );
}
