import type { Market, PulsoVivo } from "@/domain/types";
import { MarketCard } from "@/components/MarketCard";
import { cn } from "@/lib/cn";

/**
 * Carrusel de destacados.
 *
 * Los mercados calientes ya vivían arriba del feed, pero apilados en vertical:
 * cuatro de ellos empujaban el resto del catálogo fuera de la primera pantalla
 * y nadie llegaba a ver que había más de un tema. En horizontal caben los
 * mismos cuatro sin gastar ni un píxel de alto de más, y se ve de un vistazo
 * que hay varios.
 *
 * Tres decisiones que lo acotan:
 *
 *  - **No se mueve solo.** Un carrusel que avanza cada tres segundos le quita
 *    al usuario el control de lo que está leyendo y es lo primero que estorba
 *    con `prefers-reduced-motion`. Aquí el dedo manda: lo único que hay es
 *    scroll con anclaje, que no es animación nuestra.
 *  - **No añade cromo.** Sustituye a la sección que ya estaba, con su
 *    encabezado de lector de pantalla, así que la primera tarjeta sigue
 *    empezando donde empezaba y el presupuesto de densidad no se mueve.
 *  - **Cada tarjeta es la misma card de siempre.** Ni una variante nueva que
 *    haya que mantener en paralelo, ni un componente que se parezca al del
 *    feed pero se comporte distinto.
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
  return (
    <div
      role="group"
      aria-label={etiqueta}
      data-testid="carrusel-destacados"
      className={cn(
        // el desborde lo contiene la fila, nunca la página (V11)
        "flex snap-x snap-mandatory gap-2 overflow-x-auto px-4 pb-0.5",
        "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
      )}
    >
      {markets.map((market) => (
        <div
          key={market.id}
          data-testid="carrusel-item"
          /* 21rem = 336 px, y ese número está medido, no elegido: por debajo
             se corta `paga 1.94×`, y el pago es un número —el CARD_SPEC dice
             que se recorta la etiqueta, nunca la cifra—. Deja 38 px de la
             siguiente asomando, que es lo que anuncia que hay más.

             El `min()` es para 320 px, donde 336 no cabe: ahí la tarjeta se
             queda del ancho que ya tiene en el feed y no se estrecha de más.
             En `rem` y no en `vw` para que con el texto agrandado la tarjeta
             crezca con él en vez de apretar su contenido. */
          className="w-[min(21rem,calc(100vw-2rem))] shrink-0 snap-center"
        >
          <MarketCard
            market={market}
            pulso={vivos[market.id]}
            onOpen={onOpen}
          />
        </div>
      ))}
    </div>
  );
}
