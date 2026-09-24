import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * Los badges llevan SIEMPRE texto además del color: LIVE, HOT y LATAM se leen
 * sin depender de la vista cromática (R-005). El punto que late en LIVE es
 * refuerzo, no el portador del significado.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-pill border border-transparent px-2 py-0.5 font-sans text-[11px] font-semibold tracking-[0.02em]",
  {
    variants: {
      tone: {
        live: "bg-[color:color-mix(in_srgb,var(--live)_14%,transparent)] text-[color:var(--live)]",
        hot: "bg-[color:color-mix(in_srgb,var(--hot)_14%,transparent)] text-[color:var(--hot)]",
        latam: "bg-panel2 text-text2",
        neutral: "bg-panel2 text-muted",
        edge: "bg-teal-soft text-teal",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean;
}

export function Badge({ className, tone, dot, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ tone }), className)} {...props}>
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
