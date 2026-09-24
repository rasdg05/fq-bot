import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * `tailwind-merge` no conoce nuestra escala tipográfica: sin declararla, trata
 * `text-prob-pill` como si fuera un color y lo descarta cuando en la misma
 * clase viaja `text-text`. El número se quedaba sin tamaño y la jerarquía de
 * la card se perdía en silencio — el peor tipo de defecto de estilo, porque
 * ningún tipo lo ve. Aquí se declaran los tamaños propios para que tamaño y
 * color puedan convivir.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        { text: ["prob", "prob-lg", "prob-sm", "prob-pill", "prob-riv", "prob-row", "mult"] },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
