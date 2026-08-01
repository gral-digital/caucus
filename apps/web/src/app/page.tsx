import {
  ArrowRight,
  BadgeCheck,
  FileText,
  Gavel,
  Github,
  Scale,
  ScrollText,
  Server,
} from "lucide-react";
import Link from "next/link";
import { Wordmark } from "@/components/layout/Wordmark";

/**
 * Landing pubblica. Tono: numeri onesti, zero marketing non verificabile.
 * Ogni claim numerico rimanda al benchmark riproducibile.
 */
export default function Landing() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      {/* Nav */}
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <Wordmark size="lg" />
        <nav className="flex items-center gap-2">
          <Link
            href="/docs"
            className="rounded-lg px-3 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink"
          >
            Docs
          </Link>
          <a
            href="https://github.com/gral-digital/caucus"
            className="hidden items-center gap-1.5 rounded-lg px-3 py-2 text-[13.5px] text-ink-muted transition hover:bg-paper-hover hover:text-ink sm:flex"
          >
            <Github size={15} />
            GitHub
          </a>
          <Link
            href="/app"
            className="flex items-center gap-1.5 rounded-lg bg-ink px-4 py-2 text-[13.5px] font-medium text-paper transition hover:bg-ink-muted"
          >
            Apri l&apos;app
            <ArrowRight size={14} />
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-3xl px-6 pb-12 pt-16 text-center">
        <p className="mb-4 text-[12px] font-semibold uppercase tracking-[0.18em] text-accent">
          AI legale open source per il diritto italiano
        </p>
        <h1 className="font-serif text-[44px] leading-[1.12] tracking-tight">
          L&apos;accuratezza legale
          <br />
          non si dichiara. Si dimostra.
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-[16px] leading-relaxed text-ink-muted">
          Ricerca, analisi documenti e redazione sul diritto italiano — con ogni
          citazione verificata su testi consolidati, e un benchmark pubblico che
          chiunque può rieseguire. Gratis, open source, self-hostable.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link
            href="/app"
            className="flex items-center gap-2 rounded-xl bg-ink px-6 py-3 text-[15px] font-medium text-paper transition hover:bg-ink-muted"
          >
            Prova Caucus
            <ArrowRight size={16} />
          </Link>
          <a
            href="https://github.com/gral-digital/caucus"
            className="flex items-center gap-2 rounded-xl border border-paper-border bg-paper px-6 py-3 text-[15px] text-ink transition hover:bg-paper-hover"
          >
            <Github size={16} />
            Codice sorgente
          </a>
        </div>
        <p className="mt-4 text-[12px] text-ink-subtle">
          AGPL-3.0 · benchmark MIT · nessuna registrazione per il self-hosting
        </p>
      </section>

      {/* Numeri onesti */}
      <section className="border-y border-paper-border/70 bg-paper-panel">
        <div className="mx-auto max-w-5xl px-6 py-12">
          <div className="grid grid-cols-2 gap-8 text-center md:grid-cols-4">
            <Stat value="0%" label="allucinazioni misurate" />
            <Stat value="97,7%" label="pass rate (ultimo run)" />
            <Stat value="171" label="casi del benchmark aperto" />
            <Stat value="65+" label="fonti normative consolidate" />
          </div>
          <p className="mx-auto mt-8 max-w-2xl text-center text-[13px] leading-relaxed text-ink-muted">
            Numeri onesti: sono i risultati dell&apos;ultimo run di{" "}
            <span className="font-medium text-ink">Caucus Bench</span> (gold set
            v2.3), il primo benchmark legale italiano aperto. Varianza misurata
            tra run identici: pass 95,3–97,7%. Dataset, runner e report sono nel
            repository: il numero puoi controllarlo, non devi crederci.
          </p>
        </div>
      </section>

      {/* Moduli */}
      <section className="mx-auto max-w-5xl px-6 py-16">
        <h2 className="text-center font-serif text-[28px] tracking-tight">
          Quattro moduli, un trust layer
        </h2>
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Feature
            icon={<ScrollText size={17} />}
            title="Ricerca giuridica"
            text="Domande in linguaggio naturale su 50+ fonti Normattiva consolidate, 14 atti UE e giurisprudenza. Ogni riferimento è un link al testo ufficiale vigente."
          />
          <Feature
            icon={<FileText size={17} />}
            title="Analisi documenti"
            text="Carica contratti e atti (.docx, .pdf): clausole critiche, rischi e scadenze, con le norme pertinenti citate e verificate."
          />
          <Feature
            icon={<Gavel size={17} />}
            title="Redazione"
            text="Bozze di pareri, diffide e clausole già strutturate, con i campi da completare marcati e l'export in Word con formattazione da studio."
          />
          <Feature
            icon={<Scale size={17} />}
            title="Giurisprudenza"
            text="Orientamenti di Cassazione, Consiglio di Stato e TAR sul testo integrale, citati con gli estremi — mai estrapolati da sentenze non lette."
          />
        </div>
      </section>

      {/* Trust layer */}
      <section className="border-y border-paper-border/70 bg-paper-panel">
        <div className="mx-auto grid max-w-5xl grid-cols-1 gap-10 px-6 py-16 md:grid-cols-2">
          <div>
            <h2 className="font-serif text-[28px] leading-tight tracking-tight">
              Ogni citazione passa dal trust layer
            </h2>
            <p className="mt-4 text-[14.5px] leading-relaxed text-ink-muted">
              Un riferimento inventato in un atto è responsabilità professionale.
              Per questo ogni citazione generata viene verificata contro il
              corpus — esistenza, fonte, <strong>vigenza temporale</strong> e{" "}
              <strong>abrogazione</strong> — e se non regge, la risposta viene
              riscritta, non solo segnalata. Anche nei tuoi documenti Word:
              l&apos;add-in controlla le citazioni degli atti che hai già
              scritto.
            </p>
          </div>
          <ul className="flex flex-col justify-center gap-3">
            {[
              "Citazioni linkate al testo consolidato Normattiva",
              "Articoli abrogati segnalati, mai citati come vigenti",
              "Auto-riparazione dei riferimenti non verificabili",
              "Ammissione esplicita quando la fonte non è nel corpus",
              "Self-hosting completo: i fascicoli restano da te",
            ].map((t) => (
              <li key={t} className="flex items-start gap-2.5 text-[14px] text-ink">
                <BadgeCheck size={17} className="mt-0.5 shrink-0 text-accent" />
                {t}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Self host + CTA */}
      <section className="mx-auto max-w-3xl px-6 py-16 text-center">
        <Server size={22} className="mx-auto text-ink-subtle" />
        <h2 className="mt-4 font-serif text-[26px] tracking-tight">
          Tuo, davvero
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-[14.5px] leading-relaxed text-ink-muted">
          Codice AGPL-3.0, corpus ricostruibile da fonti pubbliche — o
          scaricabile già indicizzato, embedding inclusi — backend LLM ed
          embedding intercambiabili. Lo studio che non può usare il cloud fa
          girare tutto on-premise. Nessun piano a pagamento, nessun contratto
          pluriennale: è software libero. La{" "}
          <Link href="/docs" className="text-accent underline decoration-accent/40 underline-offset-2">
            documentazione
          </Link>{" "}
          copre self-hosting, corpus, API e benchmark.
        </p>
        <div className="mt-7 flex items-center justify-center gap-3">
          <Link
            href="/app"
            className="flex items-center gap-2 rounded-xl bg-ink px-6 py-3 text-[15px] font-medium text-paper transition hover:bg-ink-muted"
          >
            Inizia ora
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      <footer className="border-t border-paper-border/70">
        <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-3 px-6 py-8 text-[12.5px] text-ink-subtle sm:flex-row">
          <span>Caucus — AI legale open source per il diritto italiano</span>
          <span>
            L&apos;assistente non sostituisce il parere di un avvocato. AGPL-3.0.
          </span>
        </div>
      </footer>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="font-serif text-[34px] tracking-tight text-ink">{value}</div>
      <div className="mt-1 text-[12.5px] text-ink-muted">{label}</div>
    </div>
  );
}

function Feature({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="rounded-2xl border border-paper-border bg-paper p-6 transition hover:shadow-[0_2px_16px_rgba(0,0,0,0.05)]">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
        {icon}
      </div>
      <h3 className="mt-3 text-[16px] font-semibold">{title}</h3>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-muted">{text}</p>
    </div>
  );
}
