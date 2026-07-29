import type { MarketCategory } from "@/domain/types";
import { cn } from "@/lib/cn";
import {
  COLOR_CATEGORIA,
  FORMA_CATEGORIA,
  rellenoAcento,
  tieneAcento,
} from "@/lib/categoria";
import { S } from "@/lib/strings";

/**
 * La categoría, con su color de verdad.
 *
 * Antes era un punto de 6 px y la palabra en `muted`, alineados a la derecha
 * de la card. El sistema de color existía —seis acentos, una forma por
 * categoría— pero ocupaba seis píxeles y la palabra iba en el color más
 * apagado del sistema: el trabajo estaba hecho y no se veía. De ahí venía casi
 * toda la sensación de feed plano.
 *
 * Ahora es una píldora con relleno del propio acento y el texto en ese acento.
 * Sigue llevando la palabra y la forma, así que R-005 no se toca: el color
 * acelera el reconocimiento, no lo sustituye.
 */
export function CategoryBadge({
  category,
  className,
}: {
  category: MarketCategory;
  className?: string;
}) {
  const color = COLOR_CATEGORIA[category];
  const acento = tieneAcento(category);
  return (
    <span
      data-testid="categoria-marca"
      data-categoria={category}
      className={cn(
        "inline-flex h-[18px] shrink-0 items-center gap-1 rounded-pill border px-1.5 font-sans text-[10px] font-bold uppercase leading-none tracking-[0.05em]",
        !acento && "border-line2 text-text2",
        className,
      )}
      style={acento ? rellenoAcento(color) : undefined}
    >
      <span
        aria-hidden
        className={cn("h-1.5 w-1.5 shrink-0 bg-current", FORMA_CATEGORIA[category])}
      />
      {S.categories[category]}
    </span>
  );
}
