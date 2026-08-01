import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Benchmark — Documentazione Caucus" };

export default function BenchmarkDocs() {
  return (
    <>
      <h1>Caucus Bench</h1>
      <p>
        Il mercato dell&apos;AI legale è pieno di percentuali non
        riproducibili. Caucus Bench è la risposta: un benchmark{" "}
        <strong>aperto</strong> (licenza MIT, separato dal codice AGPL) per
        l&apos;AI giuridica italiana — gold set, harness e report sono nel
        repository, e chiunque può rieseguire la misura o sottomettere i
        risultati del proprio sistema.
      </p>

      <h2>Cosa misura</h2>
      <p>
        171 casi (gold set v2.3) su tutte le aree principali: civile, penale,
        procedura, lavoro, compliance, diritto UE. Non solo domande
        &laquo;facili&raquo;:
      </p>
      <ul>
        <li>
          <strong>casi hard</strong> — articoli abrogati, riforme recenti,
          istituti che i modelli confondono sistematicamente;
        </li>
        <li>
          <strong>casi adversarial</strong> — richieste di assistenza a
          condotte illecite, anche con framing professionale: la risposta
          giusta è il rifiuto;
        </li>
        <li>
          <strong>casi professional-legitimate</strong> — domande legittime di
          un difensore che <em>sembrano</em> scabrose: la risposta giusta è
          rispondere (misura l&apos;over-refusal);
        </li>
        <li>
          <strong>casi fuori corpus</strong> — la risposta giusta è ammettere
          il gap, non improvvisare.
        </li>
      </ul>

      <h2>Le metriche</h2>
      <table>
        <thead>
          <tr>
            <th>Metrica</th>
            <th>Cosa dice</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Pass rate</td>
            <td>Casi in cui la risposta soddisfa tutti i criteri del gold</td>
          </tr>
          <tr>
            <td>Recall@8 (source-aware)</td>
            <td>
              Gli articoli attesi sono nei primi 8 risultati del retrieval —
              contando fonte + numero, non la sola stringa
            </td>
          </tr>
          <tr>
            <td>MRR</td>
            <td>Quanto in alto compare il primo risultato corretto</td>
          </tr>
          <tr>
            <td>Citation recall</td>
            <td>Le citazioni attese compaiono nella risposta generata</td>
          </tr>
          <tr>
            <td>Hallucination rate</td>
            <td>
              Citazioni inventate, calcolate <em>sulle risposte che citano</em>{" "}
              (una risposta senza citazioni non può abbassare il tasso)
            </td>
          </tr>
          <tr>
            <td>Refusal / Over-refusal</td>
            <td>
              Rifiuto sugli adversarial e, simmetricamente, risposta sulle
              domande professionali legittime
            </td>
          </tr>
          <tr>
            <td>Gap admission</td>
            <td>Ammissione esplicita quando la fonte non è nel corpus</td>
          </tr>
          <tr>
            <td>TTFT p50/p95</td>
            <td>Latenza al primo token (con hardware dichiarato)</td>
          </tr>
        </tbody>
      </table>

      <h2>Regole anti-gaming</h2>
      <ul>
        <li>
          <strong>il gold set non si adatta mai all&apos;output del sistema</strong>:
          si corregge solo contro le fonti ufficiali;
        </li>
        <li>
          il matching delle citazioni è source-aware: citare l&apos;articolo
          giusto del codice sbagliato non conta;
        </li>
        <li>
          risultati su gold set modificato non sono confrontabili e non vengono
          accettati in leaderboard;
        </li>
        <li>
          si riporta <strong>l&apos;ultimo run, non il migliore</strong>, e la
          varianza misurata tra run identici è pubblicata accanto ai numeri;
        </li>
        <li>
          le latenze dichiarano hardware e condizioni (macchina idle o no).
        </li>
      </ul>

      <h2>I numeri correnti</h2>
      <p>
        La configurazione di riferimento misura, su gold v2.3:{" "}
        <strong>pass 98%</strong> (100% sui casi hard), recall@8 99%, MRR 0.86,
        citation recall 99%, <strong>0,0% citazioni allucinate</strong>, 100%
        refusal sugli adversarial, 0% over-refusal, 100% gap admission, TTFT
        p50 4,7s. Varianza tra run identici: pass 95,3–97,7%, recall@8
        96,2–99,4% — <em>l&apos;intervallo è il numero onesto, non il picco</em>.
        La leaderboard completa con configurazioni e correzioni dichiarate è in{" "}
        <code>benchmark/RESULTS.md</code>.
      </p>

      <h2>Riprodurre la misura</h2>
      <pre>{`make up && make migrate
make corpus-import SRC=...   # o make seed-all
make dev-api
make eval                    # scrive reports/eval_v2_latest.json
# confronto con un run precedente:
uv run python benchmark/run_benchmark.py --baseline reports/precedente.json`}</pre>
      <p>
        Per valutare un sistema diverso da Caucus basta esporre lo stesso
        contratto SSE del <Link href="/docs/api">endpoint /chat</Link> (o
        adattare una singola funzione dell&apos;harness). Le submission alla
        leaderboard richiedono il report JSON, la configurazione esatta e la
        versione del gold set.
      </p>
    </>
  );
}
