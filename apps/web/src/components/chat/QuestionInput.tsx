"use client";

import { ArrowUp, FileText, Paperclip, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { cn } from "@/lib/cn";
import type { UploadedDocument } from "@/lib/chatStream";

type Props = {
  onAsk: (q: string) => void;
  disabled?: boolean;
  documents?: UploadedDocument[];
  uploading?: boolean;
  uploadError?: string | null;
  onAttach?: (file: File) => void;
  onDetach?: (id: string) => void;
};

export function QuestionInput({
  onAsk,
  disabled,
  documents = [],
  uploading = false,
  uploadError,
  onAttach,
  onDetach,
}: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Auto-grow: altezza dinamica fino a 8 righe. Con il campo vuoto si torna
  // all'altezza naturale di una riga: misurare scrollHeight durante il primo
  // layout (larghezza ancora 0) bloccava il campo a 2-3 righe fantasma.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    if (!value) {
      el.style.height = "";
      return;
    }
    el.style.height = "0px";
    const max = 22 * 8; // ~8 righe da 22px
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [value]);

  // Riprendi il focus quando l'input torna attivo (dopo l'invio il campo
  // viene disabilitato durante lo streaming e perdeva il focus).
  useEffect(() => {
    if (!disabled) textareaRef.current?.focus();
  }, [disabled]);

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
      {documents.length > 0 || uploading || uploadError ? (
        <div className="mb-2 flex flex-wrap items-center gap-2 px-1">
          {documents.map((doc) => (
            <span
              key={doc.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-paper-border bg-paper-hover px-2.5 py-1 text-[12.5px] text-ink-muted"
              title={
                doc.truncated
                  ? "Documento lungo: analizzato solo in parte"
                  : `${doc.char_count.toLocaleString("it-IT")} caratteri`
              }
            >
              <FileText size={13} />
              <span className="max-w-[220px] truncate">{doc.filename}</span>
              {doc.truncated ? <span className="text-amber-700">· parziale</span> : null}
              {onDetach ? (
                <button
                  type="button"
                  aria-label={`Rimuovi ${doc.filename}`}
                  onClick={() => onDetach(doc.id)}
                  className="ml-0.5 rounded-full p-0.5 transition hover:bg-paper hover:text-ink"
                >
                  <X size={12} />
                </button>
              ) : null}
            </span>
          ))}
          {uploading ? (
            <span className="text-[12.5px] text-ink-subtle">Carico il documento…</span>
          ) : null}
          {uploadError ? (
            <span className="text-[12.5px] text-red-700">{uploadError}</span>
          ) : null}
        </div>
      ) : null}

      <div
        className={cn(
          "flex items-end gap-2 rounded-3xl border border-paper-border bg-paper px-3 py-2.5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition focus-within:border-ink-subtle/60 focus-within:shadow-[0_2px_10px_rgba(0,0,0,0.06)]",
        )}
      >
        {onAttach ? (
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".docx,.pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onAttach(file);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              aria-label="Allega documento (.docx o .pdf)"
              title="Allega un documento da analizzare (.docx o .pdf)"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-ink-subtle transition hover:bg-paper-hover hover:text-ink disabled:opacity-50"
            >
              <Paperclip size={16} strokeWidth={2} />
            </button>
          </>
        ) : null}
        <textarea
          ref={textareaRef}
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          placeholder={
            documents.length > 0
              ? "Chiedi qualcosa sul documento allegato…"
              : "Chiedi al Codice Civile o Penale…"
          }
          rows={1}
          disabled={disabled}
          // py-[7px]: con line-height 22px la riga singola fa 36px = altezza
          // dei bottoni (h-9), così testo e icone sono allineati in verticale.
          className="max-h-[176px] flex-1 resize-none bg-transparent px-2 py-[7px] text-[15px] leading-[22px] outline-none placeholder:text-ink-subtle disabled:opacity-60"
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
