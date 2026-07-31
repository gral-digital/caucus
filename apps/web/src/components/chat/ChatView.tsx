"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  streamChat,
  type CitationWarnings,
  type RetrievalHitSummary,
} from "@/lib/chatStream";
import { CitationsPanel } from "./CitationsPanel";
import { MessageBubble } from "./MessageBubble";
import { QuestionInput } from "./QuestionInput";

type Turn = {
  id: string;
  question: string;
  answer: string;
  /** Testo finale del server: citazioni in prosa promosse a tag <cite/>. */
  finalText?: string;
  hits: RetrievalHitSummary[];
  status: "retrieving" | "streaming" | "done" | "error";
  error?: string;
  citationWarnings?: CitationWarnings;
};

const EXAMPLES = [
  "Mi hanno fermato e sono risultato positivo all'etilometro con 1.1 g/l. Come mi difendo?",
  "Ho firmato un contratto e mi sono accorto di un vizio. Cosa posso fare?",
  "Qual è la differenza tra dolo e colpa?",
  "Il mio datore di lavoro mi ha licenziato senza giusta causa. Cosa posso chiedere?",
];

export function ChatView() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll al nuovo messaggio
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const ask = useCallback(async (question: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const id = crypto.randomUUID();

    // Snapshot lo storico PRIMA di aggiungere il nuovo turno: il backend vuole
    // solo i turni passati (non quello corrente).
    const history = turnsToHistory(turnsRef.current);

    setTurns((t) => [
      ...t,
      { id, question, answer: "", hits: [], status: "retrieving" },
    ]);

    try {
      await streamChat({ question, history }, (ev) => {
        setTurns((prev) =>
          prev.map((turn) => {
            if (turn.id !== id) return turn;
            switch (ev.kind) {
              case "retrieval":
                return { ...turn, hits: ev.hits, status: "streaming" };
              case "token":
                return { ...turn, answer: turn.answer + ev.text };
              case "citation_warnings":
                return { ...turn, citationWarnings: ev.warnings };
              case "done":
                return { ...turn, status: "done", finalText: ev.final_text };
              case "error":
                return { ...turn, status: "error", error: ev.message };
              default:
                return turn;
            }
          }),
        );
      }, controller.signal);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setTurns((prev) =>
          prev.map((turn) =>
            turn.id === id
              ? { ...turn, status: "error", error: String(err) }
              : turn,
          ),
        );
      }
    }
  }, []);

  // Mantieni ref aggiornato ai turn per leggere lo storico senza dipendenze stale
  const turnsRef = useRef<Turn[]>([]);
  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  const isBusy = turns.some(
    (t) => t.status === "retrieving" || t.status === "streaming",
  );
  const empty = turns.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 pb-8 pt-10">
          {empty ? <WelcomeScreen onPick={ask} examples={EXAMPLES} /> : null}

          {turns.map((turn) => (
            <div key={turn.id} className="flex flex-col gap-3">
              <MessageBubble role="user" text={turn.question} />
              <MessageBubble
                role="assistant"
                text={turn.answer}
                status={turn.status}
                error={turn.error}
              />
              {turn.citationWarnings &&
              turn.citationWarnings.invalid.length > 0 ? (
                <HallucinationBanner warnings={turn.citationWarnings} />
              ) : null}
              {turn.status === "done" && turn.answer ? (
                <ExportDocxButton turn={turn} />
              ) : null}
              {turn.hits.length > 0 ? <CitationsPanel hits={turn.hits} /> : null}
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-paper-divider/60 bg-paper">
        <div className="mx-auto max-w-3xl px-6 pb-6 pt-3">
          <QuestionInput onAsk={ask} disabled={isBusy} />
        </div>
      </div>
    </div>
  );
}

function ExportDocxButton({ turn }: { turn: Turn }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");

  const exportDocx = useCallback(async () => {
    setState("busy");
    try {
      const res = await fetch("/api/v1/export/docx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: turn.question,
          // finalText ha le citazioni in prosa promosse a tag <cite/> ed è
          // passato dal trust layer; il testo streamato è il fallback.
          answer: turn.finalText ?? turn.answer,
        }),
      });
      if (!res.ok) throw new Error(`export failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download =
        res.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] ??
        "parere_caucus.docx";
      a.click();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("error");
    }
  }, [turn]);

  return (
    <div className="flex items-center gap-2 self-start">
      <button
        type="button"
        onClick={exportDocx}
        disabled={state === "busy"}
        className="rounded-md border border-paper-border bg-paper px-3 py-1.5 text-[13px] text-ink-muted transition hover:bg-paper-hover hover:text-ink disabled:opacity-50"
      >
        {state === "busy" ? "Preparo il documento…" : "Esporta in Word (.docx)"}
      </button>
      {state === "error" ? (
        <span className="text-[12.5px] text-red-700">
          Export non riuscito, riprova.
        </span>
      ) : null}
    </div>
  );
}

function HallucinationBanner({ warnings }: { warnings: CitationWarnings }) {
  return (
    <div className="rounded-md border border-amber-400/50 bg-amber-50 px-3 py-2 text-[13px] text-amber-900">
      <div className="font-medium">
        ⚠ {warnings.invalid.length} citazion{warnings.invalid.length === 1 ? "e" : "i"} non verificat{warnings.invalid.length === 1 ? "a" : "e"}
      </div>
      <div className="mt-1 text-[12.5px] text-amber-800">
        Il modello ha citato articoli non presenti nel corpus indicizzato. Verifica
        direttamente prima di fare affidamento sulle seguenti fonti:
        <ul className="mt-1 list-disc pl-5">
          {warnings.invalid.slice(0, 5).map((c, i) => (
            <li key={i}>
              <span className="font-mono">
                art. {c.num} {c.source}
              </span>
              {c.reason ? <span className="text-amber-700"> — {c.reason}</span> : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function turnsToHistory(
  turns: Turn[],
): { role: "user" | "assistant"; content: string }[] {
  const out: { role: "user" | "assistant"; content: string }[] = [];
  for (const t of turns) {
    if (t.status === "error") continue;
    out.push({ role: "user", content: t.question });
    if (t.answer) out.push({ role: "assistant", content: t.answer });
  }
  return out;
}

function WelcomeScreen({
  onPick,
  examples,
}: {
  onPick: (q: string) => void;
  examples: string[];
}) {
  return (
    <div className="flex flex-col items-center gap-6 pt-16 text-center">
      <div>
        <h2 className="font-serif text-3xl text-ink">Ciao, come posso aiutarti?</h2>
        <p className="mt-2 text-sm text-ink-muted">
          Assistente legale italiano. Rispondo su Codice Civile e Codice Penale con
          citazioni precise (articolo e comma).
        </p>
      </div>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
        {examples.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onPick(q)}
            className="rounded-xl border border-paper-border bg-paper px-4 py-3 text-left text-sm text-ink-muted transition hover:bg-paper-hover hover:text-ink"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
