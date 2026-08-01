import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Guida ai moduli | Documentazione Caucus" };

export default function ModuliDocs() {
  return (
    <>
      <h1>Guida ai moduli</h1>
      <p>
        L&apos;app (<code>/app</code>) è un workspace a quattro moduli. Le
        conversazioni dei moduli sono indipendenti e restano in memoria quando
        passi dall&apos;uno all&apos;altro: puoi lasciare un&apos;analisi a
        metà, fare una ricerca e tornare. Ogni modulo usa la stessa pipeline di
        retrieval e lo stesso <Link href="/docs/trust-layer">trust layer</Link>;
        cambiano il prompt di sistema e le priorità del retrieval.
      </p>

      <h2>Ricerca giuridica</h2>
      <p>
        Domande in linguaggio naturale sul diritto italiano ed europeo. La
        risposta cita articolo e comma, e ogni citazione verificata è un link
        alla pagina <code>/norma</code> con il testo consolidato. Sotto la
        risposta trovi il pannello <em>Fonti consultate</em> con i passaggi
        recuperati e il loro punteggio.
      </p>
      <p>Consigli pratici:</p>
      <ul>
        <li>
          se conosci già gli estremi (&laquo;art. 1454 c.c.&raquo;), citali: il
          lookup diretto è deterministico e più preciso del retrieval;
        </li>
        <li>
          descrivi il fatto concreto, non solo l&apos;istituto: il sistema è
          orientato alla difesa e cerca attivamente attenuanti, vizi
          procedurali e strade alternative;
        </li>
        <li>
          la conversazione ha memoria: puoi incalzare (&laquo;e se il tasso
          fosse 0,9?&raquo;) senza ripetere il contesto.
        </li>
      </ul>

      <h2>Analisi documenti</h2>
      <p>
        Allega fino a <strong>3 documenti</strong> (.docx o .pdf) con la
        graffetta e fai domande: clausole rischiose, obblighi e scadenze,
        vessatorietà ex Codice del Consumo, conformità di una clausola alla
        disciplina legale. Ogni rilievo è collegato alla norma pertinente,
        verificata come sempre.
      </p>
      <ul>
        <li>
          i documenti restano allegati per tutta la conversazione finché non li
          rimuovi; l&apos;analisi può incrociarli (&laquo;le definizioni del
          contratto quadro coprono l&apos;allegato tecnico?&raquo;);
        </li>
        <li>
          per i documenti lunghi il sistema seleziona automaticamente gli
          estratti rilevanti per la domanda, marcando le omissioni con
          [omissis]: se un passaggio ti serve per intero, chiedilo
          esplicitamente;
        </li>
        <li>
          in self-hosting i file non lasciano la tua macchina; nella versione
          hosted sono legati al tuo account e cancellabili.
        </li>
      </ul>

      <h2>Redazione</h2>
      <p>
        Descrivi l&apos;atto che ti serve (parere, diffida, clausola, lettera
        di contestazione) e ottieni una bozza strutturata con le citazioni
        verificate e i campi da completare marcati chiaramente (mai compilati
        con dati inventati). Il bottone <em>Esporta in Word</em> produce un
        .docx con formattazione da studio; prima dell&apos;export il server
        ri-verifica ogni citazione.
      </p>

      <h2>Giurisprudenza</h2>
      <p>
        Ricerca negli orientamenti di legittimità sul testo integrale delle
        decisioni (non sulle sole massime). Le decisioni sono citate con gli
        estremi reali presi dal corpus; se il corpus non copre il tema, la
        risposta lo dice esplicitamente invece di improvvisare. Il corpus
        cresce con l&apos;harvest; la copertura attuale è indicata nel
        pannello fonti.
      </p>

      <h2>Add-in Word</h2>
      <p>
        L&apos;add-in (in <code>apps/word-addin/</code>) porta il trust layer
        dentro Microsoft Word: seleziona il testo di un atto e verifica in un
        click tutte le citazioni contenute, con gli stessi esiti della chat
        (valida / abrogata / inesistente / non verificabile). Utile come
        controllo finale su atti scritti da chiunque, anche senza Caucus.
        Richiede il sideload del manifest e l&apos;app web attiva; istruzioni
        nel README dell&apos;add-in.
      </p>

      <h2>Scorciatoie e dettagli di interfaccia</h2>
      <ul>
        <li>
          <strong>Invio</strong> invia, <strong>Shift+Invio</strong> va a capo;
        </li>
        <li>
          <em>Nuova conversazione</em> azzera solo il modulo attivo, gli altri
          non vengono toccati;
        </li>
        <li>
          durante la risposta vedi le fasi reali della pipeline (instradamento,
          espansione, retrieval, reranking, generazione, verifica), non
          un&apos;animazione di cortesia: sono gli eventi <code>status</code>{" "}
          dello stream;
        </li>
        <li>
          il pannello <em>Fonti del corpus</em> (in sidebar) elenca le 65 fonti
          indicizzate con la data del consolidato.
        </li>
      </ul>
    </>
  );
}
