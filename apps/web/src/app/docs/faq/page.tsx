import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "FAQ — Documentazione Caucus" };

export default function FaqDocs() {
  return (
    <>
      <h1>Domande frequenti</h1>

      <h2>Caucus sostituisce un avvocato?</h2>
      <p>
        No, e non ci prova. È uno strumento di ricerca e supporto alla
        redazione per chi il diritto lo pratica: trova le fonti, le verifica,
        prepara bozze. Le sue risposte non sono pareri legali e l&apos;uso non
        instaura alcun rapporto professionale.
      </p>

      <h2>Può sbagliare?</h2>
      <p>
        Sì. Il <Link href="/docs/trust-layer">trust layer</Link> elimina la
        classe di errore più pericolosa — le citazioni inventate: 0,0%
        misurato sull&apos;ultimo run del benchmark — ma la qualità
        dell&apos;argomentazione resta quella di un sistema probabilistico:
        il pass rate misurato è 95–98%, non 100%, e lo pubblichiamo con la
        varianza proprio perché tu possa calibrare la fiducia. Verifica sempre
        le fonti (ogni citazione è un link al testo consolidato).
      </p>

      <h2>Che fine fanno i miei dati?</h2>
      <p>
        In <strong>self-hosting</strong>: tutto — corpus, domande, documenti
        caricati — resta sulla tua infrastruttura. L&apos;unica uscita verso
        terzi è la chiamata al backend LLM configurato (OpenAI di default);
        con <code>LLM_BACKEND=ollama</code> ed embedding locali nemmeno
        quella. Nella versione <strong>hosted</strong>: i documenti sono legati
        al tuo account e cancellabili; le conversazioni non vengono usate per
        addestrare nulla.
      </p>

      <h2>Quanto costa farlo girare?</h2>
      <p>
        Il software è gratuito. I costi vivi con il backend di default
        (OpenAI): zero per gli embedding se importi il{" "}
        <Link href="/docs/corpus#pacchetto">pacchetto corpus</Link>, centesimi
        per la generazione (una domanda tipica costa nell&apos;ordine di
        0,01–0,03&nbsp;€). Ricostruire il corpus da zero costa qualche euro di
        embedding. Con modelli locali (Ollama) il costo API è zero.
      </p>

      <h2>Che hardware serve?</h2>
      <p>
        Per lo stack con backend OpenAI: una macchina qualsiasi con Docker,
        ~8&nbsp;GB di disco per il corpus e 4&nbsp;GB di RAM per i container.
        Il reranker locale gira su CPU, Apple Silicon (MPS) o CUDA — su CPU è
        solo più lento. Con LLM locali servono le risorse del modello scelto.
      </p>

      <h2>Perché AGPL-3.0?</h2>
      <p>
        Perché le garanzie di Caucus — trust layer, numeri riproducibili —
        hanno valore solo se chi offre il servizio non può chiuderle.
        L&apos;AGPL impone a chi eroga una versione modificata via rete di
        pubblicare le modifiche. Il benchmark è invece MIT: vogliamo che
        chiunque, anche i concorrenti, lo usi per misurare i propri sistemi.
      </p>

      <h2>Posso usarlo per lavori su commissione / nel mio studio?</h2>
      <p>
        Sì. L&apos;AGPL non limita l&apos;uso, nemmeno commerciale: limita la
        distribuzione di versioni modificate senza sorgente. Usarlo
        internamente allo studio, anche modificato, non fa scattare alcun
        obbligo.
      </p>

      <h2>Il corpus è aggiornato?</h2>
      <p>
        Ogni fonte porta la data del suo consolidato (visibile nel pannello
        fonti) e il retrieval filtra per vigenza. Le norme si riallineano
        ripetendo l&apos;ingestione della fonte; la giurisprudenza cresce con
        l&apos;harvest incrementale. Il <Link href="/docs/corpus">pacchetto
        corpus</Link> pubblicato con le release indica la propria data nel
        manifest.
      </p>

      <h2>Posso aggiungere fonti?</h2>
      <p>
        Sì: il catalogo delle fonti Normattiva è dichiarativo (una entry con
        URN e sigla) e l&apos;ingestione fa il resto — è uno dei
        &laquo;good first issue&raquo; tipici. Per fonti con formati nuovi
        serve un parser che produca il modello canonico; il parser Akoma
        Ntoso esistente copre già la maggior parte di Normattiva.
      </p>

      <h2>Come segnalo un errore giuridico nelle risposte?</h2>
      <p>
        Con l&apos;issue template dedicato (&laquo;legal accuracy&raquo;) nel
        repository: domanda, risposta ottenuta, fonte corretta. Se il caso è
        generalizzabile diventa un caso del benchmark — è così che il gold set
        cresce. Per le vulnerabilità di sicurezza usa invece il canale privato
        indicato in SECURITY.md.
      </p>

      <h2>Contribuire senza saper programmare?</h2>
      <p>
        Il contributo più prezioso è proprio giuridico: casi per il benchmark
        (specie nelle materie meno coperte), revisione dei gold, segnalazioni
        di errori normativi. Il formato dei casi è JSON leggibile e documentato
        in <code>benchmark/</code>.
      </p>
    </>
  );
}
