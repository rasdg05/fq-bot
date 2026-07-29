import * as React from "react";
import type { LiveCandle, Market, PulsoVivo } from "@/domain/types";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { CategoriaIcono } from "@/components/ui/categoria-icono";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { pct } from "@/lib/format";
import { cuentaRegresiva, UMBRAL_ANIMACION_PP } from "@/domain/vela";
import {
  BINARY_OUTCOMES,
  formatMultiplier,
  payoutMultiplier,
  probabilities,
  type Outcome,
} from "@/domain/parimutuel";

/**
 * Card de cripto en vivo.
 *
 * Es una card aparte y no una variante más de `MarketCard` a propósito: la card
 * normal está cerrada (densidad, tipografía del %, resultados nombrados) y lo
 * que necesita una vela de cinco minutos —reloj, precio que se mueve, congelado
 * al tocar— no cabía sin reabrirla. Aquí abajo no hay ninguna regla nueva de
 * marca: los mismos tokens, el mismo mínimo táctil y **el mismo alto que la
 * card normal**, que es lo que mide `npm run densidad` contra el esqueleto del
 * feed. Desde que lo vivo va arriba, la primera card del feed es ésta.
 *
 * Tres cosas que sostienen el resto:
 *
 *  1. **El reloj es local.** La cuenta regresiva corre en el dispositivo contra
 *     la hora de cierre que vino con el mercado. Si la red se cae, el reloj
 *     sigue siendo cierto; esperar al servidor para descontar un segundo sería
 *     fabricar un parpadeo cada tres segundos.
 *  2. **El congelado es sagrado.** Con el dedo sobre una pill, los números
 *     dejan de moverse. Es la diferencia entre elegir un lado y que el lado se
 *     te mueva mientras lo tocas.
 *  3. **Sin precio fresco se enseña ausencia.** El ticker declara su frescura;
 *     cuando no hay lectura, la card dice que no hay, no repite la última
 *     (R-022).
 */

/** Cuánto se queda congelada la card después de soltar. */
const CONGELADO_MS = 4_000;

/** Un reloj local, que late una vez por segundo y no depende de la red. */
function useReloj(activo: boolean): number {
  const [ahora, setAhora] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!activo) return;
    const id = setInterval(() => setAhora(Date.now()), 1_000);
    return () => clearInterval(id);
  }, [activo]);
  return ahora;
}

/**
 * Congela lo que llega mientras el dedo está encima, y un rato después de
 * soltar. Devuelve el último valor que se dejó pasar.
 */
function useCongelado<T>(valor: T, congelado: boolean): T {
  const guardado = React.useRef(valor);
  if (!congelado) guardado.current = valor;
  return guardado.current;
}

function precioLegible(valor: number): string {
  return valor.toLocaleString("es-MX", {
    minimumFractionDigits: valor >= 1_000 ? 0 : 2,
    maximumFractionDigits: valor >= 1_000 ? 0 : 2,
  });
}

function deltaLegible(pp: number): string {
  const signo = pp > 0 ? "+" : pp < 0 ? "−" : "";
  return `${signo}${Math.abs(pp).toFixed(2)}%`;
}

interface Lado extends Outcome {
  probability: number;
  multiplier: number;
  /** Cuál va ganando. Decide qué pill va rellena, nunca el orden en pantalla. */
  lider?: boolean;
}

/**
 * Los dos lados, **en el orden en que los declaró el mercado**. No se ordenan
 * por probabilidad: en una vela los lados se cruzan cada pocos segundos, y unas
 * pills que se intercambian de sitio bajo el dedo son la forma más directa de
 * que alguien apueste a lo que no quería (R-063).
 */
/**
 * Marca cuál de los dos lados va ganando. Es lo que decide qué pill va rellena:
 * en el feed hay una sola pill pintada por card, y aquí no puede ser distinto.
 * Con empate exacto manda el primero, que es el orden en que los declaró el
 * mercado — un desempate arbitrario, pero estable.
 */
function conLider(lados: Lado[]): Lado[] {
  const mayor = Math.max(...lados.map((lado) => lado.probability));
  let yaHay = false;
  return lados.map((lado) => {
    const lider = !yaHay && lado.probability === mayor;
    if (lider) yaHay = true;
    return { ...lado, lider };
  });
}

function ladosDe(market: Market, pulso?: PulsoVivo): Lado[] {
  const outcomes = market.outcomes ?? [...BINARY_OUTCOMES];
  if (pulso) {
    return conLider(
      outcomes.map((outcome) => ({
        ...outcome,
        probability: pulso.probabilidades[outcome.id] ?? 0,
        multiplier: pulso.multiplicadores[outcome.id] ?? 0,
      })),
    );
  }
  const pool = market.pool;
  if (!pool) {
    return conLider(outcomes.map((o) => ({ ...o, probability: 0, multiplier: 0 })));
  }
  const probs = probabilities(pool);
  return conLider(
    outcomes.map((outcome) => ({
      ...outcome,
      probability: probs[outcome.id] ?? 0,
      multiplier: payoutMultiplier(pool, outcome.id),
    })),
  );
}

/**
 * El porcentaje de un lado. Sólo transiciona cuando el salto vale la pena: por
 * debajo de medio punto el número cambia seco. Una card que se anima cada dos
 * segundos por dos décimas es ruido con forma de información.
 *
 * Con `prefers-reduced-motion` el bloque global de tokens.css apaga la
 * transición entera, así que esto ni se nota.
 */
function Porcentaje({ probability, lider }: { probability: number; lider?: boolean }) {
  const anterior = React.useRef(probability);
  const salto = Math.abs(probability - anterior.current) * 100;
  const anima = salto >= UMBRAL_ANIMACION_PP;
  React.useEffect(() => {
    anterior.current = probability;
  }, [probability]);

  return (
    <span
      data-role="probability"
      data-anima={anima ? "true" : "false"}
      className={cn(
        // el tamaño va **después** del color: `twMerge` mete `text-prob-sm` y
        // `text-text` en el mismo grupo `text-*` y se queda con el último. Con
        // el orden al revés, el porcentaje salía en 16 px y la puerta de
        // densidad lo cazaba como jerarquía degradada (R-004)
        "font-display tabular-nums",
        // el porcentaje sigue siendo el nodo dominante también aquí: la
        // densidad no se compra encogiéndolo. `npm run densidad` lo mide
        lider
          ? "text-prob-pill font-bold text-text"
          : "text-prob-riv font-semibold text-text2",
        anima && "transition-opacity duration-200",
      )}
    >
      {pct(probability)}
      <span className="ml-0.5 align-top text-[12px] font-bold opacity-70">%</span>
    </span>
  );
}

export interface CryptoLiveCardProps {
  market: Market & { live: LiveCandle };
  /** El último latido del servidor. Ausente = todavía no llegó ninguno. */
  pulso?: PulsoVivo;
  onOpen: (market: Market) => void;
}

export function CryptoLiveCard({ market, pulso, onOpen }: CryptoLiveCardProps) {
  const [congelado, setCongelado] = React.useState(false);
  const soltarRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(
    () => () => {
      if (soltarRef.current) clearTimeout(soltarRef.current);
    },
    [],
  );

  const tocar = React.useCallback(() => {
    if (soltarRef.current) clearTimeout(soltarRef.current);
    setCongelado(true);
  }, []);

  const soltar = React.useCallback(() => {
    if (soltarRef.current) clearTimeout(soltarRef.current);
    soltarRef.current = setTimeout(() => setCongelado(false), CONGELADO_MS);
  }, []);

  // el precio, el pozo y los porcentajes se congelan juntos: congelar sólo el
  // número grande dejaría el multiplicador moviéndose debajo del dedo
  const vivo = useCongelado(pulso, congelado);
  const lados = useCongelado(ladosDe(market, pulso), congelado);
  const vela = market.live;

  const ahora = useReloj(true);
  const restante = new Date(vela.bloqueaAt).getTime() - ahora;
  const cerrada = restante <= 0;
  const reloj = cuentaRegresiva(restante);

  const spot = vivo?.spot ?? vela.spot;
  const delta = vivo?.deltaPp ?? vela.deltaPp;
  const pozo = vivo?.pozo ?? market.volume;
  const jugando = vivo?.jugando ?? market.participantes ?? 0;

  const handleOpen = React.useCallback(() => onOpen(market), [onOpen, market]);

  return (
    <Card
      /**
       * Sin borde propio. El badge LIVE ya dice que esto está pasando, y un
       * borde de color entero le robaría jerarquía al único elemento que se
       * gana un borde en este producto, que es el Edge (R-004). Un token de
       * color tampoco admite modificador de opacidad: la declaración se
       * descarta y no se pinta nada (R-017).
       */
      className="overflow-hidden"
      data-testid="market-card"
      data-variant="live"
      data-market-id={market.id}
      data-has-edge="false"
      data-congelado={congelado ? "true" : "false"}
    >
      {/* la misma caja que la card normal: `npm run densidad` mide la primera
          card del feed contra el esqueleto, y desde que lo vivo va arriba, la
          primera card es ésta. Una card viva más baja que las demás sería un
          salto de layout cada vez que nace una vela */}
      <div className="flex flex-col gap-[3px] px-3.5 py-[9px]">
        {/* reloj. El countdown vive dentro del badge: es la misma información
            —esto está pasando y le queda esto— y separarla en dos nodos costaba
            una fila entera */}
        <div className="flex h-4 items-center gap-1.5">
          <CategoriaIcono categoria={market.category} />
          <span className="mr-auto shrink-0 text-[10px] font-bold uppercase tracking-[0.06em] text-muted">
            {S.categories[market.category]}
          </span>
          <Badge tone="live" dot data-testid="live-countdown">
            {S.badges.live}
            <span className="font-mono tabular-nums" aria-hidden>
              {cerrada ? S.vivo.cerrando : reloj}
            </span>
          </Badge>
        </div>

        {/* qué se está mirando y a cuánto va. El precio es mono y tabular: con
            proporcional, cada tick de dos segundos movía los dígitos de sitio */}
        <div className="flex h-5 items-center gap-2">
          <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-text2">
            {vela.activo} · {S.vivo.ventana(vela.intervalo)}
          </span>
          <span className="flex shrink-0 items-baseline gap-1.5">
            {spot !== undefined ? (
              <span
                data-testid="live-spot"
                className="font-mono text-[15px] font-semibold tabular-nums leading-none text-text"
              >
                {precioLegible(spot)}
              </span>
            ) : (
              /* sin lectura fresca se dice que no hay, en vez de repetir la
                 última: un precio viejo enseñado como de ahora es mentira con
                 forma de dato (R-022) */
              <span
                data-testid="live-sin-precio"
                className="text-[13px] font-semibold text-muted"
              >
                {S.vivo.sinPrecio}
              </span>
            )}
            {delta !== undefined ? (
              <span
                data-testid="live-delta"
                className={cn(
                  "font-mono text-[12px] font-semibold tabular-nums",
                  delta > 0 ? "text-up" : delta < 0 ? "text-dn" : "text-muted",
                )}
              >
                {deltaLegible(delta)}
              </span>
            ) : null}
          </span>
        </div>

        {/* la decisión: los dos lados nombrados, con su pago y su barra */}
        <div className="flex items-center gap-2" data-testid="live-pills">
          {lados.map((lado) => (
            <button
              key={lado.id}
              type="button"
              data-testid="live-pill"
              data-outcome-id={lado.id}
              onClick={handleOpen}
              onPointerDown={tocar}
              onPointerUp={soltar}
              onPointerCancel={soltar}
              onPointerLeave={soltar}
              aria-label={`${S.market.openDetail}: ${lado.label}, ${pct(
                lado.probability,
              )} %, ${S.vivo.paga(formatMultiplier(lado.multiplier))}`}
              className={cn(
                // el mismo lenguaje que la card normal: pill rellena para el
                // lado que va ganando, contorno para el otro, y el número
                // dentro. Dos maneras de pintar el mismo dato en un mismo feed
                // eran dos productos (§3.1 del rediseño)
                "group relative flex min-w-0 flex-1 items-center gap-2 text-left",
                // 36 px de pill, 44 de zona tocable: el aire de arriba y abajo
                // es parte del botón sin ocupar una fila (R-010)
                "after:absolute after:inset-x-0 after:-inset-y-1 after:content-['']",
              )}
            >
              <span
                data-role="pill"
                className={cn(
                  "flex h-9 min-w-[64px] shrink-0 items-center justify-center rounded-pill px-2.5",
                  "outline outline-2 outline-offset-2 outline-transparent",
                  "transition-[background-color,outline-color,transform] duration-[120ms] ease-out",
                  "group-focus-visible:outline-pill-ring group-active:scale-[.96]",
                  lado.lider
                    ? "bg-teal-soft ring-1 ring-pill-ring"
                    : "bg-pill-wash ring-1 ring-pill-line",
                )}
              >
                <Porcentaje probability={lado.probability} lider={lado.lider} />
              </span>
              <span className="flex min-w-0 flex-col whitespace-nowrap leading-none">
                <span className="truncate text-[13px] font-semibold leading-[15px] text-text2">
                  {lado.label}
                </span>
                <span className="mt-0.5 truncate font-mono text-mult font-medium tabular-nums text-muted">
                  {S.market.pays2(formatMultiplier(lado.multiplier))}
                </span>
              </span>
            </button>
          ))}
        </div>

        {/* una sola barra para los dos lados, igual que en la card normal:
            el líder en teal, el rival en muted, 2 px de separación */}
        <span
          aria-hidden
          data-testid="live-barra"
          className="flex h-[3px] w-full gap-0.5 overflow-hidden rounded-pill"
        >
          {lados.map((lado) => (
            <span
              key={lado.id}
              className={cn(
                "h-full rounded-pill transition-[width] duration-[240ms] ease-[cubic-bezier(.22,1,.36,1)]",
                lado.lider ? "bg-teal" : "bg-muted",
              )}
              style={{ width: `${Math.max(lado.probability * 100, 2)}%` }}
            />
          ))}
        </span>

        {/* pozo, gente y cuánto falta. La misma línea que la card normal, con
            el reloj en vez de la fecha: en una vela, "cierra en 4 d" no existe */}
        <span className="block truncate text-[11px] leading-tight text-muted">
          {`${S.market.pot} ${formatStake(pozo)}`}
          {jugando > 0 ? ` · ${S.market.participantes(jugando)}` : ""}
          {` · ${cerrada ? S.vivo.cerrando : S.vivo.restante(reloj)}`}
        </span>
      </div>
    </Card>
  );
}
