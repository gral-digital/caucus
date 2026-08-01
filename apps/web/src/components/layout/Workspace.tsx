"use client";

import { Menu, PenSquare } from "lucide-react";
import { useState } from "react";
import { ChatView } from "@/components/chat/ChatView";
import { Sidebar } from "@/components/layout/Sidebar";
import { Wordmark } from "@/components/layout/Wordmark";
import { cn } from "@/lib/cn";
import type { ChatMode } from "@/lib/chatStream";

const MODES: ChatMode[] = ["ricerca", "analisi", "redazione", "giurisprudenza"];

/**
 * Workspace a moduli: Ricerca / Analisi / Redazione.
 *
 * I tre ChatView restano montati in parallelo (visibilità via CSS): cambiare
 * modulo non perde la conversazione in corso né interrompe uno streaming.
 *
 * Su mobile (<md) la sidebar è un drawer a scomparsa aperto dalla top bar;
 * su desktop resta fissa come prima.
 */
export function Workspace() {
  const [mode, setMode] = useState<ChatMode>("ricerca");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // «Nuova conversazione» azzera solo il modulo attivo (remount via key),
  // senza ricaricare la pagina: gli altri moduli mantengono il loro stato.
  const [resets, setResets] = useState<Record<ChatMode, number>>({
    ricerca: 0,
    analisi: 0,
    redazione: 0,
    giurisprudenza: 0,
  });

  const newConversation = () =>
    setResets((r) => ({ ...r, [mode]: r[mode] + 1 }));

  return (
    <div className="flex h-dvh w-full overflow-hidden">
      <Sidebar
        mode={mode}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onSelectMode={(m) => {
          setMode(m);
          setSidebarOpen(false);
        }}
        onNewConversation={() => {
          newConversation();
          setSidebarOpen(false);
        }}
      />
      <main className="flex h-full min-w-0 flex-1 flex-col bg-paper">
        {/* Top bar solo mobile: menu, wordmark, nuova conversazione */}
        <div className="flex shrink-0 items-center justify-between border-b border-paper-border/70 px-2 py-2 md:hidden">
          <button
            type="button"
            aria-label="Apri il menu"
            onClick={() => setSidebarOpen(true)}
            className="flex h-10 w-10 items-center justify-center rounded-lg text-ink-muted transition hover:bg-paper-hover hover:text-ink"
          >
            <Menu size={19} />
          </button>
          <Wordmark />
          <button
            type="button"
            aria-label="Nuova conversazione"
            onClick={newConversation}
            className="flex h-10 w-10 items-center justify-center rounded-lg text-ink-muted transition hover:bg-paper-hover hover:text-ink"
          >
            <PenSquare size={17} />
          </button>
        </div>
        {MODES.map((m) => (
          <div
            key={`${m}-${resets[m]}`}
            className={cn("h-full min-h-0 flex-col", m === mode ? "flex" : "hidden")}
          >
            <ChatView mode={m} />
          </div>
        ))}
      </main>
    </div>
  );
}
