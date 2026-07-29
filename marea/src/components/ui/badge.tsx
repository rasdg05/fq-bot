import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";
import { rellenoAcento } from "@/lib/categoria";

/**
 * Los badges llevan SIEMPRE texto además del color: LIVE, HOT y LATAM se leen
 * sin depender de la vista cromática (R-005). El punto que late en LIVE es
 * refuerzo, no el portador del significado.
 *
 * LIVE y HOT llevan relleno y los demás no. Es la jerarquía dicha con peso: si
 * los cinco tonos se pintan igual, ninguno significa urgencia. El relleno se
 * arma con `color-mix()` en estilo en línea porque un color declarado como
 * `var(--x)` no admite modificador de opacidad en Tailwind (R-017).
 */
const badgeVariants = cva(
  // alto fijo de 18 px con `leading-none`: con el interlineado por defecto el
  // badge medía 23 px, y la fila 1 se repite 29 veces en una pantalla —cinco
  // píxeles ahí son media card al final del scroll (vault/CARD_SPEC.md)
  "inline-flex h-[18px] items-center gap-1.5 rounded-pill border px-2 font-sans text-[11px] font-bold leading-none tracking-[0.06em]",
  {
    variants: {
      tone: {
        live: "",
        hot: "",
        latam: "border-line text-text2",
        neutral: "border-line2 text-muted",
        edge: "border-teal bg-teal-soft text-teal",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

/** Los tonos que se pintan con relleno de acento, y con qué token. */
const RELLENO: Partial<Record<NonNullable<VariantProps<typeof badgeVariants>["tone"]>, string>> = {
  live: "var(--live)",
  hot: "var(--hot)",
};

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean;
}

export function Badge({ className, tone, dot, children, style, ...props }: BadgeProps) {
  const acento = tone ? RELLENO[tone] : undefined;
  return (
    <span
      className={cn(badgeVariants({ tone }), className)}
      style={acento ? { ...rellenoAcento(acento), ...style } : style}
      {...props}
    >
      {dot ? (
        <span
          aria-hidden
          className="h-1.5 w-1.5 rounded-full bg-current animate-live"
        />
      ) : null}
      {children}
    </span>
  );
}
