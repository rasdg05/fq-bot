import * as React from "react";
import { cn } from "@/lib/cn";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * La tarjeta de mercado es un `article`: dejó de ser un botón envolvente el
   * día que las pills pasaron a ser botones de verdad, y un botón dentro de
   * otro botón no es HTML válido ni se puede tabular.
   */
  as?: "div" | "article";
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, as: Tag = "div", ...props }, ref) => (
    <Tag
      ref={ref as React.Ref<HTMLDivElement>}
      className={cn(
        // sin sombra: con el borde de 1 px la card ya está despegada del fondo, y
        // treinta sombras de 30 px en una pantalla es lo que hace que un feed
        // denso se sienta pesado. La profundidad la da la superficie, no el humo
        "rounded-card border border-line2 bg-panel",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

export const CardBody = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-4", className)} {...props} />
));
CardBody.displayName = "CardBody";
