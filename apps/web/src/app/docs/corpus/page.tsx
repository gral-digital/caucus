import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Corpus | Documentazione Caucus" };

export default function CorpusDocs() {
  return (
    <>
      <h1>Il corpus</h1>
      <p>
        Tutto ciò che Caucus afferma è ancorato a un corpus locale e
        ispezionabile. Nessuna risposta si basa solo sulla memoria del modello:
        il retrieval pesca da qui, e il{" "}
        <Link href="/docs/trust-layer">trust layer</Link> verifica qui ogni
        citazione.
      </p>

      <h2>Composizione</h2>
      <table>
        <thead>
          <tr>
            <th>Sezione</th>
            <th>Fonte</th>
            <th>Contenuto</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Norme nazionali</td>
            <td>Normattiva (XML Akoma Ntoso ufficiale)</td>
            <td>
              50 fonti consolidate: i quattro codici, la Costituzione, i
              principali testi unici (sicurezza sul lavoro, bancario, finanza,
              immigrazione, edilizia, ambiente…) e le leggi di compliance
              (231/2001, antiriciclaggio, anticorruzione, whistleblowing…)
            </td>
          </tr>
          <tr>
            <td>Diritto UE</td>
            <td>EUR-Lex (HTML per CELEX, in italiano)</td>
            <td>
              14 atti: GDPR, AI Act, NIS2, DORA, MiCA, DSA/DMA, eIDAS,
              PSD2/MiFID II e le direttive consumatori, whistleblowing, AML,
              ePrivacy
            </td>
          </tr>
          <tr>
            <td>Giurisprudenza</td>
            <td>SentenzeWeb (Corte di Cassazione)</td>
            <td>
              Decisioni civili e penali a testo integrale, nella forma
              anonimizzata pubblicata dalla Corte; harvest incrementale, corpus
              in crescita (72.050 provvedimenti alla data del pacchetto
              corrente)
            </td>
          </tr>
        </tbody>
      </table>

      <h2>Come è costruito</h2>
      <ul>
        <li>
          <strong>Parsing strutturale, non scraping.</strong> Le norme arrivano
          dall&apos;XML Akoma Ntoso ufficiale di Normattiva: articoli, commi,
          rubriche, data del consolidato e stato di abrogazione sono campi
          strutturati, non regex su HTML.
        </li>
        <li>
          <strong>Chunk contestuali.</strong> Ogni frammento indicizzato porta
          nel testo il proprio contesto: fonte, articolo e rubrica (per
          esempio Codice Civile, art. 2043, &laquo;Risarcimento per fatto
          illecito&raquo;), così l&apos;embedding codifica anche la
          collocazione, non solo il testo del comma.
        </li>
        <li>
          <strong>Vigenza temporale.</strong> Ogni partizione e ogni chunk
          hanno <code>effective_from</code>/<code>effective_to</code>: il
          retrieval filtra per data di vigenza (default: oggi) e gli articoli
          abrogati sono marcati: possono essere citati come abrogati, mai
          spacciati per vigenti.
        </li>
        <li>
          <strong>Grafo dei rinvii.</strong> I riferimenti incrociati
          (&laquo;si applica l&apos;art. …&raquo;) estratti dall&apos;XML
          diventano un grafo di citazioni tra norme, usato in retrieval per
          espandere il contesto di un hop.
        </li>
        <li>
          <strong>Ingestione idempotente.</strong> Ricaricare una fonte
          normativa è delete-and-replace: stesso corpus, mai duplicati. La
          giurisprudenza è append-only per identificativo esterno, quindi
          l&apos;harvest è interrompibile e riprendibile.
        </li>
      </ul>

      <h2 id="pacchetto">Il pacchetto corpus scaricabile</h2>
      <p>
        Indicizzare tutto da zero funziona (i comandi sono pubblici e
        riproducibili) ma richiede ore di harvest e qualche euro di embedding.
        Per questo ogni release pubblica un <strong>pacchetto corpus</strong>{" "}
        pronto: l&apos;intero database già popolato e le collection vettoriali
        già calcolate.
      </p>
      <pre>{`# con l'infra attiva (make up && make migrate):
make corpus-import SRC=https://github.com/gral-digital/caucus/releases/download/corpus-20260801
# oppure da una directory locale già scaricata:
make corpus-import SRC=/percorso/caucus-corpus-YYYYMMDD`}</pre>
      <p>Il pacchetto contiene:</p>
      <ul>
        <li>
          <code>postgres_corpus.dump</code>: dump compresso delle sole tabelle
          del corpus (norme, commi, chunk, grafo dei rinvii, giurisprudenza).
          Le tabelle utente non sono incluse e l&apos;import non le tocca;
        </li>
        <li>
          <code>qdrant_*.snapshot</code>: uno snapshot per collection
          vettoriale (embedding <code>text-embedding-3-small</code>, 1536
          dimensioni), ripristinato così com&apos;è: zero chiamate API;
        </li>
        <li>
          <code>manifest.json</code>: data, commit di origine, revisione dello
          schema, conteggi per tabella e collection, checksum SHA-256 di ogni
          file. L&apos;import verifica tutto prima di scrivere e confronta i
          conteggi a fine ripristino;
        </li>
        <li>
          <code>README.md</code>: licenze dei dati e istruzioni minime.
        </li>
      </ul>
      <p>
        Il download pesa alcuni GB (la parte grossa sono gli embedding della
        giurisprudenza). Lo script riprende i download interrotti e puoi
        rilanciarlo senza paura: l&apos;import è ripetibile.
      </p>
      <p>
        Per produrre un pacchetto dalla propria istanza (per esempio dopo aver
        aggiunto fonti):
      </p>
      <pre>{`make corpus-export   # scrive dist/corpus/caucus-corpus-<data>/`}</pre>

      <h2>Licenze dei dati</h2>
      <ul>
        <li>
          <strong>Atti normativi</strong> (Normattiva, EUR-Lex): gli atti
          ufficiali dello Stato e delle amministrazioni pubbliche sono esclusi
          dalla protezione del diritto d&apos;autore (art. 5 L. 633/1941); per
          gli atti UE vale la politica di riuso della Commissione (decisione
          2011/833/UE).
        </li>
        <li>
          <strong>Giurisprudenza</strong>: i provvedimenti sono ingeriti nella
          forma anonimizzata pubblicata da SentenzeWeb ai fini di pubblicità
          legale; il corpus non aggiunge alcun dato personale rispetto alla
          fonte e l&apos;harvest rispetta un rate limit conservativo con
          user-agent identificato.
        </li>
        <li>
          <strong>Chunking ed embedding</strong> (il lavoro di Caucus sul
          testo): rilasciati sotto licenza MIT, come il benchmark. Il codice
          resta AGPL-3.0.
        </li>
      </ul>

      <h2>Aggiornare il corpus</h2>
      <p>
        Le norme si riallineano al consolidato corrente ripetendo
        l&apos;ingestione della singola fonte (
        <code>uv run caucus-ingest ingest --codice cc</code>): il loader
        sostituisce la fonte per intero. La giurisprudenza cresce con{" "}
        <code>make harvest-cassazione</code>, che riparte da dove si era
        fermato. La data di consolidamento di ogni fonte è visibile nel
        pannello &laquo;Fonti del corpus&raquo; dell&apos;app.
      </p>
    </>
  );
}
