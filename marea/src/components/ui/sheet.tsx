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
        <Dialog.Overlay className="fixed inset-0 z-40 animate-fade-in bg-black/55 backdrop-blur-[2px]" />
        <Dialog.Content
          className={cn(
            "fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[88vh] w-full max-w-[520px] animate-sheet-in",
            "overflow-y-auto rounded-t-sheet border-t border-line bg-panel shadow-sheet",
            "pb-[max(env(safe-area-inset-bottom),16px)]",
          )}
        >
          <div className="sticky top-0 z-10 bg-panel px-4 pb-3 pt-3">
            <div
              aria-hidden
              className="mx-auto mb-3 h-1 w-10 rounded-full bg-line2"
            />
            <div className="flex items-start justify-between gap-3">
              <div>
                <Dialog.Title className="font-display text-[20px] font-semibold leading-tight text-text">
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
                className="-mr-1 grid h-touch w-touch shrink-0 place-items-center rounded-full text-text2 hover:text-text"
              >
                <X aria-hidden className="h-5 w-5" />
              </Dialog.Close>
            </div>
          </div>
          <div className="px-4">{children}</div>
          {footer ? <div className="px-4 pt-4">{footer}</div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
