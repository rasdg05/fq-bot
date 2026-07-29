import type { Market } from "@/domain/types";
import { cn } from "@/lib/cn";

/**
 * El escudo del equipo que nombra un resultado.
 *
 * Antes vivía en la fila de badges, junto a la categoría: dos escudos sueltos
 * arriba a la izquierda, sin decir de quién eran. Ahí no ayudaban a decidir —
 * la decisión es "¿de qué lado me pongo?", y el lado se lee abajo. Ahora cada
 * escudo va pegado a su propio resultado.
 *
 * Sólo se pinta cuando el dato existe. No hay monograma de relleno para `Sí` y
 * `No`: una inicial en un círculo junto a "Sí" no es información, es ruido con
 * forma de avatar. Y no se genera ninguna cara: una foto que nadie subió es
 * una identidad que no es de quien la lleva.
 */
export function EscudoOutcome({
  market,
  label,
  className,
}: {
  market: Market;
  label?: string;
  className?: string;
}) {
  const escudo = escudoDe(market, label);
  if (!escudo) return null;
  return (
    <img
      src={escudo.url}
      alt=""
      aria-hidden
      // `width`/`height` explícitos y `lazy`: una imagen sin dimensiones
      // reserva cero y empuja el layout cuando llega — es la forma más común
      // de subir el CLS sin darse cuenta. Lo verifica `npm run densidad`
      width={20}
      height={20}
      loading="lazy"
      decoding="async"
      className={cn(
        "h-5 w-5 shrink-0 rounded-full bg-panel2 object-contain p-px ring-1 ring-line2",
        className,
      )}
    />
  );
}

/**
 * A qué equipo se refiere una etiqueta de resultado.
 *
 * El mercado trae los equipos y las etiquetas por separado (`Gana el América`,
 * `Empatan`, `Gana Santos`), así que el vínculo se busca por nombre dentro de
 * la etiqueta. Si no hay coincidencia clara —`Empatan`, `4 o más goles`— no se
 * pinta nada: es preferible un hueco a colgarle a un resultado el escudo del
 * equipo equivocado.
 */
export function escudoDe(
  market: Market,
  label?: string,
): { nombre: string; url: string } | null {
  if (!label || !market.equipos?.length) return null;
  const normal = normalizar(label);
  for (const equipo of market.equipos) {
    if (!equipo.escudo) continue;
    if (normal.includes(normalizar(equipo.nombre))) {
      return { nombre: equipo.nombre, url: equipo.escudo };
    }
  }
  return null;
}

/** Sin acentos y en minúscula: `Gana el América` tiene que casar con `America`. */
function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}
