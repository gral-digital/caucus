"use client";

import {
  Briefcase,
  Building2,
  Car,
  FileText,
  Gavel,
  Landmark,
  PenSquare,
  Scale,
  ScrollText,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import { cn } from "@/lib/cn";

/**
 * Sidebar in stile Claude. Fissa a sinistra, sfondo beige chiarissimo,
 * logo + "Nuova conversazione" in alto, area "Moduli / corpora" al centro,
 * footer con profilo utente in basso.
 *
 * L'elenco dei corpora qui è DISPLAY-ONLY: mostra cosa c'è nell'indice,
 * non seleziona un filtro (quello sarà M2). Il retriever cerca di default
 * su tutti i corpora.
 */
export function Sidebar() {
  return (
    <aside className="flex h-full w-[272px] shrink-0 flex-col border-r border-paper-border bg-paper-panel">
      <div className="flex items-center gap-2 px-4 pb-3 pt-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-paper">
          <ScrollText size={15} strokeWidth={2.2} />
        </div>
        <span className="font-serif text-[17px] tracking-tight text-ink">Caucus</span>
      </div>

      <div className="px-3 pb-3 pt-1">
        <button
          type="button"
          className={cn(
            "flex w-full items-center gap-2 rounded-lg border border-paper-border bg-paper px-3 py-2 text-[13.5px] font-medium text-ink transition hover:bg-paper-hover",
          )}
          onClick={() => {
            if (typeof window !== "undefined") window.location.reload();
          }}
        >
          <PenSquare size={14} />
          Nuova conversazione
        </button>
      </div>

      {/* Moduli (attivi / presto) */}
      <div className="px-4 pt-2 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
        Moduli
      </div>
      <nav className="flex flex-col gap-0.5 px-3 pb-3 pt-1">
        <SidebarLink active icon={<ScrollText size={14} />} label="Chiedi al Codice" />
        <SidebarLink icon={<FileText size={14} />} label="Analisi documenti" soon />
        <SidebarLink icon={<Gavel size={14} />} label="Drafting atti" soon />
        <SidebarLink icon={<Scale size={14} />} label="Giurisprudenza" soon />
      </nav>

      {/* Corpora indicizzati */}
      <div className="px-4 pt-2 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
        Corpus normativo
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-2 pt-1">
        <CorpusGroup label="Codici" items={CORPUS_CODICI} />
        <CorpusGroup label="Testi Unici" items={CORPUS_TU} />
        <CorpusGroup label="Leggi" items={CORPUS_LEGGI} />
        <CorpusGroup label="Compliance" items={CORPUS_COMPLIANCE} />
        <CorpusGroup label="Diritto UE" items={CORPUS_UE} />
        <CorpusGroup label="Giurisprudenza" items={CORPUS_GIURISPRUDENZA} />
        <p className="mt-3 px-2 text-[11px] leading-relaxed text-ink-subtle">
          Fonti aggiornate a vigenti al 17/04/2026. Cassazione e altre
          leggi speciali in arrivo.
        </p>
      </div>

      <div className="border-t border-paper-border/70 px-3 py-3">
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
        >
          <Settings size={14} />
          Impostazioni
        </button>
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------

type CorpusItem = {
  short: string;
  label: string;
  icon?: ReactNode;
};

const CORPUS_CODICI: CorpusItem[] = [
  { short: "cc", label: "Codice Civile", icon: <Scale size={12} /> },
  { short: "cp", label: "Codice Penale", icon: <Gavel size={12} /> },
  { short: "cpc", label: "Procedura Civile" },
  { short: "cpp", label: "Procedura Penale" },
  { short: "cost", label: "Costituzione", icon: <Landmark size={12} /> },
  { short: "cds", label: "Codice della Strada", icon: <Car size={12} /> },
  { short: "cdc", label: "Codice del Consumo" },
  { short: "ccii", label: "Crisi d'Impresa" },
  { short: "ccp", label: "Contratti Pubblici" },
  { short: "cad", label: "Amm. Digitale" },
  { short: "cts", label: "Terzo Settore" },
  { short: "cpriv", label: "Privacy", icon: <ShieldCheck size={12} /> },
];

const CORPUS_TU: CorpusItem[] = [
  { short: "tus", label: "TU Stupefacenti" },
  { short: "tui", label: "TU Immigrazione" },
  { short: "tue", label: "TU Edilizia", icon: <Building2 size={12} /> },
  { short: "tusl", label: "TU Sicurezza Lavoro" },
  { short: "tub", label: "TU Bancario" },
  { short: "tuf", label: "TU Finanza" },
  { short: "tuir", label: "TU Imposte Redditi" },
];

const CORPUS_LEGGI: CorpusItem[] = [
  { short: "l241", label: "L. 241/1990 proc. amm." },
  { short: "stat", label: "Statuto Lavoratori", icon: <Briefcase size={12} /> },
  { short: "l689", label: "L. 689/1981 depen." },
  { short: "lpf", label: "L. 247/2012 forense" },
  { short: "l604", label: "L. 604/1966 licenziamenti" },
  { short: "l392", label: "L. 392/1978 locazioni" },
  { short: "l898", label: "L. 898/1970 divorzio" },
  { short: "l76", label: "L. 76/2016 unioni civili" },
  { short: "l91", label: "L. 91/1992 cittadinanza" },
];

const CORPUS_COMPLIANCE: CorpusItem[] = [
  { short: "dlgs231", label: "D.Lgs. 231/2001 enti" },
  { short: "aml", label: "Antiriciclaggio 231/2007" },
  { short: "l190", label: "Anticorruzione 190/2012" },
  { short: "dlgs33", label: "Trasparenza 33/2013" },
  { short: "cam", label: "Codice Antimafia" },
  { short: "wb", label: "Whistleblowing 24/2023" },
  { short: "tua", label: "TU Ambiente" },
  { short: "tupi", label: "TU Pubblico Impiego" },
  { short: "cpa", label: "Processo Amministrativo" },
  { short: "cpt", label: "Processo Tributario" },
  { short: "tuel", label: "TU Enti Locali" },
  { short: "cap", label: "Codice Assicurazioni" },
  { short: "iva", label: "IVA 633/1972" },
  { short: "tumat", label: "TU Maternità" },
  { short: "lav81", label: "Contratti Lavoro 81/2015" },
];

const CORPUS_UE: CorpusItem[] = [
  { short: "gdpr", label: "GDPR", icon: <ShieldCheck size={12} /> },
  { short: "aiact", label: "AI Act" },
  { short: "nis2", label: "NIS2" },
  { short: "dora", label: "DORA" },
  { short: "mica", label: "MiCA" },
  { short: "dsa", label: "DSA / DMA" },
  { short: "eidas", label: "eIDAS" },
  { short: "psd2", label: "PSD2 / MiFID II" },
];

const CORPUS_GIURISPRUDENZA: CorpusItem[] = [
  { short: "cass-civ", label: "Cassazione Civile", icon: <Gavel size={12} /> },
  { short: "cass-pen", label: "Cassazione Penale", icon: <Gavel size={12} /> },
];

function CorpusGroup({ label, items }: { label: string; items: CorpusItem[] }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="mb-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-[12px] font-medium text-ink-muted hover:bg-paper-hover/50"
      >
        <span>{label}</span>
        <span className="font-mono text-[10px] text-ink-subtle">{items.length}</span>
      </button>
      {open ? (
        <ul className="mt-0.5 flex flex-col gap-px">
          {items.map((it) => (
            <li
              key={it.short}
              className="flex items-center gap-1.5 rounded px-2 py-1 text-[12.5px] text-ink-muted"
              title={it.label}
            >
              {it.icon ? (
                <span className="text-ink-subtle">{it.icon}</span>
              ) : (
                <span className="inline-block h-[4px] w-[4px] rounded-full bg-ink-subtle" />
              )}
              <span className="truncate">{it.label}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function SidebarLink({
  icon,
  label,
  active,
  soon,
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  soon?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={soon}
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
