import { cn } from "@/lib/cn";
import { parseCitations } from "@/lib/citations";

type Props = {
  role: "user" | "assistant";
  text: string;
  status?: "retrieving" | "streaming" | "done" | "error";
  error?: string;
};

export function MessageBubble({ role, text, status, error }: Props) {
  const segments = role === "assistant" ? parseCitations(text) : null;

  return (
    <div
      className={cn(
        "rounded-md border px-4 py-3 text-[15px]",
        role === "user"
          ? "border-paper-border bg-paper-elevated font-medium"
          : "border-paper-border bg-paper prose-legal",
      )}
    >
      {role === "assistant" && status === "retrieving" ? (
        <span className="text-ink-subtle">Ricerca normativa in corso…</span>
      ) : null}

      {role === "assistant" && segments
        ? segments.map((seg, i) =>
            seg.kind === "text" ? (
              <span key={i} className="whitespace-pre-wrap">
                {seg.text}
              </span>
            ) : (
              <a
                key={i}
                href={seg.href}
                data-cite={`${seg.source}:${seg.part}:${seg.num}`}
                title={seg.display}
              >
                {seg.display}
              </a>
            ),
          )
        : null}

      {role === "user" ? <span className="whitespace-pre-wrap">{text}</span> : null}

      {status === "error" ? (
        <div className="mt-2 text-sm text-accent">
          Errore: {error ?? "sconosciuto"}
        </div>
      ) : null}
    </div>
  );
}
