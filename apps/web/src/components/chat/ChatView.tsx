"use client";

import { useCallback, useRef, useState } from "react";
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

export function ChatView() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const abortRef = useRef<AbortController | null>(null);

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

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-6">
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
      <QuestionInput onAsk={ask} />
    </div>
  );
}
