import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "API | Documentazione Caucus" };

export default function ApiDocs() {
  return (
    <>
      <h1>API</h1>
      <p>
        L&apos;API è FastAPI, tutta sotto <code>/api/v1</code>. La chat è
        streaming SSE; il resto è JSON. Lo schema OpenAPI generato è
        disponibile su <code>/docs</code> dell&apos;API stessa (Swagger UI, in
        locale <code>http://localhost:8000/docs</code>); questa pagina descrive
        il contratto e le scelte non ovvie.
      </p>

      <h2>Autenticazione</h2>
      <ul>
        <li>
          <strong>Self-hosting single-user</strong> (default,{" "}
          <code>APP_ENV=local</code>): nessuna autenticazione richiesta.
        </li>
        <li>
          <strong>Token statico</strong>: fuori da <code>APP_ENV=local</code>{" "}
          il server esige <code>API_AUTH_TOKEN</code> (fail-closed: senza
          token configurato non parte). Le richieste lo passano come{" "}
          <code>Authorization: Bearer &lt;token&gt;</code>.
        </li>
        <li>
          <strong>Account</strong> (<code>ACCOUNTS_ENABLED=true</code>):
          sessioni utente via <code>/auth/*</code>; il token di sessione è
          restituito al login e va passato come bearer. Lato server è
          conservato solo il suo hash SHA-256.
        </li>
      </ul>
      <p>
        Rate limiting per IP configurabile via{" "}
        <code>RATE_LIMIT_PER_MINUTE</code> (0 = disattivato).
      </p>

      <h2>Endpoint</h2>
      <table>
        <thead>
          <tr>
            <th>Endpoint</th>
            <th>Descrizione</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>POST /chat</code></td>
            <td>Risposta in streaming SSE con retrieval e trust layer</td>
          </tr>
          <tr>
            <td><code>POST /search</code></td>
            <td>Solo retrieval: hit rankati senza generazione</td>
          </tr>
          <tr>
            <td><code>GET /norma/{"{source}"}/art/{"{num}"}</code></td>
            <td>Testo consolidato di un articolo (es. <code>/norma/cc/art/2043</code>)</td>
          </tr>
          <tr>
            <td><code>POST /documents</code> · <code>DELETE /documents/{"{id}"}</code></td>
            <td>Upload (multipart, .docx/.pdf) e rimozione documenti per l&apos;analisi</td>
          </tr>
          <tr>
            <td><code>POST /export/docx</code></td>
            <td>Esporta una risposta in .docx; ri-verifica le citazioni server-side</td>
          </tr>
          <tr>
            <td><code>POST /citations/validate</code></td>
            <td>Trust layer standalone: verifica le citazioni di un testo qualsiasi</td>
          </tr>
          <tr>
            <td><code>POST /auth/register|login|logout</code> · <code>GET /auth/me|config</code></td>
            <td>Gestione account (attivi solo con <code>ACCOUNTS_ENABLED</code>)</td>
          </tr>
          <tr>
            <td><code>GET /health/live</code> · <code>GET /health/ready</code></td>
            <td>Liveness / readiness (DB e vector store raggiungibili)</td>
          </tr>
        </tbody>
      </table>

      <h2>POST /chat: lo stream</h2>
      <p>Richiesta:</p>
      <pre>{`{
  "question": "Recesso dal contratto per vizio della cosa venduta",
  "history":  [{"role": "user", "content": "..."},
               {"role": "assistant", "content": "..."}],   // opzionale
  "mode": "ricerca",          // ricerca | analisi | redazione | giurisprudenza
  "document_ids": ["..."],    // opzionale, documenti caricati
  "corpora": ["codici"],      // opzionale; il primo è il corpus primario
  "effective_at": "2026-08-01" // opzionale, data di vigenza (default oggi)
}`}</pre>
      <p>
        La risposta è <code>text/event-stream</code>. Eventi, nell&apos;ordine
        tipico:
      </p>
      <table>
        <thead>
          <tr>
            <th>Evento</th>
            <th>Payload</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>status</code></td>
            <td>
              <code>{"{stage, detail}"}</code>: le fasi reali della pipeline
              (instradamento, espansione, retrieval, reranking, generazione,
              verifica, riparazione), emesse quando accadono
            </td>
          </tr>
          <tr>
            <td><code>retrieval</code></td>
            <td>
              <code>{"{hits: [{chunk_id, citation_display, citation_anchor, score, excerpt}], latency_ms}"}</code>
            </td>
          </tr>
          <tr>
            <td><code>token</code></td>
            <td><code>{"{text}"}</code>: frammento incrementale della risposta</td>
          </tr>
          <tr>
            <td><code>citation_warnings</code></td>
            <td>
              <code>{"{valid: [...], invalid: [{source, num, reason}], total}"}</code>:
              esito del <Link href="/docs/trust-layer">trust layer</Link>;
              le citazioni valide includono <code>grounding: strong|weak</code>
            </td>
          </tr>
          <tr>
            <td><code>done</code></td>
            <td>
              <code>{"{finish_reason, final_text, citations_total, citations_valid}"}</code>:
              <code>final_text</code> è il testo con le citazioni in prosa
              promosse a tag <code>&lt;cite/&gt;</code> ed eventualmente
              riparate; è la forma da usare per l&apos;export
            </td>
          </tr>
          <tr>
            <td><code>error</code></td>
            <td><code>{"{message}"}</code>: errore applicativo; chiude lo stream</td>
          </tr>
        </tbody>
      </table>
      <p>Esempio con curl:</p>
      <pre>{`curl -N -X POST http://localhost:8000/api/v1/chat \\
  -H "Content-Type: application/json" \\
  -d '{"question": "Qual è il termine di prescrizione del danno da fatto illecito?"}'`}</pre>
      <p>
        Note per l&apos;integrazione: EventSource nativo è GET-only, serve un
        client SSE che supporti POST (il frontend usa{" "}
        <code>@microsoft/fetch-event-source</code>). Se metti un reverse proxy
        davanti all&apos;API, escludi <code>/api/v1/chat</code> da compressione
        e buffering, o lo stream arriverà in un blocco unico a fine
        generazione.
      </p>

      <h2>POST /citations/validate</h2>
      <p>
        Il trust layer come servizio: passi un testo (per esempio un atto già
        scritto), ricevi l&apos;elenco delle citazioni riconosciute con
        l&apos;esito della verifica di ciascuna. È l&apos;endpoint usato
        dall&apos;add-in Word.
      </p>
      <pre>{`curl -X POST http://localhost:8000/api/v1/citations/validate \\
  -H "Content-Type: application/json" \\
  -d '{"text": "Ai sensi dell'"'"'art. 2043 c.c. e dell'"'"'art. 18 St. lav. ..."}'`}</pre>

      <h2>Vigenza temporale</h2>
      <p>
        <code>effective_at</code> filtra il retrieval per data di vigenza: con{" "}
        <code>&quot;2020-01-01&quot;</code> il sistema risponde sulla base dei
        testi vigenti a quella data, e le versioni successive degli articoli
        non entrano nel contesto. Default: oggi. Il dettaglio della
        multivigenza storica completa è in roadmap; oggi il corpus porta il
        consolidato corrente con le finestre di vigenza note.
      </p>
    </>
  );
}
