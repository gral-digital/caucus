"use client";

import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { cn } from "@/lib/cn";

type Props = {
  onAsk: (q: string) => void;
  disabled?: boolean;
};

export function QuestionInput({ onAsk, disabled }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-grow: altezza dinamica fino a 8 righe
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    const max = 22 * 8; // ~8 righe da 22px
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [value]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onAsk(trimmed);
    setValue("");
  };

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <form onSubmit={submit} className="w-full">
      <div
        className={cn(
          "flex items-end gap-2 rounded-3xl border border-paper-border bg-paper px-3 py-2.5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition focus-within:border-ink-subtle/60 focus-within:shadow-[0_2px_10px_rgba(0,0,0,0.06)]",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Chiedi al Codice Civile o Penale…"
          rows={1}
          disabled={disabled}
          className="max-h-[176px] flex-1 resize-none bg-transparent px-2 py-1 text-[15px] leading-[22px] outline-none placeholder:text-ink-subtle disabled:opacity-60"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(e);
            }
          }}
        />
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Invia"
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition",
            canSend
              ? "bg-ink text-paper hover:bg-ink-muted"
              : "bg-paper-hover text-ink-subtle",
          )}
        >
          <ArrowUp size={16} strokeWidth={2.2} />
        </button>
      </div>
      <p className="mt-2 px-2 text-[11px] text-ink-subtle">
        Invio per inviare · Shift+Invio per andare a capo. L&apos;assistente non sostituisce
        il parere di un avvocato.
      </p>
    </form>
  );
}
