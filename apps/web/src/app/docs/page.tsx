import Link from "next/link";
import { DOCS_NAV } from "./nav";

export default function DocsIndex() {
  return (
    <>
      <h1>Documentazione</h1>
      <p>
        Caucus è un assistente legale open source per il diritto italiano:
        retrieval-augmented generation su un corpus di testi normativi
        consolidati e giurisprudenza integrale, con un <strong>trust layer</strong>{" "}
        che verifica ogni citazione dopo la generazione e un{" "}
        <strong>benchmark pubblico</strong> (Caucus Bench) che chiunque può
        rieseguire. Codice AGPL-3.0, benchmark MIT.
      </p>
      <p>
        Questa documentazione copre l&apos;uso del prodotto, il self-hosting
        completo (incluso il <Link href="/docs/corpus">pacchetto corpus</Link>{" "}
        già indicizzato, per partire in minuti senza rifare l&apos;ingestione)
        e il funzionamento interno del sistema.
      </p>

      <h2>Da dove cominciare</h2>
      <div className="not-prose grid grid-cols-1 gap-3 sm:grid-cols-2">
        {DOCS_NAV.filter((i) => i.href !== "/docs").map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="rounded-xl border border-paper-border bg-paper p-4 transition hover:bg-paper-hover"
          >
            <div className="text-[14.5px] font-semibold text-ink">{item.label}</div>
            <div className="mt-1 text-[13px] leading-relaxed text-ink-muted">
              {item.description}
            </div>
          </Link>
        ))}
      </div>

      <h2>Il sistema in breve</h2>
      <p>
        Il monorepo contiene quattro componenti principali, con una separazione
        netta: <code>rag-core</code> è l&apos;unica libreria che parla con LLM e
        vector store, <code>ingestion</code> normalizza fonti eterogenee in un
        modello canonico unico, e l&apos;API li consuma.
      </p>
      <pre>{`apps/web              Next.js 15: chat SSE, pannello fonti, pagina /norma
apps/api              FastAPI: /chat (SSE), /search, /norma, auth, export
services/rag-core     retriever ibrido, reranker, query expansion,
                      fusione RRF pesata, schemi Pydantic
services/ingestion    parser Normattiva AKN + EUR-Lex + SentenzeWeb,
                      chunker contestuale, loader idempotenti
benchmark/            Caucus Bench (MIT): gold set + harness di valutazione`}</pre>

      <h2>I tre principi</h2>
      <ol>
        <li>
          <strong>Trust layer prima di tutto.</strong> Ogni citazione normativa
          generata è validata contro il database: esistenza, fonte, vigenza
          temporale, abrogazione. Il sistema preferisce ammettere un gap che
          inventare una norma. Dettagli in{" "}
          <Link href="/docs/trust-layer">Trust layer</Link>.
        </li>
        <li>
          <strong>Il benchmark è l&apos;arbitro.</strong> Ogni modifica di
          qualità si misura su{" "}
          <Link href="/docs/benchmark">Caucus Bench</Link>, mai su impressioni.
          I numeri pubblicati riportano l&apos;intervallo misurato tra run, non
          il picco.
        </li>
        <li>
          <strong>Determinismo dove possibile.</strong> Il lookup per estremi
          espliciti (&laquo;art. 2043 c.c.&raquo;) batte sempre il retrieval
          probabilistico; i segnali deterministici correggono i punteggi
          neurali, mai il contrario.
        </li>
      </ol>

      <h2>Cosa Caucus non è</h2>
      <p>
        Caucus non è un avvocato e le sue risposte non sono pareri legali: è
        uno strumento di ricerca e supporto alla redazione, pensato per
        professionisti che verificano le fonti. Ogni risposta espone le fonti
        consultate e segnala esplicitamente le citazioni che non è riuscito a
        verificare, ma la responsabilità professionale resta di chi firma
        l&apos;atto.
      </p>
    </>
  );
}
