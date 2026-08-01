"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";
import type { RetrievalHitSummary } from "@/lib/chatStream";
import { cn } from "@/lib/cn";

export function CitationsPanel({ hits }: { hits: RetrievalHitSummary[] }) {
  const [open, setOpen] = useState(false);
  if (hits.length === 0) return null;

  return (
    <div className="mt-2 rounded-xl border border-paper-border bg-paper">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-[13px] text-ink-muted hover:bg-paper-hover/60"
      >
        <span>Fonti consultate · {hits.length}</span>
        <ChevronDown
          size={14}
          className={cn("transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <ul className="flex flex-col divide-y divide-paper-divider border-t border-paper-divider">
          {hits.map((h) => (
            <li key={h.chunk_id} className="px-3 py-2.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[13px] font-medium text-ink">
                  {h.citation_display ?? "fonte non identificata"}
                </span>
                <span className="shrink-0 font-mono text-[11px] text-ink-subtle">
                  {h.score.toFixed(3)}
                </span>
              </div>
              <p className="mt-1 line-clamp-3 text-[12.5px] leading-snug text-ink-muted">
                {h.excerpt}…
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
