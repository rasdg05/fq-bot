import * as React from "react";
import type { Market, PulsoVivo } from "@/domain/types";
import { MarketCard } from "@/components/MarketCard";
import { cn } from "@/lib/cn";
import { COLOR_CATEGORIA } from "@/lib/categoria";

/**
 * Carrusel de destacados.
 *
 * Los mercados calientes ya vivían arriba del feed, pero apilados en vertical:
 * cuatro de ellos empujaban el resto del catálogo fuera de la primera pantalla
 * y nadie llegaba a ver que había más de un tema. En horizontal caben los
 * mismos sin gastar ni un píxel de alto de más, y se ve de un vistazo que hay
 * varios.
 *
 * Qué entra lo decide `elegirDestacados` (dominio): pocos, variados y lo más
 * vivo primero. Este componente sólo los pinta.
 *
 * Cuatro decisiones que lo acotan:
 *
 *  - **No se mueve solo.** Un carrusel que avanza cada tres segundos le quita
 *    al usuario el control de lo que está leyendo y es lo primero que estorba
 *    con `prefers-reduced-motion`. Aquí el dedo manda: scroll con anclaje.
 *  - **Cada marco abraza su tarjeta.** Antes el marco se estiraba al alto de la
 *    tarjeta más alta de la fila (un partido de tres respuestas, 176 px) y bajo
 *    una vela de cripto (121 px) quedaba colgando un bloque de degradado de
 *    55 px. Estirar la tarjeta en vez del marco tampoco sirve: deja 55 px de
 *    panel vacío dentro, que se lee como un mercado al que le falta algo. La
 *    fila alinea arriba y cada tarjeta mide lo que su contenido.
 *  - **Indicador de posición**, como el de los mercados grandes: dice cuántos
 *    hay y en cuál estás. Es decorativo a propósito — unos puntos de 6 px como
 *    botones violarían los 44 px de R-010, y navegar ya se puede con el dedo y
 *    con el teclado sobre las propias tarjetas.
 *  - **Cada tarjeta es la misma card de siempre.** Ni una variante nueva que
 *    haya que mantener en paralelo.
 */
export function CarruselDestacados({
  markets,
  vivos,
  onOpen,
  etiqueta,
}: {
  markets: Market[];
  vivos: Record<string, PulsoVivo>;
  onOpen: (market: Market) => void;
  /** Cómo se anuncia la fila entera. El encabezado visible no existe (R-063). */
  etiqueta: string;
}) {
  const pistaRef = React.useRef<HTMLDivElement>(null);
  const [activo, setActivo] = React.useState(0);

  /**
   * Cuál está a la vista: el ítem cuyo centro queda más cerca del centro de la
   * pista. Se recalcula en un `requestAnimationFrame` por scroll, nunca más de
   * una vez por cuadro, y con el listener pasivo para no frenar el gesto.
   */
  React.useEffect(() => {
    const pista = pistaRef.current;
    if (!pista) return;
    let cuadro = 0;
    const medir = () => {
      cuadro = 0;
      const centro = pista.scrollLeft + pista.clientWidth / 2;
      let mejor = 0;
      let distancia = Number.POSITIVE_INFINITY;
      Array.from(pista.children).forEach((hijo, indice) => {
        const el = hijo as HTMLElement;
        const d = Math.abs(el.offsetLeft + el.offsetWidth / 2 - centro);
        if (d < distancia) {
          distancia = d;
          mejor = indice;
        }
      });
      setActivo(mejor);
    };
    const alMover = () => {
      if (!cuadro) cuadro = requestAnimationFrame(medir);
    };
    pista.addEventListener("scroll", alMover, { passive: true });
    return () => {
      pista.removeEventListener("scroll", alMover);
      if (cuadro) cancelAnimationFrame(cuadro);
    };
  }, [markets.length]);

  return (
    <div>
      <div
        ref={pistaRef}
        role="group"
        aria-label={etiqueta}
        data-testid="carrusel-destacados"
        className={cn(
          // el desborde lo contiene la fila, nunca la página (V11)
          "flex items-start snap-x snap-mandatory gap-2 overflow-x-auto px-4 pb-0.5",
          "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        )}
      >
        {markets.map((market) => (
          <div
            key={market.id}
            data-testid="carrusel-item"
            /* 21rem = 336 px, medido: por debajo se corta la etiqueta del
               líder. Deja 38 px de la siguiente asomando, que es lo que anuncia
               que hay más. El `min()` es para 320 px, donde 336 no cabe. */
            className="w-[min(21rem,calc(100vw-2rem))] shrink-0 snap-center rounded-[17.5px] p-[1.5px]"
            /* el filo en degradado es lo que dice «destacado» sin gastar una
               fila de cromo en un título: va del color de su categoría al acento */
            style={{
              background: `linear-gradient(135deg, ${COLOR_CATEGORIA[market.category]}, var(--teal) 60%, var(--cat-clima))`,
            }}
          >
            <MarketCard market={market} pulso={vivos[market.id]} onOpen={onOpen} />
          </div>
        ))}
      </div>

      {markets.length > 1 ? (
        <div
          aria-hidden
          data-testid="carrusel-puntos"
          className="mt-2.5 flex items-center justify-center gap-1.5"
        >
          {markets.map((market, indice) => (
            <span
              key={market.id}
              data-activo={indice === activo ? "true" : "false"}
              className={cn(
                "h-1.5 rounded-pill transition-[width,background-color] duration-200 ease-out",
                indice === activo ? "w-5 bg-text" : "w-1.5 bg-line",
              )}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
