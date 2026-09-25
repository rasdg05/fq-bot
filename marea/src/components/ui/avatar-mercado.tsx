import * as React from "react";
import { cn } from "@/lib/cn";
import { COLOR_CATEGORIA, ICONO_CATEGORIA } from "@/lib/categoria";
import type { Market } from "@/domain/types";

/**
 * La ficha de un mercado: lo primero que el ojo reconoce antes de leer.
 *
 * - **Partido**: los dos escudos, encimados. Los sirve ESPN, que es la misma
 *   fuente que resuelve el mercado (R-046).
 * - **Cripto**: la moneda en su color de marca, con su símbolo.
 * - **Lo demás**: el glifo de la categoría sobre un degradado de su color.
 *
 * Lleva `data-testid="categoria-marca"`: es la marca de categoría de la card
 * (antes un azulejo de 16 px, que con la ficha al lado sólo repetía).
 *
 * Es adorno con información, nunca el único portador: el nombre del equipo, del
 * activo o de la categoría va siempre escrito al lado (R-005). Si un escudo no
 * carga, se cae a la ficha de categoría — una imagen rota no es una ficha.
 */

const MONEDA: Record<string, { simbolo: string; color: string }> = {
  BTC: { simbolo: "₿", color: "var(--coin-btc)" },
  ETH: { simbolo: "Ξ", color: "var(--coin-eth)" },
  SOL: { simbolo: "◎", color: "var(--coin-sol)" },
  XRP: { simbolo: "✕", color: "var(--coin-xrp)" },
  DOGE: { simbolo: "Ð", color: "var(--coin-doge)" },
};

export function AvatarMercado({
  market,
  className,
}: {
  market: Pick<Market, "category" | "equipos" | "activo">;
  className?: string;
}) {
  const [escudoRoto, setEscudoRoto] = React.useState(false);
  const escudos = (market.equipos ?? []).filter((equipo) => equipo.escudo);
  const moneda = market.activo ? MONEDA[market.activo] : undefined;
  const color = COLOR_CATEGORIA[market.category];

  if (escudos.length > 0 && !escudoRoto) {
    return (
      <span
        aria-hidden
        data-testid="categoria-marca"
        data-categoria={market.category}
        data-ficha="escudos"
        className={cn("relative block shrink-0", className)}
      >
        {escudos.slice(0, 2).map((equipo, i) => (
          <img
            key={equipo.nombre}
            src={equipo.escudo}
            alt=""
            width={28}
            height={28}
            loading="lazy"
            decoding="async"
            onError={() => setEscudoRoto(true)}
            className={cn(
              "absolute h-[70%] w-[70%] rounded-full bg-white object-contain p-[3px] ring-2 ring-panel",
              i === 0 ? "left-0 top-0" : "bottom-0 right-0",
            )}
          />
        ))}
      </span>
    );
  }

  if (moneda) {
    return (
      <span
        aria-hidden
        data-testid="categoria-marca"
        data-categoria={market.category}
        data-ficha="moneda"
        className={cn(
          "grid shrink-0 place-items-center rounded-full text-[18px] font-bold leading-none text-white",
          className,
        )}
        style={{
          background: `radial-gradient(circle at 30% 25%, color-mix(in srgb, ${moneda.color} 70%, white), ${moneda.color} 70%)`,
          boxShadow: `0 4px 14px color-mix(in srgb, ${moneda.color} 35%, transparent)`,
        }}
      >
        {/* el glifo en su propio nodo: la ficha mide 38 px y el texto una
            línea, y así es como lo mide `npm run densidad` */}
        <span>{moneda.simbolo}</span>
      </span>
    );
  }

  const Icono = ICONO_CATEGORIA[market.category];
  return (
    <span
      aria-hidden
      data-testid="categoria-marca"
      data-categoria={market.category}
      data-ficha="categoria"
      className={cn("grid shrink-0 place-items-center rounded-[11px] text-white", className)}
      style={{
        background: `linear-gradient(135deg, color-mix(in srgb, ${color} 85%, white), color-mix(in srgb, ${color} 80%, black))`,
        boxShadow: `0 4px 14px color-mix(in srgb, ${color} 30%, transparent)`,
      }}
    >
      <Icono className="h-[55%] w-[55%]" strokeWidth={2.2} />
    </span>
  );
}
