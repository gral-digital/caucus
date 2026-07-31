"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteDocument,
  streamChat,
  uploadDocument,
  type ChatMode,
  type CitationWarnings,
  type RetrievalHitSummary,
  type UploadedDocument,
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

const MODE_COPY: Record<
  ChatMode,
  { title: string; subtitle: string; examples: string[] }
> = {
  ricerca: {
    title: "Ciao, come posso aiutarti?",
    subtitle:
      "Ricerca giuridica sul diritto italiano ed europeo, con citazioni verificate (articolo e comma).",
    examples: [
      "Mi hanno fermato e sono risultato positivo all'etilometro con 1.1 g/l. Come mi difendo?",
      "Ho firmato un contratto e mi sono accorto di un vizio. Cosa posso fare?",
      "Qual è la differenza tra dolo e colpa?",
      "Il mio datore di lavoro mi ha licenziato senza giusta causa. Cosa posso chiedere?",
    ],
  },
  analisi: {
    title: "Analisi documenti",
    subtitle:
      "Allega un contratto o un atto (.docx o .pdf) con la graffetta qui sotto, poi fai la tua domanda: l'analisi collega ogni rilievo alla norma.",
    examples: [
      "Quali clausole di questo contratto sono rischiose per il mio cliente?",
      "Riassumi obblighi, scadenze e penali previsti dal documento",
      "Ci sono clausole vessatorie ai sensi del Codice del Consumo?",
      "La clausola di recesso è conforme alla disciplina legale?",
    ],
  },
  giurisprudenza: {
    title: "Giurisprudenza",
    subtitle:
      "Ricerca negli orientamenti della Cassazione (civile e penale, testo integrale): la risposta cita le decisioni con gli estremi e le norme di riferimento.",
    examples: [
      "Qual è l'orientamento della Cassazione sul licenziamento ritorsivo?",
      "Come valuta la Cassazione la guida in stato di ebbrezza con tasso vicino alla soglia?",
      "Ci sono decisioni recenti sulla responsabilità della banca per operazioni non autorizzate?",
      "Orientamenti sul risarcimento del danno da perdita di chance",
    ],
  },
  redazione: {
    title: "Redazione",
    subtitle:
      "Descrivi l'atto che ti serve: ricevi una bozza completa con citazioni verificate, pronta per l'export in Word.",
    examples: [
      "Prepara una bozza di parere sulla riducibilità di una clausola penale",
      "Redigi una diffida ad adempiere ex art. 1454 c.c. per una fornitura non consegnata",
      "Scrivi una clausola di riservatezza bilaterale per un contratto di collaborazione",
      "Bozza di lettera di contestazione disciplinare a un dipendente",
    ],
  },
};

export function ChatView({ mode = "ricerca" }: { mode?: ChatMode }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const attach = useCallback(async (file: File) => {
    setUploading(true);
    setUploadError(null);
    try {
      const doc = await uploadDocument(file);
      // Restano allegati per tutta la conversazione, finché non rimossi.
      setDocuments((docs) => [...docs.filter((d) => d.id !== doc.id), doc].slice(-3));
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }, []);

  const detach = useCallback((id: string) => {
    setDocuments((docs) => docs.filter((d) => d.id !== id));
    void deleteDocument(id);
  }, []);

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

    const document_ids = documentsRef.current.map((d) => d.id);
    try {
      await streamChat({ question, history, document_ids, mode }, (ev) => {
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
  }, [mode]);

  // Mantieni ref aggiornato ai turn per leggere lo storico senza dipendenze stale
  const turnsRef = useRef<Turn[]>([]);
  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);
  const documentsRef = useRef<UploadedDocument[]>([]);
  useEffect(() => {
    documentsRef.current = documents;
  }, [documents]);

  const isBusy = turns.some(
    (t) => t.status === "retrieving" || t.status === "streaming",
  );
  const empty = turns.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 pb-8 pt-10">
          {empty ? <WelcomeScreen onPick={ask} copy={MODE_COPY[mode]} /> : null}

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
          <QuestionInput
            onAsk={ask}
            disabled={isBusy}
            documents={documents}
            uploading={uploading}
            uploadError={uploadError}
            onAttach={attach}
            onDetach={detach}
          />
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
  copy,
}: {
  onPick: (q: string) => void;
  copy: { title: string; subtitle: string; examples: string[] };
}) {
  return (
    <div className="flex flex-col items-center gap-6 pt-16 text-center">
      <div>
        <h2 className="font-serif text-3xl text-ink">{copy.title}</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-ink-muted">{copy.subtitle}</p>
      </div>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
        {copy.examples.map((q) => (
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
