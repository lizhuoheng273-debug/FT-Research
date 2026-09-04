import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function MarketReviewModal({ open, title, onClose, children }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    triggerRef.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      triggerRef.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-0 sm:p-6" role="dialog" aria-modal="true" aria-label={title}>
    <button className="absolute inset-0" aria-label="关闭弹层" onClick={onClose} />
    <div className="relative z-10 flex h-full max-h-[100dvh] w-full flex-col overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-2xl sm:h-auto sm:max-h-[85dvh] sm:max-w-5xl">
      <div className="flex shrink-0 items-center justify-between border-b border-border/60 px-4 py-3 sm:px-6">
        <h2 className="text-base font-semibold">{title}</h2>
        <button ref={closeRef} onClick={onClose} aria-label="关闭" className="rounded-lg border border-border/70 p-2 text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-6">{children}</div>
    </div>
  </div>;
}
