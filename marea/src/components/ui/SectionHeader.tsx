import { cn } from "@/lib/cn";

/**
 * Encabezado de sección con chevron.
 *
 * El chevron no es adorno: cuando hay `onOpen`, el encabezado es un botón que
 * filtra el feed por esa sección. Un `›` que no lleva a ningún lado enseña a
 * la gente a no tocar los encabezados, y esa lección después cuesta.
 *
 * Sin `onOpen` se pinta como texto y el chevron no aparece, porque entonces no
 * promete nada.
 */
export function SectionHeader({
  id,
  titulo,
  cuenta,
  onOpen,
  className,
}: {
  id?: string;
  titulo: string;
  /** Cuántos mercados hay debajo. Es la prueba de que la sección tiene fondo. */
  cuenta?: number;
  onOpen?: () => void;
  className?: string;
}) {
  const contenido = (
    <>
      <span className="font-display text-[17px] font-semibold leading-none tracking-tight text-text">
        {titulo}
      </span>
      {cuenta !== undefined ? (
        <span className="font-mono text-[12px] font-semibold tabular-nums text-muted">
          {cuenta}
        </span>
      ) : null}
      {onOpen ? (
        // el chevron es tipográfico, no un icono: hereda peso y línea base del
        // titular, así que nunca queda desalineado medio píxel
        <span aria-hidden className="text-[17px] leading-none text-teal">
          ›
        </span>
      ) : null}
    </>
  );

  if (!onOpen) {
    return (
      <h2 id={id} className={cn("flex items-center gap-1.5 px-4 pb-1.5", className)}>
        {contenido}
      </h2>
    );
  }

  return (
    <h2 id={id} className={cn("px-4 pb-1.5", className)}>
      <button
        type="button"
        onClick={onOpen}
        data-testid="section-header"
        className="flex min-h-[32px] items-center gap-1.5"
      >
        {contenido}
      </button>
    </h2>
  );
}
