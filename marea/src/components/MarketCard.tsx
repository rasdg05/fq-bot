import * as React from "react";
import type { Market, MarcadorVivo, PulsoVivo } from "@/domain/types";
import { hasEdge } from "@/domain/edge";
import { Card } from "@/components/ui/card";
import { CryptoLiveCard } from "@/components/CryptoLiveCard";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { CategoriaIcono } from "@/components/ui/categoria-icono";
import { COLOR_CATEGORIA } from "@/lib/categoria";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { compactUsd, pct, closesIn, eventoTexto } from "@/lib/format";
import {
  BINARY_OUTCOMES,
  formatMultiplier,
  payoutMultiplier,
  rankedOutcomes,
  type OutcomeId,
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
  /** El latido de la vela, cuando el mercado es de cripto en vivo. */
  pulso?: PulsoVivo;
  /**
   * El segundo argumento es el resultado que se tocó. Tocar la tarjeta abre el
   * detalle; tocar una pill abre el mismo detalle con ese lado ya elegido.
   */
  onOpen: (market: Market, outcomeId?: OutcomeId) => void;
}

/** Cuánto dura el congelado después de soltar: lo que tarda en subir la hoja. */
const DESHIELO_MS = 220;
/** El destello de actualización. Coincide con `animate-flash-*`. */
const DESTELLO_MS = 200;

/**
 * Estado presionado y foco de una pill, en un solo lugar.
 *
 * El anillo vive siempre a 2 px en `transparent` y sólo transiciona el color:
 * animar el grosor produce un salto de pintado en cada tabulación. Va en
 * `outline` y no en `box-shadow` para que no participe del layout — dentro de
 * una tarjeta de 114 px, un anillo que empuja es un anillo que rompe.
 */
const PILL_BASE = cn(
  "relative z-10 flex h-9 min-w-[64px] shrink-0 items-center justify-center rounded-pill px-2.5",
  // 36 px de pill, 44 de zona tocable: el aire de arriba y abajo es parte del
  // botón y no cuesta una fila de card (R-010)
  "after:absolute after:inset-x-0 after:-inset-y-1 after:content-['']",
  "outline outline-2 outline-offset-2 outline-transparent focus-visible:outline-pill-ring",
  "transition-[background-color,outline-color,transform,color] duration-[120ms] ease-out",
  "active:scale-[.96] active:duration-90",
);

interface OpcionProps {
  lado: "lider" | "rival";
  label: string;
  probability: number;
  multiplier?: string;
  /**
   * Color de la categoría, para teñir el anillo del líder. Es un acento y nada
   * más: el que manda se sigue reconociendo por el tamaño y el peso del número
   * (R-005). Sin esto el anillo se queda en `--pill-ring`, como estaba.
   */
  color?: string;
  destello: "up" | "dn" | null;
  onPick?: () => void;
  onCongelar?: (congelar: boolean) => void;
}

/**
 * Un resultado: la pill con el porcentaje y, al lado, su nombre y su pago.
 *
 * El número es lo accionable; el texto de al lado es contexto y cae en el
 * enlace estirado de la tarjeta. Así el anillo de foco hereda el radio de la
 * pill sin dibujar un rectángulo alrededor de media fila.
 */
function Opcion({
  lado,
  label,
  probability,
  multiplier,
  color,
  destello,
  onPick,
  onCongelar,
}: OpcionProps) {
  const lider = lado === "lider";
  const porcentaje = pct(probability);
  return (
    <div
      data-testid={lider ? "card-lider" : "card-other-side"}
      className="flex min-w-0 flex-1 items-center gap-2"
    >
      <button
        type="button"
        data-role="pill"
        data-lado={lado}
        aria-label={
          multiplier
            ? S.market.pillLabel(label, porcentaje, multiplier)
            : `${label}, ${porcentaje} %`
        }
        onClick={onPick}
        onPointerDown={() => onCongelar?.(true)}
        onPointerUp={() => onCongelar?.(false)}
        onPointerCancel={() => onCongelar?.(false)}
        onPointerLeave={() => onCongelar?.(false)}
        className={cn(
          PILL_BASE,
          lider
            ? "bg-teal-soft ring-1 ring-[color:var(--pill-cat)] [@media(hover:hover)and(pointer:fine)]:hover:ring-teal"
            : "bg-pill-wash ring-1 ring-pill-line [@media(hover:hover)and(pointer:fine)]:hover:ring-pill-ring",
          destello === "up" ? "animate-flash-up" : "",
          destello === "dn" ? "animate-flash-dn" : "",
        )}
        /* Sólo el anillo, y a media fuerza: el relleno sigue siendo `teal-soft`
           para todas las categorías. Teñir también el fondo convertiría la
           tarjeta en un semáforo de seis colores y le quitaría el sitio al
           número, que es el nodo dominante (R-004). */
        style={
          lider
            ? ({
                "--pill-cat": color
                  ? `color-mix(in srgb, ${color} 55%, transparent)`
                  : "var(--pill-ring)",
              } as React.CSSProperties)
            : undefined
        }
      >
        <span
          {...(lider ? { "data-dominant": "probability", "data-role": "probability" } : {})}
          className={cn(
            "font-display tabular-nums",
            // el rival sube a `--text` con fondo teñido: sobre el relleno del
            // `active` el `--text2` caía a 5,27:1 y el número es el dato
            lider
              ? "text-prob-pill font-bold text-text"
              : "text-prob-riv font-semibold text-text2 group-active:text-text",
          )}
        >
          {porcentaje}
          <span
            className={cn(
              "ml-0.5 align-top text-[12px] font-bold opacity-70",
              lider ? "text-text" : "text-text2",
            )}
          >
            %
          </span>
        </span>
      </button>

      {/* el pago nunca se corta: es un número, y "2.4…" no es un número. La
          columna mide al menos lo que mide el pago (`min-w-fit`) y quien cede
          es la etiqueta, que sí se entiende recortada */}
      {/* la columna de texto sí puede encogerse: si no, la etiqueta del líder
          se monta encima de la pill del rival. Quien cede es la etiqueta, que
          se entiende recortada; el pago cabe entero en el ancho que queda */}
      <span className="flex min-w-0 flex-col whitespace-nowrap leading-none">
        <span className="truncate text-[13px] font-semibold leading-[15px] text-text2">
          {label}
        </span>
        {multiplier ? (
          <span className="mt-0.5 truncate font-mono text-mult font-medium tabular-nums text-muted">
            {S.market.pays2(multiplier)}
          </span>
        ) : null}
      </span>
    </div>
  );
}

/**
 * Barra de probabilidad. Dos segmentos con 2 px de separación, nunca de 0 px
 * de ancho: por debajo del 2 % se dibuja un tope, porque "casi nada" y "nada"
 * no son lo mismo cuando se está apostando. Decorativa para el lector de
 * pantalla — el porcentaje ya está en texto al lado.
 */
function ProbBar({ lider, rival }: { lider: number; rival: number }) {
  const ancho = (p: number) => `${Math.max(p * 100, p > 0 ? 2 : 0)}%`;
  return (
    <span aria-hidden className="flex h-[3px] w-full gap-0.5 overflow-hidden rounded-pill">
      <span
        data-testid="prob-bar-lider"
        className="h-full rounded-pill bg-teal transition-[width] duration-[240ms] ease-[cubic-bezier(.22,1,.36,1)]"
        style={{ width: ancho(lider) }}
      />
      <span
        className="h-full rounded-pill bg-muted transition-[width] duration-[240ms] ease-[cubic-bezier(.22,1,.36,1)]"
        style={{ width: ancho(rival) }}
      />
      <span className="h-full flex-1 rounded-pill bg-line2" />
    </span>
  );
}

/**
 * Una fila de un mercado de más de dos resultados.
 *
 * Vertical y no en dos columnas: con tres candidatos, dos columnas obligan a
 * elegir cuáles dos se enseñan, y el tercero desaparece sin decirlo. En lista
 * los tres se leen de arriba abajo y el número queda en la misma columna, que
 * es lo que permite compararlos de un vistazo.
 */
function FilaResultado({
  outcome,
  primera,
  color,
  destello,
  onPick,
  onCongelar,
}: {
  outcome: { id: OutcomeId; label: string; probability: number; multiplier: number };
  primera: boolean;
  /** Igual que en `Opcion`: tiñe el anillo del que va primero, nada más. */
  color?: string;
  destello: "up" | "dn" | null;
  onPick?: () => void;
  onCongelar?: (congelar: boolean) => void;
}) {
  const porcentaje = pct(outcome.probability);
  const pago = formatMultiplier(outcome.multiplier);
  return (
    <div className="flex flex-col gap-[3px]">
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          data-role="pill"
          data-lado={primera ? "lider" : "rival"}
          aria-label={S.market.pillLabel(outcome.label, porcentaje, pago)}
          onClick={onPick}
          onPointerDown={() => onCongelar?.(true)}
          onPointerUp={() => onCongelar?.(false)}
          onPointerCancel={() => onCongelar?.(false)}
          onPointerLeave={() => onCongelar?.(false)}
          className={cn(
            "relative z-10 flex h-[26px] min-w-[62px] shrink-0 items-center justify-center rounded-pill px-2.5",
            "outline outline-2 outline-offset-2 outline-transparent focus-visible:outline-pill-ring",
            "transition-[background-color,outline-color,transform,color] duration-[120ms] ease-out",
            "active:scale-[.96] active:duration-90",
            primera
              ? "bg-teal-soft ring-1 ring-[color:var(--pill-cat)]"
              : "bg-pill-wash ring-1 ring-pill-line",
            destello === "up" ? "animate-flash-up" : "",
            destello === "dn" ? "animate-flash-dn" : "",
          )}
          style={
            primera
              ? ({
                  "--pill-cat": color
                    ? `color-mix(in srgb, ${color} 55%, transparent)`
                    : "var(--pill-ring)",
                } as React.CSSProperties)
              : undefined
          }
        >
          <span
            {...(primera
              ? { "data-dominant": "probability", "data-role": "probability" }
              : {})}
            className={cn(
              "font-display tabular-nums",
              primera
                ? "text-prob-pill font-bold text-text"
                : "text-prob-row font-semibold text-text2",
            )}
          >
            {porcentaje}
            <span className="ml-0.5 align-top text-[11px] font-bold opacity-70">%</span>
          </span>
        </button>
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-text2">
          {outcome.label}
        </span>
        <span className="shrink-0 font-mono text-mult font-medium tabular-nums text-muted">
          {S.market.pays2(pago)}
        </span>
      </div>
      <span aria-hidden className="flex h-[3px] w-full overflow-hidden rounded-pill bg-line2">
        <span
          className={cn(
            "h-full rounded-pill transition-[width] duration-[240ms] ease-[cubic-bezier(.22,1,.36,1)]",
            primera ? "bg-teal" : "bg-muted",
          )}
          style={{ width: `${Math.max(outcome.probability * 100, 2)}%` }}
        />
      </span>
    </div>
  );
}

/** El marcador del evento en curso, en una fila de 20 px. */
function FilaMarcador({ marcador }: { marcador: MarcadorVivo }) {
  const numero = "font-display text-[16px] font-bold leading-5 tabular-nums text-text";
  const nombre = "min-w-0 truncate text-[13px] font-semibold text-text2";
  return (
    <div
      data-testid="card-marcador"
      className="flex h-5 items-center gap-4 overflow-hidden"
    >
      {marcador.deporte === "tenis" ? (
        marcador.jugadores.map((jugador, i) => (
          <span key={jugador} className="flex min-w-0 items-center gap-1.5">
            {marcador.saque === i ? (
              <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-teal" />
            ) : null}
            <span className={nombre}>{jugador}</span>
            <span className={cn(numero, "flex shrink-0 gap-1.5")}>
              {marcador.sets.map((set, s) => (
                <span key={s} className={s === marcador.sets.length - 1 ? "opacity-70" : ""}>
                  {set[i]}
                </span>
              ))}
            </span>
          </span>
        ))
      ) : marcador.deporte === "beisbol" ? (
        marcador.equipos.map((equipo, i) => (
          <span key={equipo} className="flex min-w-0 items-center gap-1.5">
            <span className={nombre}>{equipo}</span>
            <span className={cn(numero, "shrink-0")}>{marcador.carreras[i]}</span>
          </span>
        ))
      ) : (
        marcador.equipos.map((equipo, i) => (
          <span key={equipo} className="flex min-w-0 items-center gap-1.5">
            <span className={nombre}>{equipo}</span>
            <span className={cn(numero, "shrink-0")}>{marcador.goles[i]}</span>
          </span>
        ))
      )}
    </div>
  );
}

/** El badge de estado del evento: game de tenis, entrada de béisbol, minuto. */
function badgeEstado(marcador?: MarcadorVivo): string | null {
  if (!marcador) return null;
  if (marcador.deporte === "tenis") return marcador.game ?? null;
  if (marcador.deporte === "beisbol") return S.market.entrada(marcador.entrada, marcador.mitad);
  return marcador.minuto ?? null;
}

/**
 * Tarjeta de mercado. Descubrimiento denso: el porcentaje manda por tamaño y
 * peso, los dos lados se nombran, y la barra dice de un vistazo cómo está
 * repartido el pozo. El Edge **no vive aquí** — se lee en el detalle, que es
 * donde se decide (R-001, §4.7 del rediseño).
 *
 * La tarjeta entera abre el detalle a través de un enlace estirado; las pills
 * son botones reales por encima y abren el mismo detalle con su lado elegido.
 */
export function MarketCard({ market, variant, pulso, onOpen }: MarketCardProps) {
  /**
   * Una vela viva se pinta con su propia card. No es una variante más de ésta:
   * lo que necesita —reloj, precio que se mueve, congelado al tocar— no cabía
   * aquí sin reabrir una card que ya está cerrada. La decisión de cuál pintar
   * la toma el dato (`market.live`), nunca la vista.
   */
  if (market.live && market.status === "live" && !variant) {
    return (
      <CryptoLiveCard
        market={market as Market & { live: NonNullable<Market["live"]> }}
        pulso={pulso}
        onOpen={onOpen}
      />
    );
  }

  const resolved = variant ?? resolveVariant(market);
  const compact = resolved === "compact";

  // mientras el dedo está sobre una pill, esta tarjeta deja de aplicar
  // actualizaciones: apostar a un número que cambió en el milisegundo del
  // toque es el defecto clásico del live, y se arregla aquí
  const [congelado, setCongelado] = React.useState(false);
  const [vista, setVista] = React.useState(market);
  const deshielo = React.useRef<ReturnType<typeof setTimeout>>();

  React.useEffect(() => {
    if (!congelado) setVista(market);
  }, [market, congelado]);

  const congelar = React.useCallback((activo: boolean) => {
    clearTimeout(deshielo.current);
    if (activo) {
      setCongelado(true);
      return;
    }
    // se descongela cuando la hoja ya tomó la pantalla, no al soltar
    deshielo.current = setTimeout(() => setCongelado(false), DESHIELO_MS);
  }, []);

  React.useEffect(() => () => clearTimeout(deshielo.current), []);

  const pool = vista.pool;
  const ranked = pool
    ? rankedOutcomes(pool, vista.outcomes ?? [...BINARY_OUTCOMES])
    : [];
  const [lider, rival] = ranked;
  const probLider = lider ? lider.probability : vista.probability;

  // destello de actualización: sólo con cambios que se notan (0,5 pp)
  const [destello, setDestello] = React.useState<"up" | "dn" | null>(null);
  const anterior = React.useRef(probLider);
  React.useEffect(() => {
    const delta = probLider - anterior.current;
    anterior.current = probLider;
    if (Math.abs(delta) < 0.005) return;
    setDestello(delta > 0 ? "up" : "dn");
    const id = setTimeout(() => setDestello(null), DESTELLO_MS);
    return () => clearTimeout(id);
  }, [probLider]);

  // con más de dos respuestas la card cambia de disposición: lista vertical
  const multi = ranked.length > 2;
  const restantes = ranked.length - 3;
  const vivo = vista.status === "live" && Boolean(vista.marcadorVivo);
  const resolviendo = vista.status === "settling";
  const cerrado = vista.status === "resolved" || resolviendo;
  const closes = closesIn(vista.closesAt);
  const colorCategoria = COLOR_CATEGORIA[vista.category];
  const estado = badgeEstado(vista.marcadorVivo);
  const evento = eventoTexto(vista.eventoReciente);
  const titulo = vista.shortTitle ?? vista.title;

  const abrir = React.useCallback(
    (outcomeId?: OutcomeId) => onOpen(vista, outcomeId),
    [onOpen, vista],
  );

  return (
    <Card
      as="article"
      className={cn("relative overflow-hidden", cerrado && "opacity-90")}
      data-testid="market-card"
      data-variant={resolved}
      data-market-id={vista.id}
      data-congelado={congelado ? "true" : "false"}
    >
      <div
        className={cn(
          "flex flex-col gap-[3px] px-3.5",
          compact ? "min-h-touch py-2" : "py-[9px]",
        )}
      >
        {/* la categoría manda a la izquierda, con su azulejo: es lo primero que
            dice de qué va la card, igual que en las casas que se leen bien.
            Los badges de estado se van a la derecha, donde no compiten */}
        <div className="flex h-4 items-center gap-1.5">
          <CategoriaIcono categoria={vista.category} />
          <span className="mr-auto shrink-0 text-[10px] font-bold uppercase tracking-[0.06em] text-muted">
            {S.categories[vista.category]}
          </span>
          {vivo ? (
            <Badge tone="live" dot>
              {S.badges.live}
            </Badge>
          ) : null}
          {estado && vivo ? (
            <Badge tone="live" data-testid="card-estado" className="font-mono">
              {estado}
            </Badge>
          ) : null}
          {resolviendo ? (
            <Badge tone="neutral" data-testid="card-resolviendo">
              {S.badges.settling}
            </Badge>
          ) : null}
          {vista.hot && !resolviendo ? <Badge tone="hot">{S.badges.hot}</Badge> : null}
          {vista.country || vista.region === "latam" ? (
            <Badge tone="latam">{vista.country ?? S.badges.latam}</Badge>
          ) : null}
        </div>

        {vivo && vista.marcadorVivo ? (
          <FilaMarcador marcador={vista.marcadorVivo} />
        ) : (
          <h3
            className={cn(
              "font-display font-semibold text-text",
              vista.shortTitle ? "line-clamp-1" : "line-clamp-2",
              compact ? "text-[14px]" : "text-[15px]",
              // el interlineado va DESPUÉS del recorte: `line-clamp` y
              // `leading` son grupos que chocan en tailwind-merge, y el que
              // llega primero se descarta. Con el orden al revés el título se
              // iba a 22.5 px de línea y la card crecía 7 px por línea
              "leading-[19px]",
            )}
          >
            {titulo}
          </h3>
        )}

        {multi ? (
          /* lista vertical: las tres respuestas con más pozo, cada una con su
             barra. La cuarta y siguientes se cuentan en el pie */
          <div className="flex flex-col gap-[3px]" data-testid="card-multi">
            {ranked.slice(0, 3).map((outcome, i) => (
              <FilaResultado
                key={outcome.id}
                outcome={outcome}
                primera={i === 0}
                color={colorCategoria}
                destello={i === 0 ? destello : null}
                onPick={cerrado ? undefined : () => abrir(outcome.id)}
                onCongelar={congelar}
              />
            ))}
          </div>
        ) : (
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <Opcion
            lado="lider"
            label={pool ? (lider?.label ?? S.market.yes) : S.market.probability}
            probability={probLider}
            multiplier={
              pool
                ? formatMultiplier(
                    lider ? lider.multiplier : payoutMultiplier(pool, "si"),
                  )
                : undefined
            }
            color={colorCategoria}
            destello={destello}
            onPick={cerrado ? undefined : () => abrir(lider?.id)}
            onCongelar={congelar}
          />
          {pool && rival ? (
            <Opcion
              lado="rival"
              label={rival.label}
              probability={rival.probability}
              multiplier={formatMultiplier(rival.multiplier)}
              destello={destello}
              onPick={cerrado ? undefined : () => abrir(rival.id)}
              onCongelar={congelar}
            />
          ) : null}
        </div>
        )}

        {multi ? null : (
          <ProbBar
            lider={probLider}
            rival={rival ? rival.probability : Math.max(0, 1 - probLider)}
          />
        )}

        {/* pie en una sola línea. El orden es la prioridad: primero lo que
            explica el movimiento del precio, y lo primero que se va cuando no
            cabe es cuánta gente hay dentro */}
        <span className="-mt-px flex h-[11px] items-center gap-1 overflow-hidden whitespace-nowrap text-[11px] leading-[11px] tracking-[0.005em] text-muted">
          {multi && restantes > 0 ? (
            <span className="shrink-0 text-text2">{S.market.respuestasMas(restantes)} ·</span>
          ) : null}
          {evento ? <span className="shrink-0 text-text2">{evento} ·</span> : null}
          <span className="shrink-0">
            {pool ? `${S.market.pot} ${formatStake(vista.volume)}` : compactUsd(vista.volume)}
          </span>
          {vista.participantes ? (
            <span className="hidden shrink-0 angosto:inline">
              · {S.market.participantes(vista.participantes)}
            </span>
          ) : null}
          <span className="shrink-0">
            {resolviendo
              ? `· ${S.market.esperandoFuente}`
              : closes
                ? ` · ${S.market.closes} ${closes}`
                : ` · ${S.badges.closed}`}
          </span>
        </span>
      </div>

      {/* enlace estirado: cubre la tarjeta entera y queda por debajo de las
          pills, que llevan `z-10`. Va al final del DOM para que el contenido
          se lea antes que la acción */}
      <button
        type="button"
        data-testid="card-open"
        onClick={() => abrir()}
        aria-label={`${S.market.openDetail}: ${vista.title}`}
        className="absolute inset-0 rounded-card focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-pill-ring"
      />
    </Card>
  );
}
