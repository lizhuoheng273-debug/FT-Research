type PropagationEvent = { stopPropagation: () => void };
type FocusEvent = { key: string; shiftKey: boolean; preventDefault: () => void };
type FocusTarget = { focus: () => void };

const FOCUSABLE_SELECTOR = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function stopDragActivation(event: PropagationEvent) {
  event.stopPropagation();
}

export function trapDialogFocus(event: FocusEvent, dialog: HTMLElement, activeElement: Element | null) {
  if (event.key !== "Tab") return;

  const focusableElements = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  if (focusableElements.length === 0) {
    event.preventDefault();
    return;
  }

  const firstFocusable = focusableElements[0]!;
  const lastFocusable = focusableElements[focusableElements.length - 1]!;
  const focusOutsideDialog = !dialog.contains(activeElement);
  if (event.shiftKey && (activeElement === firstFocusable || focusOutsideDialog)) {
    event.preventDefault();
    lastFocusable.focus();
  } else if (!event.shiftKey && (activeElement === lastFocusable || focusOutsideDialog)) {
    event.preventDefault();
    firstFocusable.focus();
  }
}

export function restoreFocusOnNextFrame(
  target: FocusTarget | null,
  schedule: (callback: FrameRequestCallback) => number | void = window.requestAnimationFrame,
) {
  schedule(() => target?.focus());
}
