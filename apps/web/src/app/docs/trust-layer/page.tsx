import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Trust layer | Documentazione Caucus" };

export default function TrustLayerDocs() {
  return (
    <>
      <h1>Il trust layer</h1>
      <p>
        Un riferimento normativo inventato dentro un atto è un problema di
        responsabilità professionale, non un difetto estetico. Per questo in
        Caucus la validazione delle citazioni non è un prompt che chiede al
        modello di &laquo;essere accurato&raquo;: è un passaggio di verifica{" "}
        <strong>post-generazione, contro il database</strong>, che nessuna
        risposta salta.
      </p>

      <h2>Cosa succede a ogni risposta</h2>
      <ol>
        <li>
          <strong>Riconoscimento.</strong> Le citazioni in prosa
          (&laquo;art. 2043 c.c.&raquo;, &laquo;articolo 17 del D.Lgs.
          81/2008&raquo;, sigle e forme lunghe) vengono riconosciute e promosse
          a riferimenti strutturati.
        </li>
        <li>
          <strong>Verifica su database.</strong> Per ogni riferimento: la
          fonte è indicizzata? L&apos;articolo esiste? È vigente alla data
          della domanda? È abrogato?
        </li>
        <li>
          <strong>Controllo del grounding.</strong> Una citazione può essere
          formalmente corretta ma non provenire dal contesto recuperato: è
          l&apos;allucinazione più insidiosa, perché il testo &laquo;torna&raquo;.
          Queste citazioni sono marcate <em>weak grounding</em> e segnalate.
        </li>
        <li>
          <strong>Riparazione.</strong> Se la verifica trova riferimenti
          inesistenti, una passata di riparazione (con timeout: mai a costo
          della latenza percepita) riscrive la risposta correggendo o
          rimuovendo i riferimenti non verificabili.
        </li>
        <li>
          <strong>Trasparenza.</strong> L&apos;esito arriva al client
          nell&apos;evento SSE <code>citation_warnings</code> e il testo
          finale (con le citazioni promosse a tag <code>&lt;cite/&gt;</code>)
          nell&apos;evento <code>done</code>. La UI mostra il conteggio
          &laquo;citazioni verificate&raquo; sotto ogni risposta e un banner
          per quelle non verificabili.
        </li>
      </ol>

      <h2>Gli esiti possibili</h2>
      <table>
        <thead>
          <tr>
            <th>Esito</th>
            <th>Significato</th>
            <th>Cosa vede l&apos;utente</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Valida</td>
            <td>Fonte e articolo esistono, vigenti, presenti nel contesto</td>
            <td>Citazione linkata al testo consolidato (pagina /norma)</td>
          </tr>
          <tr>
            <td>Abrogata</td>
            <td>L&apos;articolo esiste ma è abrogato</td>
            <td>Marcatura esplicita: citabile come storia, non come vigente</td>
          </tr>
          <tr>
            <td>Fuori vigenza</td>
            <td>Non vigente alla data richiesta</td>
            <td>Segnalazione con la finestra di vigenza reale</td>
          </tr>
          <tr>
            <td>Weak grounding</td>
            <td>Articolo reale ma assente dal contesto recuperato</td>
            <td>Avviso: verificare prima di farci affidamento</td>
          </tr>
          <tr>
            <td>Inesistente</td>
            <td>La fonte o l&apos;articolo non risultano nel corpus</td>
            <td>Banner di avvertimento con l&apos;elenco dei riferimenti</td>
          </tr>
        </tbody>
      </table>

      <h2>La giurisprudenza è un caso a parte</h2>
      <p>
        Le decisioni si citano in prosa con gli estremi reali (sezione, numero,
        anno) presi dal contesto recuperato, mai generati. Il prompt lo vieta,
        e il <Link href="/docs/benchmark">benchmark</Link> contiene casi che
        verificano proprio questo: quando il corpus non contiene giurisprudenza
        pertinente, la risposta deve dirlo (&laquo;gap admission&raquo;), non
        inventare una massima plausibile.
      </p>

      <h2>Nei tuoi documenti Word</h2>
      <p>
        Lo stesso motore è esposto dall&apos;endpoint{" "}
        <code>POST /api/v1/citations/validate</code> e dall&apos;add-in Word:
        seleziona un atto già scritto e ottieni la verifica di ogni citazione
        contenuta: utile per il controllo finale prima del deposito. Vedi{" "}
        <Link href="/docs/moduli">Guida ai moduli</Link>.
      </p>

      <h2>Limiti, detti chiaramente</h2>
      <ul>
        <li>
          La verifica copre ciò che è nel corpus: una citazione a una fonte non
          indicizzata è segnalata come non verificabile, non come falsa.
        </li>
        <li>
          Il trust layer verifica i <em>riferimenti</em>, non la correttezza
          dell&apos;argomentazione giuridica: quella resta responsabilità del
          professionista.
        </li>
        <li>
          Il tasso di citazioni allucinate misurato sul benchmark è 0,0%
          sull&apos;ultimo run: misurato, non garantito. La varianza tra run
          esiste ed è pubblicata insieme ai numeri.
        </li>
      </ul>
    </>
  );
}
