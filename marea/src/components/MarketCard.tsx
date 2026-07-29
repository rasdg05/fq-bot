import * as React from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import type { Market } from "@/domain/types";
import { formatEdgePp, hasEdge } from "@/domain/edge";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { CategoryBadge } from "@/components/ui/CategoryBadge";
import { EscudoOutcome } from "@/components/ui/EscudoOutcome";
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
          // el hueco entre filas baja de 4 a 2 px y el padding vertical de 10
          // a 8: la barra de reparto entra sin que la card crezca. Medido en
          // navegador real, no estimado (vault/CARD_SPEC.md)
          "flex w-full flex-col gap-[2px] text-left",
          compact ? "min-h-touch px-3.5 py-2" : "px-3.5 py-2",
        )}
      >
        {/* Fila 1. La categoría abrió la fila y dejó de ser un punto de 6 px
            en `muted` a la derecha: es lo que da color al feed. LIVE va junto
            a ella porque las dos responden "¿qué es esto y corre prisa?".
            Como mucho tres piezas: la cuarta hace envolver la fila a 320 px */}
        <div className="flex items-center gap-1.5">
          <CategoryBadge category={market.category} />
          {market.status === "live" ? (
            <Badge tone="live" dot>
              {S.badges.live}
            </Badge>
          ) : null}
          {market.hot ? <Badge tone="hot">{S.badges.hot}</Badge> : null}
          {/* el país dice más que "LATAM" cuando todo el catálogo es de Latam.
              Va al final y se va primero: es la pieza que menos decide */}
          {market.country || market.region === "latam" ? (
            <Badge tone="latam" className="ml-auto hidden angosto:inline-flex">
              {market.country ?? S.badges.latam}
            </Badge>
          ) : null}
        </div>

        {/* `leading-tight` daba 22.5 px por línea medidos, no los 18.75 que
            promete el 1.25: dentro de un `-webkit-box` el interlineado se
            resuelve contra las métricas de la serif, no contra el múltiplo.
            Se declara en píxeles y se acabó la sorpresa: 19 px por línea */}
        <h3
          className={cn(
            "font-display font-semibold text-text",
            compact
              ? "line-clamp-1 text-[14px] leading-[18px]"
              : "line-clamp-2 text-[15px] leading-[19px]",
          )}
        >
          {market.title}
        </h3>

        {/* fila de decisión: los dos resultados más probables, cada uno en
            UNA línea. Se corta la etiqueta con elipsis antes que envolver —
            comprimir no es amputar: el número y el lado nunca se tocan
            (R-063, vault/CARD_SPEC.md) */}
        {/* `flex-wrap` para el texto agrandado: a 200 % la elipsis se comía la
            etiqueta entera ("Gana el A…" en 18 px de ancho), y una etiqueta que
            no se lee es lo mismo que no mostrarla. A tamaño normal no envuelve
            —cabe de sobra— así que la densidad no paga nada por esto.
            El mínimo va en `rem`: a 200 % vale 272 px, los dos grupos dejan de
            caber en una línea y la fila se parte sola. Es la misma regla
            resolviendo los dos casos, no un caso especial */}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <div
            data-dominant="probability"
            className="flex min-w-[8.5rem] flex-[1.25] items-baseline gap-1"
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
            <EscudoOutcome market={market} label={lider?.label} />
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
              className="flex min-w-[8.5rem] flex-1 items-baseline justify-end gap-1"
            >
              <span className="shrink-0 font-display text-[20px] font-semibold tabular-nums text-text2">
                {pct(rival.probability)}
                <span className="ml-0.5 align-top text-[0.4em] font-bold text-muted">
                  %
                </span>
              </span>
              <EscudoOutcome market={market} label={rival.label} />
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

        {/* La barra de reparto. Una sola barra, no una por resultado: lo que
            se lee de un vistazo es la proporción entre los dos lados, y dos
            barras apiladas cuestan el doble de alto para decir lo mismo.
            3 px de alto — es refuerzo del número, no su sustituto: los
            porcentajes ya están arriba, así que la barra no carga información
            que no esté escrita (R-005) */}
        {pool && lider ? (
          <div
            aria-hidden
            data-testid="card-reparto"
            className="flex h-[3px] w-full gap-px overflow-hidden rounded-pill bg-panel2"
          >
            <span
              className="h-full rounded-pill"
              style={{
                width: `${Math.round(lider.probability * 100)}%`,
                backgroundColor: "var(--teal)",
              }}
            />
            {rival ? (
              <span
                className="h-full rounded-pill"
                style={{
                  width: `${Math.round(rival.probability * 100)}%`,
                  backgroundColor: "var(--muted)",
                }}
              />
            ) : null}
          </div>
        ) : null}

        {/* meta en una sola línea: la `d` huérfana de "Cierra en 4 d" salía de
            dejar que este nodo envolviera */}
        <span className="block truncate text-[11px] leading-tight text-muted">
          {pool ? `${S.market.pot} ${formatStake(market.volume)}` : compactUsd(market.volume)}
          {/* cuánta gente hay dentro: es lo que dice si el mercado está vivo */}
          {market.participantes ? ` · ${S.market.participantes(market.participantes)}` : ""}
          {closes ? ` · ${S.market.closes} ${closes}` : ` · ${S.badges.closed}`}
        </span>
      </button>
    </Card>
  );
}
