# Caucus

[![CI](https://github.com/gral-digital/caucus/actions/workflows/ci.yml/badge.svg)](https://github.com/gral-digital/caucus/actions/workflows/ci.yml)

**AI open source per il diritto e la compliance italiana — con un trust layer
verificabile e il primo benchmark legale italiano aperto.**

*[English version → README.md](README.md)*

Caucus è un assistente legale RAG sull'ordinamento italiano: 50 fonti
consolidate da Normattiva (codici, testi unici, leggi di compliance), 14 atti
UE in italiano (GDPR, AI Act, NIS2, DORA, MiCA…) e le sentenze integrali
anonimizzate della Corte di Cassazione. Ogni citazione normativa di ogni
risposta è validata post-generazione contro il corpus — esistenza, fonte e
vigenza temporale — e segnalata all'utente quando non è verificabile.

> ⚠️ **Caucus non è un avvocato e le sue risposte non sono pareri legali.**
> È uno strumento di ricerca e supporto. Il suo uso non instaura alcun
> rapporto professionale. Per decisioni con conseguenze legali rivolgiti a un
> professionista abilitato.

## Perché esiste

I vendor di AI legale dichiarano accuratezze non riproducibili. Caucus fa la
scommessa opposta: **codice aperto (AGPL-3.0), benchmark aperto (MIT), numeri
onesti**. Su [Caucus Bench](benchmark/README.md) — 171 casi su tutte le aree
principali del diritto italiano, inclusi articoli abrogati, richieste
adversarial e domande fuori corpus — lo stack di riferimento misura oggi:

| | |
|---|---|
| Pass rate | **98%** (100% sui casi difficili) |
| Recall@8 source-aware / MRR | **99% / 0.86** |
| Citation recall | **99%** |
| **Citazioni allucinate** (sulle risposte che citano) | **0,0%** |
| Rifiuto su richieste illecite | **100%** |
| **Rifiuti indebiti su domande professionali legittime** | **0%** |

La varianza tra run della stessa configurazione è reale (pass 95–98%,
recall@8 96–99%, per il nondeterminismo di OpenAI): il numero onesto è
l'intervallo, non il picco. Metodologia e regole anti-gaming:
[benchmark/](benchmark/README.md).

## Cosa c'è dentro

- **Corpus** — 50 fonti Normattiva parsate dall'XML Akoma Ntoso ufficiale
  (rilevamento abrogazioni, data di consolidamento), 14 atti EUR-Lex in
  italiano, harvest incrementale e idempotente delle sentenze di Cassazione
  (~430k disponibili, riprendibile).
- **Retrieval** — quattro rami fusi (RRF pesato): lookup deterministico per
  articolo, query expansion LLM con risoluzione degli estremi ufficiali
  ("art. 17 D.Lgs. 81/2008" → TU Sicurezza), FTS Postgres (config italiana),
  vettori densi (Qdrant). Reranking cross-encoder (bge-reranker-v2-m3,
  locale, MPS/CUDA/CPU). Espansione one-hop sul **grafo dei rinvii normativi**
  estratto dai riferimenti incrociati dell'XML.
- **Trust layer** — ogni `<cite/>` della risposta è validato su database:
  articoli inesistenti, fuori vigenza o abrogati vengono segnalati; le
  citazioni di articoli reali ma *assenti dal contesto* recuperato
  (l'allucinazione più insidiosa) sono riportate come grounding debole. La
  giurisprudenza si cita in prosa con gli estremi reali, mai inventati.
- **Vigenza temporale** — ogni partizione e chunk porta
  `effective_from`/`effective_to`; il retrieval filtra per data di vigenza su
  tutti i rami (default: oggi).
- **API e UI** — FastAPI con streaming SSE, auth a token, rate limiting;
  chat Next.js con pannello fonti e warning sulle citazioni non verificate.

## Avvio rapido

Prerequisiti: Docker, [`uv`](https://docs.astral.sh/uv/), `pnpm`, Node ≥ 20,
una chiave OpenAI (backend di default; backend locali supportati).

```bash
git clone <repo-url> caucus && cd caucus
cp .env.example .env          # poi imposta OPENAI_API_KEY
make install
make up                       # Postgres :55432, Qdrant :6333, Redis, Langfuse
make migrate
make corpus-import SRC=<url>  # corpus completo già indicizzato, embedding inclusi
make dev                      # API :8000, web :3000
```

**Il pacchetto corpus** (pubblicato con ogni release) ripristina in un solo
comando l'intero corpus indicizzato — tabelle Postgres e vettori Qdrant:
niente ingestione, niente costi di embedding. Checksum e revisione dello
schema sono verificati prima di scrivere. In alternativa, la ricostruzione
dalle fonti pubbliche:

```bash
make seed-all                 # 50 fonti Normattiva + atti UE (≈ centesimi di embedding)
make harvest-cassazione       # giurisprudenza, incrementale e riprendibile
make eval                     # Caucus Bench sulla tua istanza
```

Le guide dettagliate (self-hosting, corpus, trust layer, API, benchmark)
sono nell'app stessa, alla pagina `/docs`.

## Licenze

- **Codice applicativo**: [AGPL-3.0](LICENSE) — chi offre un Caucus
  modificato come servizio condivide le modifiche.
- **Benchmark** (`benchmark/`): [MIT](benchmark/LICENSE) — chiunque può
  valutarci sopra qualunque sistema e pubblicare i risultati.

Nota: il repo include ~50 MB di fixture XML ufficiali, così i test del parser
sono riproducibili offline.

## Stato e roadmap

Funziona oggi: tutto quanto sopra. Limiti noti (tracciati onestamente):
consolidamento a snapshot singolo (niente versioning storico), atti UE nel
testo base GU (non consolidato), storia conversazioni client-side, TTFT
~3-4s sulle domande concettuali. Roadmap: multivigenza storica via
`dataVigenza` Normattiva, embedding self-hosted (BGE-M3 ibrido), citazioni in
structured output, conversazioni server-side + audit log, ricerca agentica
multi-hop.

## Contribuire

Vedi [CONTRIBUTING.md](CONTRIBUTING.md). Segnalazioni di sicurezza:
[.github/SECURITY.md](.github/SECURITY.md).
