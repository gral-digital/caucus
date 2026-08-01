"use client";

import { Check, ChevronDown, Loader2 } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/cn";
import type { StatusStep } from "@/lib/chatStream";

/**
 * Il "ragionamento" della pipeline, reso visibile: fasi vere (analisi,
 * fonti, verifica citazioni, eventuale riparazione), non un'animazione.
 *
 * Durante il lavoro: riga animata con la fase corrente.
 * A risposta completata: riga compatta collassata («4 fonti · citazioni
 * verificate»), espandibile per rivedere i passaggi.
 */
export function ThinkingSteps({
  steps,
  running,
  summary,
}: {
  steps: StatusStep[];
  running: boolean;
  summary?: string;
}) {
  const [open, setOpen] = useState(false);
  const current = steps[steps.length - 1];
  if (current === undefined) return null;

  if (running) {
    return (
      <div className="flex flex-col gap-1 py-1">
        {steps.slice(0, -1).map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-[12.5px] text-ink-subtle">
            <Check size={12} className="shrink-0 text-ink-subtle/70" />
            <span>{s.detail}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 text-[13px] text-ink-muted">
          <Loader2 size={13} className="shrink-0 animate-spin" />
          <span className="animate-pulse">{current.detail}…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="py-0.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="group flex items-center gap-1.5 text-[12px] text-ink-subtle transition hover:text-ink-muted"
        aria-expanded={open}
      >
        <Check size={12} className="text-emerald-700/70" />
        <span>{summary ?? "Fonti selezionate e citazioni verificate"}</span>
        <ChevronDown
          size={12}
          className={cn("transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <div className="mt-1.5 flex flex-col gap-1 border-l-2 border-paper-border pl-3">
          {steps.map((s, i) => (
            <div key={i} className="text-[12.5px] text-ink-muted">
              {s.detail}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
