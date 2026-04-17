"use client";

import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { preprocessCitations } from "@/lib/citations";
import { cn } from "@/lib/cn";

type Props = {
  role: "user" | "assistant";
  text: string;
  status?: "retrieving" | "streaming" | "done" | "error";
  error?: string;
};

// Componenti custom per il renderer Markdown. In particolare i link (dove
// abbiamo inserito le citazioni) ottengono styling e attributi data-cite.
const markdownComponents = {
  a({ href, children, ...rest }: ComponentProps<"a">) {
    const isCitation = typeof href === "string" && href.startsWith("/norma/");
    return (
      <a
        href={href}
        {...rest}
        data-cite={isCitation ? "true" : undefined}
        className={cn(
          isCitation
            ? "font-medium text-accent decoration-accent/40 underline-offset-[3px] hover:decoration-accent"
            : "text-accent decoration-accent/40 underline-offset-[3px] hover:decoration-accent",
        )}
      >
        {children}
      </a>
    );
  },
  // Headings interni del modello: leggermente più silenziosi di h1 (che è del layout).
  h1({ children }: ComponentProps<"h1">) {
    return <h2 className="mt-4 text-lg font-semibold">{children}</h2>;
  },
  h2({ children }: ComponentProps<"h2">) {
    return <h3 className="mt-3 text-base font-semibold">{children}</h3>;
  },
};

export function MessageBubble({ role, text, status, error }: Props) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-paper-panel px-4 py-2.5 text-[15px] leading-relaxed">
          {text.split("\n").map((line, i) => (
            <span key={i}>
              {line}
              {i < text.split("\n").length - 1 ? <br /> : null}
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (status === "retrieving") {
    return (
      <div className="flex items-center gap-2 py-1 text-sm text-ink-subtle">
        <span className="inline-flex gap-1">
          <Dot delay={0} />
          <Dot delay={150} />
          <Dot delay={300} />
        </span>
        <span>Ricerca normativa…</span>
      </div>
    );
  }

  const processed = preprocessCitations(text);

  return (
    <div className="pb-1">
      <div className="prose prose-legal max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {processed}
        </ReactMarkdown>
      </div>
      {status === "error" ? (
        <div className="mt-2 rounded-md border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent">
          Errore: {error ?? "sconosciuto"}
        </div>
      ) : null}
    </div>
  );
}

function Dot({ delay }: { delay: number }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-ink-subtle"
      style={{ animationDelay: `${delay}ms` }}
    />
  );
}
