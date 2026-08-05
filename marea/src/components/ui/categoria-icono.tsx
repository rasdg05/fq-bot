import { cn } from "@/lib/cn";
import { COLOR_CATEGORIA, ICONO_CATEGORIA } from "@/lib/categoria";
import type { MarketCategory } from "@/domain/types";

/**
 * El azulejo de categoría de una card.
 *
 * Un cuadrado de 16 px con el color de la categoría al 18 % y su glifo encima.
 * No lleva imagen: una ilustración por mercado sería adorno en una pregunta
 * sobre inflación, y el catálogo se llenaría de dibujos que no dicen nada. Lo
 * que sí identifica algo real —el escudo de un equipo, el retrato de una
 * persona— viaja en el dato y se pinta al lado del resultado, citando a la
 * misma fuente que resuelve el mercado (R-046).
 */
export function CategoriaIcono({
  categoria,
  className,
}: {
  categoria: MarketCategory;
  className?: string;
}) {
  const Icono = ICONO_CATEGORIA[categoria];
  const color = COLOR_CATEGORIA[categoria];
  return (
    <span
      aria-hidden
      data-testid="categoria-marca"
      data-categoria={categoria}
      className={cn(
        "grid h-4 w-4 shrink-0 place-items-center rounded-[5px]",
        className,
      )}
      /* 28 %, no 20 %: a 16 px un lavado del 20 % sobre `--panel` se lee como
         gris y las seis categorías volvían a parecer la misma. El glifo va a
         color pleno encima, que es lo que hace que el azulejo se distinga de
         reojo. La caja no cambia de tamaño, así que la densidad tampoco. */
      style={{ backgroundColor: `color-mix(in srgb, ${color} 28%, transparent)` }}
    >
      <Icono className="h-2.5 w-2.5" style={{ color }} strokeWidth={2.4} />
    </span>
  );
}
