import { cn } from "@/lib/cn";

/**
 * La marca de Marea.
 *
 * Un azulejo redondeado con dos líneas de marea caladas encima. Dos ideas y
 * ninguna más: **marea** (las dos líneas, una que sube y otra que se retira) y
 * **mercado** (la línea de abajo no cierra plana, termina más arriba de donde
 * empezó).
 *
 * Por qué azulejo y no un trazo suelto: a 26 px un trazo fino se deshace y se
 * pierde contra el fondo. Una forma sólida con el símbolo calado se lee entera
 * a cualquier tamaño y es lo que hace que el logo domine la izquierda del
 * header sin ocupar más sitio.
 *
 * Es geometría abstracta a propósito: no representa nada más que agua en
 * movimiento.
 */
export function Brandmark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      role="img"
      aria-hidden
      className={cn("shrink-0", className)}
    >
      <rect width="32" height="32" rx="9.5" className="fill-teal" />
      <g
        className="stroke-teal-ink"
        fill="none"
        strokeWidth="2.4"
        strokeLinecap="round"
      >
        {/* la que se retira: más corta, y por eso las dos no son la misma */}
        <path d="M6.2 12.4C8.6 12.4 8.6 9 11 9S13.4 12.4 15.8 12.4 18.2 9 20.6 9" />
        {/* la que sube: cruza el ancho completo y cierra más arriba */}
        <path d="M6.2 21.4C8.6 21.4 8.6 18 11 18S13.4 21.4 15.8 21.4 18.2 18 20.6 18 23 21.4 25.4 20.2" />
      </g>
    </svg>
  );
}
