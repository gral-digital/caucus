"use client";

import { useState } from "react";
import { ChatView } from "@/components/chat/ChatView";
import { Sidebar } from "@/components/layout/Sidebar";
import { cn } from "@/lib/cn";
import type { ChatMode } from "@/lib/chatStream";

const MODES: ChatMode[] = ["ricerca", "analisi", "redazione", "giurisprudenza"];

/**
 * Workspace a moduli: Ricerca / Analisi / Redazione.
 *
 * I tre ChatView restano montati in parallelo (visibilità via CSS): cambiare
 * modulo non perde la conversazione in corso né interrompe uno streaming.
 */
export function Workspace() {
  const [mode, setMode] = useState<ChatMode>("ricerca");

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar mode={mode} onSelectMode={setMode} />
      <main className="flex h-full flex-1 flex-col bg-paper">
        {MODES.map((m) => (
          <div
            key={m}
            className={cn("h-full min-h-0 flex-col", m === mode ? "flex" : "hidden")}
          >
            <ChatView mode={m} />
          </div>
        ))}
      </main>
    </div>
  );
}
