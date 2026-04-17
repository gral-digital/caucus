"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat, type RetrievalHitSummary } from "@/lib/chatStream";
import { CitationsPanel } from "./CitationsPanel";
import { MessageBubble } from "./MessageBubble";
import { QuestionInput } from "./QuestionInput";

type Turn = {
  id: string;
  question: string;
  answer: string;
  hits: RetrievalHitSummary[];
  status: "retrieving" | "streaming" | "done" | "error";
  error?: string;
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

    setTurns((t) => [
      ...t,
      { id, question, answer: "", hits: [], status: "retrieving" },
    ]);

    try {
      await streamChat({ question }, (ev) => {
        setTurns((prev) =>
          prev.map((turn) => {
            if (turn.id !== id) return turn;
            switch (ev.kind) {
              case "retrieval":
                return { ...turn, hits: ev.hits, status: "streaming" };
              case "token":
                return { ...turn, answer: turn.answer + ev.text };
              case "done":
                return { ...turn, status: "done" };
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
