import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Self-hosting | Documentazione Caucus" };

export default function Quickstart() {
  return (
    <>
      <h1>Self-hosting</h1>
      <p>
        Caucus è progettato per girare per intero sulla tua macchina o nel tuo
        studio: database, vector store, reranker e, volendo, anche i modelli
        di linguaggio. Questa pagina porta da zero a uno stack funzionante.
        Tempo stimato: <strong>10–15 minuti</strong> con il pacchetto corpus,
        qualche ora se ricostruisci il corpus da zero.
      </p>

      <h2>Prerequisiti</h2>
      <ul>
        <li>
          <strong>Docker</strong> (con Docker Compose) per Postgres, Qdrant e
          Redis;
        </li>
        <li>
          <strong>uv</strong> (gestore Python) e <strong>Python 3.12</strong>;
        </li>
        <li>
          <strong>Node.js ≥ 20</strong> e <strong>pnpm</strong>;
        </li>
        <li>
          una <strong>chiave OpenAI</strong> per la generazione delle risposte
          (default; backend alternativi: Ollama e modelli locali, vedi{" "}
          <a href="#backend-llm">Backend LLM</a>). Con il pacchetto corpus non
          servono chiamate di embedding: paghi solo la generazione, centesimi
          per centinaia di domande.
        </li>
        <li>
          <strong>Disco</strong>: ~8 GB liberi per il corpus completo
          (Postgres + Qdrant); 4 GB di RAM per i container sono sufficienti.
        </li>
      </ul>

      <h2>1. Clona e configura</h2>
      <pre>{`git clone https://github.com/gral-digital/caucus && cd caucus
cp .env.example .env
# apri .env e imposta OPENAI_API_KEY=sk-...`}</pre>
      <p>
        Tutte le opzioni sono variabili d&apos;ambiente documentate in{" "}
        <code>.env.example</code>: backend LLM ed embedding, device del
        reranker, rate limiting, autenticazione. I default vanno bene per un
        primo avvio locale.
      </p>

      <h2>2. Dipendenze e infrastruttura</h2>
      <pre>{`make install     # dipendenze Python (uv) + Node (pnpm)
make up          # Postgres :55432, Qdrant :6333, Redis
make migrate     # schema del database (Alembic)`}</pre>

      <h2>3. Il corpus: importa il pacchetto (consigliato)</h2>
      <p>
        La via rapida è importare il <strong>pacchetto corpus</strong>{" "}
        pubblicato con le release: contiene le tabelle Postgres già popolate e
        gli embedding Qdrant già calcolati. Un solo comando, nessuna chiamata
        API, nessun costo:
      </p>
      <pre>{`make corpus-import SRC=https://github.com/gral-digital/caucus/releases/download/corpus-20260801`}</pre>
      <p>
        Lo script scarica i file (con ripresa automatica se la connessione
        cade), verifica i checksum SHA-256, controlla che lo schema del
        database sia alla revisione giusta e ripristina tabelle e collection.
        Le tabelle utente non vengono toccate. Dettagli su contenuto e licenze
        del pacchetto: <Link href="/docs/corpus">Corpus</Link>.
      </p>
      <p>
        L&apos;alternativa è ricostruire tutto dalle fonti pubbliche
        (Normattiva, EUR-Lex, SentenzeWeb):
      </p>
      <pre>{`make seed-all             # 50 fonti normative + 14 atti UE (~ centesimi di embedding)
make harvest-cassazione   # giurisprudenza, incrementale e resumabile (ore)`}</pre>

      <h2>4. Avvia</h2>
      <pre>{`make dev    # API su :8000, web su :3000`}</pre>
      <p>
        Apri <code>http://localhost:3000/app</code>. Al primo avvio il
        reranker locale (bge-reranker-v2-m3) scarica i pesi e si scalda in
        qualche secondo; le richieste successive non pagano questo costo.
      </p>

      <h2 id="backend-llm">Backend LLM ed embedding</h2>
      <p>
        Il backend di default è OpenAI (<code>gpt-4o</code> per la
        generazione, <code>gpt-4.1-mini</code> per l&apos;espansione query,{" "}
        <code>text-embedding-3-small</code> per gli embedding). Sono
        intercambiabili via env:
      </p>
      <ul>
        <li>
          <code>LLM_BACKEND=ollama</code>: modelli locali via Ollama, per un
          deployment senza alcuna dipendenza cloud;
        </li>
        <li>
          <code>EMBEDDING_BACKEND=local</code>: embedding self-hosted
          (BGE-M3); nota che gli embedding del pacchetto corpus sono
          text-embedding-3-small: cambiando modello di embedding va rifatta
          l&apos;indicizzazione vettoriale;
        </li>
        <li>
          <code>RERANKER_BACKEND=local</code> (default) con{" "}
          <code>RERANKER_DEVICE=mps|cuda|cpu</code>; in assenza delle
          dipendenze il sistema degrada a un reranker keyword e lo segnala nei
          log: le prestazioni misurate valgono solo con il cross-encoder
          attivo.
        </li>
      </ul>
      <p>
        La qualità dichiarata nel <Link href="/docs/benchmark">benchmark</Link>{" "}
        è misurata sulla configurazione di riferimento: se cambi modelli,
        rimisura con <code>make eval</code> prima di fidarti dei numeri.
      </p>

      <h2>Autenticazione e multiutenza</h2>
      <p>
        In self-hosting l&apos;app è aperta di default (nessuna registrazione:
        i dati non lasciano la tua macchina). Per esporre l&apos;istanza a più
        utenti puoi attivare gli account con <code>ACCOUNTS_ENABLED=true</code>:
        registrazione e login con password (Argon2id), sessioni con token
        salvato solo come hash, documenti caricati legati all&apos;utente.
        Per API machine-to-machine c&apos;è il token statico{" "}
        <code>API_AUTH_TOKEN</code> (obbligatorio fuori da{" "}
        <code>APP_ENV=local</code>: il server non parte senza).
      </p>

      <h2>Deploy del frontend su Vercel</h2>
      <p>
        Il frontend è un&apos;app Next.js standard e si deploya su Vercel così
        com&apos;è; l&apos;API (FastAPI + Postgres + Qdrant + reranker) gira
        invece su un server tuo (VPS, Fly.io, Railway…). Configurazione:
      </p>
      <ul>
        <li>
          <strong>Root Directory</strong>: <code>apps/web</code> (il repo è un
          monorepo pnpm; Vercel rileva Next e pnpm da solo);
        </li>
        <li>
          <strong>Variabile d&apos;ambiente</strong>:{" "}
          <code>NEXT_PUBLIC_API_URL</code> = URL pubblico della tua API (es.{" "}
          <code>https://api.tuodominio.it</code>). Le rewrite di Next proxano{" "}
          <code>/api/v1/*</code> verso quell&apos;URL, quindi il browser parla
          solo col dominio del frontend;
        </li>
        <li>
          lo streaming SSE attraversa il proxy senza buffering: la config Next
          disattiva già la compressione sulla rotta della chat. Se davanti
          all&apos;API metti nginx, mantieni le esclusioni descritte sotto in{" "}
          <em>Problemi comuni</em>;
        </li>
        <li>
          CORS: passando dal proxy Next non serve aprire l&apos;API ad altre
          origini; se invece esponi l&apos;API direttamente, configura{" "}
          <code>CORS_ALLOW_ORIGINS</code> con il dominio Vercel.
        </li>
      </ul>

      <h2>Problemi comuni</h2>
      <ul>
        <li>
          <strong>Porte occupate</strong>: Postgres è mappato su :55432
          proprio per non collidere con un Postgres locale; Qdrant usa :6333.
        </li>
        <li>
          <strong>&laquo;reranker_local_deps_missing_fallback_keyword&raquo; nei log</strong>:
          manca <code>sentence-transformers</code> nel venv; rilancia{" "}
          <code>make install</code>. Con il fallback keyword la qualità del
          retrieval cala sensibilmente.
        </li>
        <li>
          <strong>Streaming che arriva &laquo;a blocchi&raquo;</strong>: se
          metti un reverse proxy davanti all&apos;API, disattiva compressione
          e buffering su <code>/api/v1/chat</code> (l&apos;API imposta già{" "}
          <code>X-Accel-Buffering: no</code> e <code>Cache-Control:
          no-transform</code>).
        </li>
        <li>
          <strong>Import corpus rifiutato</strong>: il pacchetto dichiara la
          revisione di schema per cui è stato prodotto: esegui{" "}
          <code>make migrate</code> (o aggiorna il codice) e riprova.
        </li>
      </ul>
    </>
  );
}
