/**
 * Client SSE per /api/v1/chat.
 *
 * Usa `@microsoft/fetch-event-source` perché supporta POST (EventSource stock è GET-only).
 */

import { fetchEventSource } from "@microsoft/fetch-event-source";

export interface ChatRequest {
  question: string;
  corpora?: Array<"codici" | "leggi" | "cassazione">;
  sources?: string[];
  effective_at?: string;
}

export interface RetrievalHitSummary {
  chunk_id: string;
  citation_display: string | null;
  citation_anchor: string | null;
  score: number;
  excerpt: string;
}

export type ChatStreamEvent =
  | { kind: "retrieval"; hits: RetrievalHitSummary[]; latency_ms: number }
  | { kind: "token"; text: string }
  | { kind: "done"; finish_reason: string }
  | { kind: "error"; message: string };

export async function streamChat(
  req: ChatRequest,
  onEvent: (e: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const url = "/api/v1/chat";
  await fetchEventSource(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
    openWhenHidden: true,
    onmessage(ev) {
      if (!ev.data) return;
      const payload = JSON.parse(ev.data);
      switch (ev.event) {
        case "retrieval":
          onEvent({
            kind: "retrieval",
            hits: payload.hits,
            latency_ms: payload.latency_ms,
          });
          break;
        case "token":
          onEvent({ kind: "token", text: payload.text });
          break;
        case "done":
          onEvent({ kind: "done", finish_reason: payload.finish_reason });
          break;
        case "error":
          onEvent({ kind: "error", message: payload.message });
          break;
      }
    },
    onerror(err) {
      onEvent({ kind: "error", message: String(err) });
      throw err; // stop retries
    },
  });
}
