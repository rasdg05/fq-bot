import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Todo CTA crítico expone los cuatro estados: idle | loading | disabled | error
 * (R-006). El alto mínimo nunca baja de 44 px (R-010).
 */
const buttonVariants = cva(
  "relative inline-flex select-none items-center justify-center gap-2 rounded-pill font-sans font-semibold " +
    "transition-[transform,background-color,border-color,opacity] duration-150 active:scale-[.985] " +
    "disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "bg-teal text-[color:var(--teal-ink)] hover:bg-teal-deep",
        secondary: "bg-panel2 text-text border border-line hover:border-teal",
        ghost: "bg-transparent text-text2 hover:text-text",
        yes: "bg-[color:var(--up)] text-[color:var(--bg)] hover:opacity-90",
        no: "bg-[color:var(--dn)] text-[color:var(--bg)] hover:opacity-90",
      },
      size: {
        // 44 px es el piso; los CTA de pantalla usan 52 px (zona de pulgar)
        md: "min-h-touch px-5 text-[15px]",
        lg: "min-h-[52px] w-full px-6 text-[16px]",
        sm: "min-h-touch px-4 text-[14px]",
        icon: "h-touch w-touch p-0",
      },
      state: {
        idle: "",
        error: "ring-1 ring-[color:var(--dn)]",
      },
    },
    defaultVariants: { variant: "primary", size: "md", state: "idle" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
  loadingLabel?: string;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      state,
      asChild = false,
      loading = false,
      loadingLabel,
      disabled,
      children,
      onClick,
      ...props
    },
    ref,
  ) => {
    const Comp = asChild ? Slot : "button";
    // Doble tap no dispara dos veces mientras hay trabajo en vuelo (R-016).
    const handleClick = React.useCallback(
      (event: React.MouseEvent<HTMLButtonElement>) => {
        if (loading || disabled) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      },
      [loading, disabled, onClick],
    );

    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size, state }), className)}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        data-state={loading ? "loading" : disabled ? "disabled" : state ?? "idle"}
        onClick={handleClick}
        {...props}
      >
        {loading ? (
          <>
            <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
            <span>{loadingLabel ?? children}</span>
          </>
        ) : (
          children
        )}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
