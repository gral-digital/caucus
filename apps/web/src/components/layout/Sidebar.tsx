"use client";

import {
  BookOpen,
  FileText,
  Gavel,
  PenSquare,
  Scale,
  ScrollText,
  Settings,
  X,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import type { ChatMode } from "@/lib/chatStream";

/**
 * Sidebar minimale: logo, nuova conversazione, moduli, footer.
 *
 * Il catalogo delle fonti NON vive più qui (era un elenco di 50+ voci sempre
 * aperto): sta nel pannello «Fonti» richiamabile dal footer — visibile quando
 * serve, invisibile quando si lavora.
 */
export function Sidebar({
  mode,
  onSelectMode,
}: {
  mode: ChatMode;
  onSelectMode: (mode: ChatMode) => void;
}) {
  const [fontiOpen, setFontiOpen] = useState(false);

  return (
    <aside className="flex h-full w-[248px] shrink-0 flex-col border-r border-paper-border bg-paper-panel">
      <div className="flex items-center gap-2 px-4 pb-4 pt-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-paper">
          <ScrollText size={15} strokeWidth={2.2} />
        </div>
        <span className="font-serif text-[17px] tracking-tight text-ink">Caucus</span>
      </div>

      <div className="px-3 pb-4">
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-lg border border-paper-border bg-paper px-3 py-2 text-[13.5px] font-medium text-ink transition hover:bg-paper-hover"
          onClick={() => {
            if (typeof window !== "undefined") window.location.reload();
          }}
        >
          <PenSquare size={14} />
          Nuova conversazione
        </button>
      </div>

      <div className="px-4 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
        Moduli
      </div>
      <nav className="flex flex-col gap-0.5 px-3 pb-3 pt-1">
        <SidebarLink
          active={mode === "ricerca"}
          icon={<ScrollText size={14} />}
          label="Ricerca giuridica"
          onClick={() => onSelectMode("ricerca")}
        />
        <SidebarLink
          active={mode === "analisi"}
          icon={<FileText size={14} />}
          label="Analisi documenti"
          onClick={() => onSelectMode("analisi")}
        />
        <SidebarLink
          active={mode === "redazione"}
          icon={<Gavel size={14} />}
          label="Redazione"
          onClick={() => onSelectMode("redazione")}
        />
        <SidebarLink
          active={mode === "giurisprudenza"}
          icon={<Scale size={14} />}
          label="Giurisprudenza"
          onClick={() => onSelectMode("giurisprudenza")}
        />
      </nav>

      <div className="flex-1" />

      <div className="border-t border-paper-border/70 px-3 py-3">
        <button
          type="button"
          onClick={() => setFontiOpen(true)}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
        >
          <BookOpen size={14} />
          <span className="flex-1 text-left">Fonti del corpus</span>
          <span className="font-mono text-[10.5px] text-ink-subtle">65</span>
        </button>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
        >
          <Settings size={14} />
          Impostazioni
        </button>
      </div>

      {fontiOpen ? <FontiPanel onClose={() => setFontiOpen(false)} /> : null}
    </aside>
  );
}

// ---------------------------------------------------------------------------

const FONTI: { label: string; items: string[] }[] = [
  {
    label: "Codici",
    items: [
      "Codice Civile",
      "Codice Penale",
      "Procedura Civile",
      "Procedura Penale",
      "Costituzione",
      "Codice della Strada",
      "Codice del Consumo",
      "Crisi d'Impresa",
      "Contratti Pubblici",
      "Amministrazione Digitale",
      "Terzo Settore",
      "Codice Privacy",
      "Codice Antimafia",
      "Codice Assicurazioni",
      "Beni Culturali",
      "Codice della Navigazione",
      "Processo Amministrativo",
      "Processo Tributario",
    ],
  },
  {
    label: "Testi Unici",
    items: [
      "Stupefacenti",
      "Immigrazione",
      "Edilizia",
      "Sicurezza sul Lavoro",
      "Bancario (TUB)",
      "Finanza (TUF)",
      "Imposte sui Redditi (TUIR)",
      "Ambiente",
      "Pubblico Impiego",
      "Enti Locali",
      "Maternità e Paternità",
      "Documentazione Amministrativa",
    ],
  },
  {
    label: "Leggi e compliance",
    items: [
      "Procedimento amministrativo (241/1990)",
      "Statuto dei Lavoratori",
      "Licenziamenti (604/1966)",
      "Locazioni (392/1978)",
      "Divorzio (898/1970)",
      "Unioni civili (76/2016)",
      "Cittadinanza (91/1992)",
      "Depenalizzazione (689/1981)",
      "Professione forense (247/2012)",
      "Responsabilità enti (231/2001)",
      "Antiriciclaggio (231/2007)",
      "Anticorruzione (190/2012)",
      "Trasparenza (33/2013)",
      "Whistleblowing (24/2023)",
      "Contratti di lavoro (81/2015)",
      "IVA e accertamento",
    ],
  },
  {
    label: "Diritto UE",
    items: [
      "GDPR",
      "AI Act",
      "NIS2",
      "DORA",
      "MiCA",
      "DSA / DMA",
      "eIDAS",
      "PSD2 / MiFID II",
      "Direttive consumatori, whistleblowing, AML, ePrivacy",
    ],
  },
];

function FontiPanel({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/20 p-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-paper-border bg-paper p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Fonti del corpus"
      >
        <div className="mb-1 flex items-start justify-between">
          <h2 className="font-serif text-xl text-ink">Fonti del corpus</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Chiudi"
            className="rounded-full p-1.5 text-ink-subtle transition hover:bg-paper-hover hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>
        <p className="mb-5 text-[13px] leading-relaxed text-ink-muted">
          Testi consolidati Normattiva e atti EUR-Lex, con filtro di vigenza; ogni
          citazione nelle risposte è verificata contro queste fonti. In più,
          giurisprudenza di Cassazione civile e penale (testo integrale
          anonimizzato, corpus in crescita).
        </p>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          {FONTI.map((group) => (
            <div key={group.label}>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
                {group.label}
              </div>
              <ul className="flex flex-col gap-0.5">
                {group.items.map((it) => (
                  <li key={it} className="text-[13px] leading-relaxed text-ink-muted">
                    {it}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-5 border-t border-paper-border/70 pt-3 text-[11.5px] text-ink-subtle">
          Fonti normative aggiornate ai testi vigenti al 17/04/2026.
        </p>
      </div>
    </div>
  );
}

function SidebarLink({
  icon,
  label,
  active,
  soon,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  soon?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      disabled={soon}
      onClick={onClick}
      className={cn(
        "group flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13.5px] transition",
        active
          ? "bg-paper text-ink"
          : "text-ink-muted hover:bg-paper-hover hover:text-ink",
        soon && "cursor-not-allowed opacity-60 hover:bg-transparent hover:text-ink-muted",
      )}
    >
      {icon}
      <span className="flex-1">{label}</span>
      {soon ? (
        <span className="rounded-full bg-paper-hover px-1.5 py-0.5 text-[10px] font-medium text-ink-subtle">
          presto
        </span>
      ) : null}
    </button>
  );
}
