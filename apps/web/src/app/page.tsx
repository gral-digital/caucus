import { ChatView } from "@/components/chat/ChatView";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-6 py-10">
      <header className="mb-8 border-b border-paper-border pb-6">
        <h1 className="font-serif text-4xl tracking-tight">Avvocato</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Assistente legale italiano. Le risposte citano sempre articoli e commi
          del Codice Civile o Penale.
        </p>
      </header>

      <ChatView />

      <footer className="mt-10 text-xs text-ink-subtle">
        Strumento di supporto — non sostituisce il parere dell&apos;avvocato.
        Verificare sempre la vigenza della norma.
      </footer>
    </main>
  );
}
