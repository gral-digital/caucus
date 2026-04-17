# Roadmap

Obiettivo: arrivare a tutti i moduli di Harvey, italianizzati, con sovranità dati EU.

La fondazione comune è **RAG core + gerarchia normativa + citazioni machine-readable**. Una volta solida,
i moduli si sbloccano in parallelo perché riusano lo stesso motore.

## Milestone

### M1 — Fondazioni (in corso)
- [x] Scaffolding monorepo (Python+Node)
- [x] Schema dati normativa (Postgres + pgvector + Qdrant)
- [x] Migration iniziale con FTS italiano + ltree
- [x] FastAPI skeleton con `/search` e `/chat` SSE
- [x] rag-core: retriever hybrid + reranker + LiteLLM router
- [x] Ingestion scaffold Normattiva
- [x] Next.js 15 chat UI con citazioni cliccabili
- [x] Terraform minimo GCP `europe-west1`
- [x] Parser AkomaNtoso XML completo per Normattiva (CC + CP, 92% rubrica coverage)
- [x] Fixture committati di CC + CP (snapshot 2026-04-17) per test offline
- [x] Suite di test pytest sul parser (unit + fixture-based con articoli sentinel)
- [ ] Primo seed funzionante end-to-end: CC + CP indicizzati in Postgres + Qdrant
- [ ] Deploy `dev` su Cloud Run
- [ ] Arricchimento gerarchia Libro/Titolo/Capo (parsing indice HTML Normattiva)

### M2 — "Chiedi al Codice" GA
- [ ] Auth (Clerk o Auth.js)
- [ ] Storico conversazioni
- [ ] Feedback thumbs up/down → dataset di eval
- [ ] Eval set gold verificato da avvocato partner (≥ 200 coppie)
- [ ] Metriche: recall@10 per retriever, faithfulness (LLM-as-judge) per risposte

### M3 — Analisi Documenti
- [ ] Upload PDF/DOCX → GCS → Docling parse
- [ ] Estrazione strutturata (parti, oggetto, clausole)
- [ ] Red flags detector (LangGraph agent)
- [ ] Report PDF/HTML scaricabile

### M4 — Drafting assistito
- [ ] Template library (atto di citazione, comparsa di costituzione, contratto)
- [ ] LangGraph flow con validazione normativa intermedia
- [ ] Versioning bozze, commenti

### M5 — Giurisprudenza
- [ ] Ingestion CED Cassazione (massime)
- [ ] Ingestion sentenze integrali (on-demand)
- [ ] Filter materia/anno/sezione
- [ ] Collegamento automatico sentenze ↔ norme citate

### M6 — Enterprise
- [ ] Onyx connectors (Drive, SharePoint, Outlook, Notion)
- [ ] Multi-tenancy stretta (Postgres RLS + Qdrant collections per-tenant)
- [ ] SSO SAML/OIDC (WorkOS)
- [ ] Audit log WORM su GCS
- [ ] CMEK per tenant

### M7 — Scale
- [ ] Fine-tune Italian-LegalBERT come reranker domain-specific
- [ ] Self-hosted vLLM su GKE (se volume giustifica)
- [ ] Evaluation continua in CI (LLM-as-judge su dataset gold)

## KPI di prodotto (da strumentare dalla M2)

- **Precisione citazioni**: % risposte in cui ogni citazione puntata è verificabile contro il testo normativo (target ≥ 98%).
- **Completezza**: % domande del test set con risposta utile (non "non trovato", anche quando la risposta c'è) — target ≥ 85%.
- **Latenza P50 / P95**: chat response — target P50 < 2s TTFT, P95 < 5s TTFT.
- **Cost per request**: target < €0.05 in fase 1 con Llama via Vertex.
