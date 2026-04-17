import type { RetrievalHitSummary } from "@/lib/chatStream";

export function CitationsPanel({ hits }: { hits: RetrievalHitSummary[] }) {
  return (
    <details className="rounded-md border border-paper-border bg-paper-elevated/50 px-4 py-2 text-sm">
      <summary className="cursor-pointer text-ink-muted">
        Fonti utilizzate ({hits.length})
      </summary>
      <ul className="mt-2 flex flex-col gap-2">
        {hits.map((h) => (
          <li
            key={h.chunk_id}
            className="rounded border border-paper-border bg-paper p-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">
                {h.citation_display ?? "—"}
              </span>
              <span className="text-xs text-ink-subtle">
                score {h.score.toFixed(3)}
              </span>
            </div>
            <p className="mt-1 text-ink-muted">{h.excerpt}…</p>
          </li>
        ))}
      </ul>
    </details>
  );
}
