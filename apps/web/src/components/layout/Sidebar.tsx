"use client";

import {
  BookMarked,
  BookOpen,
  FileText,
  Gavel,
  LogOut,
  PenSquare,
  Scale,
  ScrollText,
  Settings,
  X,
} from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/components/auth/AuthGate";
import { type ReactNode, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import type { ChatMode } from "@/lib/chatStream";
import { loadSettings, saveSettings } from "@/lib/settings";
import { Wordmark } from "./Wordmark";

/**
 * Sidebar minimale: logo, nuova conversazione, moduli, footer.
 *
 * Il catalogo delle fonti NON vive più qui (era un elenco di 50+ voci sempre
 * aperto): sta nel pannello «Fonti» richiamabile dal footer, visibile quando
 * serve e invisibile quando si lavora.
 *
 * Su mobile (<md) è un drawer a scomparsa controllato da `open`/`onClose`;
 * su desktop è sempre visibile e le due prop sono ininfluenti.
 */
export function Sidebar({
  mode,
  open = false,
  onClose,
  onSelectMode,
  onNewConversation,
}: {
  mode: ChatMode;
  open?: boolean;
  onClose?: () => void;
  onSelectMode: (mode: ChatMode) => void;
  onNewConversation?: () => void;
}) {
  const [fontiOpen, setFontiOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <>
      {open ? (
        <div
          className="fixed inset-0 z-30 bg-ink/25 backdrop-blur-[1px] md:hidden"
          onClick={onClose}
          role="presentation"
        />
      ) : null}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex h-full w-[280px] max-w-[85vw] shrink-0 flex-col border-r border-paper-border bg-paper-panel transition-transform duration-200 ease-out md:static md:z-auto md:w-[248px] md:max-w-none md:translate-x-0 md:transition-none",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
      <div className="px-4 pb-4 pt-5">
        <Wordmark />
      </div>

      <div className="px-3 pb-4">
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-lg border border-paper-border bg-paper px-3 py-2 text-[13.5px] font-medium text-ink transition hover:bg-paper-hover"
          onClick={onNewConversation}
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
        <AccountBadge />
        <button
          type="button"
          onClick={() => setFontiOpen(true)}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
        >
          <BookOpen size={14} />
          <span className="flex-1 text-left">Fonti del corpus</span>
          <span className="font-mono text-[10.5px] text-ink-subtle">65</span>
        </button>
        <Link
          href="/docs"
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
        >
          <BookMarked size={14} />
          Documentazione
        </Link>
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
        >
          <Settings size={14} />
          Impostazioni
        </button>
      </div>

        {fontiOpen ? <FontiPanel onClose={() => setFontiOpen(false)} /> : null}
        {settingsOpen ? (
          <SettingsPanel onClose={() => setSettingsOpen(false)} />
        ) : null}
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------

function SettingsPanel({ onClose }: { onClose: () => void }) {
  const { user, accountsEnabled, logout } = useAuth();
  const [settings, setSettings] = useState(loadSettings);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const setEffectiveAt = (value: string | null) => {
    const next = { ...settings, effectiveAt: value };
    setSettings(next);
    saveSettings(next);
  };

  // Portal su body: vedi FontiPanel.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/25 p-4 backdrop-blur-[2px] sm:p-8"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-[88dvh] w-full max-w-lg flex-col rounded-2xl border border-paper-border bg-paper shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Impostazioni"
      >
        <div className="flex items-center justify-between border-b border-paper-border/70 px-5 pb-4 pt-5 sm:px-6">
          <h2 className="font-serif text-[22px] tracking-tight text-ink">
            Impostazioni
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Chiudi"
            className="-mr-2 rounded-full p-1.5 text-ink-subtle transition hover:bg-paper-hover hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex flex-col gap-6 overflow-y-auto px-5 py-5 sm:px-6">
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
              Ricerca
            </h3>
            <div className="mt-2 rounded-xl border border-paper-border bg-paper-panel/60 p-4">
              <label
                htmlFor="effective-at"
                className="text-[13.5px] font-medium text-ink"
              >
                Data di vigenza
              </label>
              <p className="mt-1 text-[12.5px] leading-relaxed text-ink-muted">
                Le risposte si basano sui testi vigenti a questa data: gli
                articoli entrati in vigore dopo non vengono considerati.
                Lascia vuoto per usare la data odierna.
              </p>
              <div className="mt-2.5 flex items-center gap-2">
                <input
                  id="effective-at"
                  type="date"
                  value={settings.effectiveAt ?? ""}
                  onChange={(e) => setEffectiveAt(e.target.value || null)}
                  className="rounded-lg border border-paper-border bg-paper px-3 py-1.5 text-[13.5px] text-ink outline-none transition focus:border-ink-subtle/60"
                />
                {settings.effectiveAt ? (
                  <button
                    type="button"
                    onClick={() => setEffectiveAt(null)}
                    className="rounded-lg px-2.5 py-1.5 text-[12.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
                  >
                    Torna a oggi
                  </button>
                ) : (
                  <span className="text-[12.5px] text-ink-subtle">oggi</span>
                )}
              </div>
              {settings.effectiveAt ? (
                <p className="mt-2 text-[12px] text-accent">
                  Attiva: le prossime domande usano i testi vigenti al{" "}
                  {new Date(settings.effectiveAt + "T00:00:00").toLocaleDateString("it-IT")}.
                </p>
              ) : null}
            </div>
          </section>

          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
              Account
            </h3>
            <div className="mt-2 rounded-xl border border-paper-border bg-paper-panel/60 p-4">
              {accountsEnabled && user ? (
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-[13.5px] font-medium text-ink">
                      {user.email}
                    </div>
                    <div className="mt-0.5 text-[12.5px] text-ink-muted">
                      I documenti caricati sono legati a questo account.
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void logout()}
                    className="flex shrink-0 items-center gap-1.5 rounded-lg border border-paper-border bg-paper px-3 py-1.5 text-[13px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
                  >
                    <LogOut size={13} />
                    Esci
                  </button>
                </div>
              ) : (
                <p className="text-[13px] leading-relaxed text-ink-muted">
                  Istanza self-hosted: nessun account necessario, i dati non
                  lasciano questa macchina. Gli account si attivano con{" "}
                  <code className="rounded bg-paper-hover px-1 py-0.5 font-mono text-[11.5px]">
                    ACCOUNTS_ENABLED=true
                  </code>
                  .
                </p>
              )}
            </div>
          </section>

          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
              Istanza
            </h3>
            <div className="mt-2 flex flex-col gap-1 rounded-xl border border-paper-border bg-paper-panel/60 p-4 text-[13px] text-ink-muted">
              <a href="/docs" className="text-accent hover:underline">
                Documentazione
              </a>
              <a
                href="https://github.com/gral-digital/caucus"
                className="text-accent hover:underline"
              >
                Codice sorgente e segnalazioni
              </a>
              <p className="mt-1.5 text-[12.5px] leading-relaxed">
                Caucus è software libero (AGPL-3.0). L&apos;assistente non
                sostituisce il parere di un avvocato.
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>,
    document.body,
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

  // Portal su body: l'aside è transform-ata (drawer mobile) e diventerebbe
  // il containing block del `fixed`, confinando il modale nella sidebar.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/25 p-4 backdrop-blur-[2px] sm:p-8"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-[88dvh] w-full max-w-4xl flex-col rounded-2xl border border-paper-border bg-paper shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Fonti del corpus"
      >
        <div className="flex items-start justify-between gap-4 border-b border-paper-border/70 px-5 pb-4 pt-5 sm:px-8 sm:pt-6">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-4">
            <h2 className="font-serif text-[22px] tracking-tight text-ink">
              Fonti del corpus
            </h2>
            <span className="text-[12.5px] text-ink-subtle">
              Testi consolidati Normattiva ed EUR-Lex · ogni citazione è verificata
              contro queste fonti
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Chiudi"
            className="-mr-2 rounded-full p-1.5 text-ink-subtle transition hover:bg-paper-hover hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>

        <div className="grid flex-1 grid-cols-1 gap-x-8 gap-y-6 overflow-y-auto px-5 py-5 sm:grid-cols-2 sm:px-8 sm:py-6 md:grid-cols-4">
          {FONTI.map((group) => (
            <div key={group.label}>
              <div className="mb-2 flex items-baseline justify-between border-b border-paper-border/60 pb-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                  {group.label}
                </span>
                <span className="font-mono text-[10px] text-ink-subtle">
                  {group.items.length}
                </span>
              </div>
              <ul className="flex flex-col gap-[3px]">
                {group.items.map((it) => (
                  <li key={it} className="text-[12px] leading-[1.5] text-ink-muted">
                    {it}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-1.5 rounded-b-2xl border-t border-paper-border/70 bg-paper-panel px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <span className="text-[12px] text-ink-muted">
            + Giurisprudenza: Cassazione civile e penale, Consiglio di Stato e
            TAR (testo integrale, corpus in crescita)
          </span>
          <span className="text-[11.5px] text-ink-subtle">
            Testi vigenti al 17/04/2026
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function AccountBadge() {
  const { user, accountsEnabled, logout } = useAuth();
  if (!accountsEnabled || !user) return null;
  return (
    <div className="mb-1 flex items-center gap-2 rounded-lg px-2 py-2">
      <span
        className="min-w-0 flex-1 truncate text-[12.5px] text-ink-muted"
        title={user.email}
      >
        {user.email}
      </span>
      <button
        type="button"
        onClick={() => void logout()}
        className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[12px] text-ink-subtle transition hover:bg-paper-hover hover:text-ink"
        aria-label="Esci"
      >
        <LogOut size={12} />
        Esci
      </button>
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
