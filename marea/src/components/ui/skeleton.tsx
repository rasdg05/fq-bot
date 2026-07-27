import { cn } from "@/lib/cn";

/**
 * Skeleton con la altura final del contenido: sin saltos de layout (CLS <= 0.1).
 */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn(
        "relative overflow-hidden rounded-lg bg-panel2",
        "after:absolute after:inset-0 after:-translate-x-full after:animate-shimmer",
        "after:bg-gradient-to-r after:from-transparent after:via-[color:var(--line2)] after:to-transparent",
        className,
      )}
      {...props}
    />
  );
}
