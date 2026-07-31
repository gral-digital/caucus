# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/) · versioni [SemVer](https://semver.org/).

## [Unreleased] — verso la prima release pubblica come **Caucus**

### Added
- **Guardrail bidirezionale**: policy che distingue analisi giuridica (sempre
  ammessa, anche su reati e clienti colpevoli) da assistenza operativa a un
  illecito (rifiutata per chiunque, avvocati inclusi: artt. 377-378 c.p.), e
  metrica **over-refusal** nel benchmark — nessun benchmark legale la misura.
- **Route `/norma/{source}/art/{num}`**: destinazione dei link delle citazioni
  (API + pagina), con filtro di vigenza e banner per gli articoli abrogati.
- **Corpus**: 50 fonti Normattiva (codici, testi unici, compliance: 231/2001,
  AML, anticorruzione, trasparenza, antimafia, whistleblowing, ambiente,
  processo amministrativo/tributario…), 14 atti UE via EUR-Lex (GDPR, AI Act,
  NIS2, DORA, MiCA, eIDAS, DSA, DMA, direttive), harvest incrementale
  Cassazione da SentenzeWeb (testo integrale anonimizzato, resumabile).
- **Caucus Bench** (`benchmark/`, MIT): primo benchmark legale italiano
  aperto — 162 casi, metriche source-aware, hallucination rate solo sulle
  risposte che citano, casi abrogati/adversarial/out-of-corpus.
- **Trust layer**: validazione post-generazione delle citazioni (esistenza,
  fonte, vigenza, abrogazione, grounding sul contesto).
- **Retrieval**: fusione RRF pesata a 4 rami, query expansion LLM con
  risoluzione estremi ufficiali (act registry), cross-encoder locale
  bge-reranker-v2-m3, grafo dei rinvii normativi con one-hop expansion,
  chunking contestuale, filtro di vigenza su tutti i rami.
- **Sicurezza API**: token auth fail-closed, rate limiting, CORS da env,
  cap sull'history, container non-root.

### Changed
- Fusione inter-collection proporzionale con quota per corpus: con la crescita
  della giurisprudenza (285k chunk vs 64k di norme) il corpus secondario
  sottraeva slot alla normativa prima del reranking.
- Query router: riconoscimento dei riferimenti con la fonte prima del numero
  ("Costituzione italiana art. 3") e separazione tra riferimenti espliciti
  (pinnati) e suggerimenti euristici delle regole di materia (candidati).
- Parser Akoma Ntoso riscritto nei punti critici: euristica body/allegati,
  commi `<list>`, numerazioni oltre-decies e forme slash, date di
  consolidamento reali (FRBRdate + dataVigenza).
- Loader idempotente (delete-and-replace per fonte).

### Security
- Endpoint chiusi di default fuori da `app_env=local`; errori interni mai
  esposti al client; sessione DB gestita correttamente nello streaming SSE.

> Storia dettagliata pre-release: `git log` (commit in italiano, con numeri
> di benchmark nei messaggi).
