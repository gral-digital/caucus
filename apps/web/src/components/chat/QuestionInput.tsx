"use client";

import { useState, type FormEvent } from "react";
import { ArrowUp } from "lucide-react";

type Props = { onAsk: (q: string) => void };

export function QuestionInput({ onAsk }: Props) {
  const [value, setValue] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    onAsk(trimmed);
    setValue("");
  };

  return (
    <form onSubmit={submit} className="sticky bottom-0 mt-auto">
      <div className="flex items-end gap-2 rounded-md border border-paper-border bg-paper-elevated p-2 shadow-sm">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Chiedi al Codice Civile o Penale… (es. «qual è la differenza tra dolo e colpa?»)"
          rows={2}
          className="flex-1 resize-none bg-transparent px-2 py-1 text-[15px] outline-none placeholder:text-ink-subtle"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(e);
            }
          }}
        />
        <button
          type="submit"
          disabled={!value.trim()}
          aria-label="Invia"
          className="flex h-9 w-9 items-center justify-center rounded bg-accent text-white transition hover:opacity-90 disabled:opacity-40"
        >
          <ArrowUp size={16} />
        </button>
      </div>
      <p className="mt-1 px-2 text-xs text-ink-subtle">
        Invio = invia · Shift+Invio = a capo
      </p>
    </form>
  );
}
