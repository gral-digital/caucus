# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/) · versioni [SemVer](https://semver.org/).

## [Unreleased] — verso la prima release pubblica come **Caucus**

### Added
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
- Parser Akoma Ntoso riscritto nei punti critici: euristica body/allegati,
  commi `<list>`, numerazioni oltre-decies e forme slash, date di
  consolidamento reali (FRBRdate + dataVigenza).
- Loader idempotente (delete-and-replace per fonte).

### Security
- Endpoint chiusi di default fuori da `app_env=local`; errori interni mai
  esposti al client; sessione DB gestita correttamente nello streaming SSE.

> Storia dettagliata pre-release: `git log` (commit in italiano, con numeri
> di benchmark nei messaggi).
