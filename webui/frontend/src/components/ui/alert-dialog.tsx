import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";

import { cn } from "@/lib/utils";
import { Button, buttonVariants } from "@/components/ui/button";

/* A confirmation dialog, built on @radix-ui/react-dialog (already installed —
 * @radix-ui/react-alert-dialog is NOT a dependency and we don't add one). This
 * is the destructive-confirm pattern only: an overlay-blocking modal with a
 * cancel + a confirm action. We expose a single <ConfirmDialog> component (not
 * the full compound API) because our only use is "are you sure you want to
 * permanently delete this?" in the Tracker archive view.
 *
 * Radix Dialog gives us focus trap, Esc-to-cancel, and scroll lock; we add the
 * copy + the two buttons. `onConfirm` fires then the dialog closes. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          data-slot="alert-dialog-overlay"
          className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
        />
        <DialogPrimitive.Content
          data-slot="alert-dialog-content"
          // role=alertdialog is the correct a11y role for a destructive confirm.
          role="alertdialog"
          onOpenAutoFocus={(e) => {
            // Keep initial focus off the destructive button — focus Cancel first
            // so an accidental Enter doesn't delete. Radix focuses the first
            // tabbable by default; our layout puts Cancel first, which is what we
            // want, so we just let it be but guard against autofocusing confirm.
            e.preventDefault();
            (e.currentTarget as HTMLElement)
              .querySelector<HTMLButtonElement>("[data-confirm-cancel]")
              ?.focus();
          }}
          className={cn(
            "bg-card text-card-foreground fixed top-[50%] left-[50%] z-[61] grid w-full max-w-md translate-x-[-50%] translate-y-[-50%] gap-3 rounded-lg border border-border p-6 shadow-2xl duration-150 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
          )}
        >
          <DialogPrimitive.Title
            data-slot="alert-dialog-title"
            className="zg-serif text-foreground text-lg leading-tight font-semibold tracking-tight"
          >
            {title}
          </DialogPrimitive.Title>
          {description && (
            <DialogPrimitive.Description
              data-slot="alert-dialog-description"
              className="text-muted-foreground text-sm leading-relaxed"
            >
              {description}
            </DialogPrimitive.Description>
          )}
          <div className="mt-2 flex items-center justify-end gap-2">
            <DialogPrimitive.Close asChild>
              <Button variant="outline" size="sm" data-confirm-cancel>
                {cancelLabel}
              </Button>
            </DialogPrimitive.Close>
            <button
              type="button"
              data-slot="alert-dialog-confirm"
              className={cn(
                buttonVariants({
                  variant: destructive ? "destructive" : "default",
                  size: "sm",
                }),
              )}
              onClick={() => {
                onConfirm();
                onOpenChange(false);
              }}
            >
              {confirmLabel}
            </button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
