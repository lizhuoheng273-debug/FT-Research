import { useEffect, useRef } from "react";
import { ChevronDown } from "lucide-react";
import type { ReasoningEffort } from "@/lib/reasoningEffort";
import { cn } from "@/lib/utils";

const modes: { value: ReasoningEffort; label: string }[] = [
  { value: "low", label: "快速" },
  { value: "high", label: "均衡" },
  { value: "max", label: "深入" },
];

export function ReasoningControl({ value, onChange, disabled, loading }: {
  value: ReasoningEffort;
  onChange: (value: ReasoningEffort) => void;
  disabled?: boolean;
  loading: boolean;
}) {
  const root = useRef<HTMLDetailsElement>(null);
  const selected = modes.findIndex(mode => mode.value === value);

  useEffect(() => {
    const dismiss = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) root.current.open = false;
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, []);

  return <details ref={root} className="group relative min-w-0" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) event.currentTarget.open = false;
  }} onKeyDown={event => {
    if (event.key === "Escape" && event.currentTarget.open) {
      event.preventDefault();
      event.stopPropagation();
      event.currentTarget.open = false;
      event.currentTarget.querySelector("summary")?.focus();
    }
  }}>
    <summary aria-label={`推理模式：${modes[selected].label}`} className="flex min-h-9 cursor-pointer list-none items-center gap-1 rounded-lg px-2 text-xs text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 [&::-webkit-details-marker]:hidden">
      {modes[selected].label}<ChevronDown aria-hidden="true" className="h-3 w-3 transition-transform group-open:rotate-180" />
    </summary>
    <div className="absolute bottom-full left-0 z-30 mb-2 w-60 max-w-[calc(100vw-3rem)] rounded-2xl border border-border bg-card p-4 text-card-foreground shadow-md" aria-label="推理模式设置">
      <div className="mb-2 flex justify-between gap-2">
        {modes.map((mode, index) => <button key={mode.value} type="button" disabled={disabled} aria-pressed={selected === index} onClick={() => onChange(mode.value)} className={cn("rounded-md px-1 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 disabled:opacity-40", selected === index ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>{mode.label}</button>)}
      </div>
      <input type="range" aria-label="推理强度" aria-valuetext={modes[selected].label} min={0} max={2} step={1} value={selected} disabled={disabled} onChange={event => {
        const mode = modes[Number(event.target.value)];
        if (mode) onChange(mode.value);
      }} className="block h-6 w-full cursor-pointer accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 disabled:cursor-not-allowed disabled:opacity-40" />
      <p className="mt-2 text-[11px] leading-4 text-muted-foreground">{loading ? "下一条提问生效" : "控制推理投入，深入模式可能等待更久"}</p>
    </div>
  </details>;
}
