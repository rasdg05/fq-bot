import * as React from "react";
import { cn } from "@/lib/cn";

export interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
}

/**
 * Chip de categoría. 44 px de alto y 8 px de separación en la fila (R-010);
 * el estado activo no depende solo del color: cambia peso y borde.
 */
export const Chip = React.forwardRef<HTMLButtonElement, ChipProps>(
  ({ className, active, children, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={active}
      data-active={active || undefined}
      className={cn(
        "min-h-touch shrink-0 whitespace-nowrap rounded-pill border px-4 text-[14px] transition-colors",
        active
          ? "border-teal bg-teal-soft font-bold text-teal"
          : "border-line2 font-medium text-text2 hover:border-line",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  ),
);
Chip.displayName = "Chip";

export function ChipRow({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="tablist"
      className={cn(
        // scroll horizontal contenido: la fila desborda, la página nunca (V11)
        "flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        className,
      )}
      {...props}
    />
  );
}
