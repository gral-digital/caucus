import { ArrowRight, Github } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { Wordmark } from "@/components/layout/Wordmark";
import { DocsMobileNav, DocsSidebarNav } from "@/components/docs/DocsNav";

export const metadata: Metadata = {
  title: "Documentazione — Caucus",
  description:
    "Documentazione di Caucus: self-hosting, corpus, trust layer, API e benchmark.",
};

export default function DocsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-paper text-ink">
      <header className="sticky top-0 z-20 border-b border-paper-border/70 bg-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-baseline gap-3">
            <Link href="/">
              <Wordmark />
            </Link>
            <span className="text-[13px] text-ink-subtle">Documentazione</span>
          </div>
          <nav className="flex items-center gap-1.5">
            <a
              href="https://github.com/gral-digital/caucus"
              className="hidden items-center gap-1.5 rounded-lg px-3 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink sm:flex"
            >
              <Github size={14} />
              GitHub
            </a>
            <Link
              href="/app"
              className="flex items-center gap-1.5 rounded-lg bg-ink px-3.5 py-2 text-[13px] font-medium text-paper transition hover:bg-ink-muted"
            >
              Apri l&apos;app
              <ArrowRight size={13} />
            </Link>
          </nav>
        </div>
        <div className="border-t border-paper-border/50 md:hidden">
          <DocsMobileNav />
        </div>
      </header>

      <div className="mx-auto flex max-w-6xl gap-10 px-4 py-8 sm:px-6 md:py-10">
        <aside className="sticky top-[76px] hidden h-fit w-52 shrink-0 md:block">
          <DocsSidebarNav />
        </aside>
        <main className="min-w-0 flex-1">
          <article className="prose prose-legal max-w-3xl">{children}</article>
        </main>
      </div>
    </div>
  );
}
