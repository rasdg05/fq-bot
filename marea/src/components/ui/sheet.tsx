import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { S } from "@/lib/strings";

/**
 * Bottom sheet. Sube desde abajo (zona de pulgar) y el botón de cerrar siempre
 * existe: ninguna hoja es un muro. Radix da foco atrapado y Escape gratis.
 */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 animate-fade-in bg-black/40 backdrop-blur-[3px]" />
        <Dialog.Content
          className={cn(
            "fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[88vh] w-full max-w-[520px] animate-sheet-in",
            "overflow-y-auto rounded-t-sheet border-t border-line2 bg-panel shadow-sheet",
            "pb-[max(env(safe-area-inset-bottom),16px)]",
          )}
        >
          <div className="sticky top-0 z-10 bg-panel px-5 pb-3 pt-2.5">
            <div
              aria-hidden
              className="mx-auto mb-4 h-1 w-9 rounded-full bg-line"
            />
            <div className="flex items-start justify-between gap-3">
              <div>
                <Dialog.Title className="font-display text-[21px] font-semibold leading-tight tracking-[-0.01em] text-text">
                  {title}
                </Dialog.Title>
                {description ? (
                  <Dialog.Description className="mt-1 text-[14px] text-text2">
                    {description}
                  </Dialog.Description>
                ) : (
                  <Dialog.Description className="sr-only">{title}</Dialog.Description>
                )}
              </div>
              <Dialog.Close
                aria-label={S.common.close}
                className="-mr-2 grid h-touch w-touch shrink-0 place-items-center rounded-full text-muted transition-colors hover:bg-panel2 hover:text-text"
              >
                <X aria-hidden className="h-5 w-5" />
              </Dialog.Close>
            </div>
          </div>
          <div className="px-5">{children}</div>
          {footer ? <div className="px-5 pt-4">{footer}</div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
