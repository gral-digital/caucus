# Audit completo — verso un agente open source SOTA per legal & compliance in Italia

**Data:** 2026-07-31 · **Perimetro:** intero repo (rag-core, apps/api, ingestion, indexer, apps/web, infra, eval, docs) + ricerca di mercato/letteratura 2025-26.

---

## Verdetto sintetico

Il progetto ha **fondamenta concettuali giuste** (modellazione giuridica del dominio sopra la media, architettura retrieval a 3 vie corretta, validazione citazioni post-generazione che è il pezzo di "trust layer" giusto) ma **quasi ogni layer ha o un bug di correttezza o un componente dichiarato-e-non-implementato**. Lo stato attuale è un demo convincente su CC/CP, non un prodotto: il corpus è corrotto su più fonti, l'hybrid search è di fatto dense-only, il reranker attivo è keyword-based, la multivigenza restituisce risposte storicamente false, non c'è autenticazione, l'eval non è statisticamente interpretabile e la documentazione descrive un sistema molto più completo di quello che esiste.

La distanza dal SOTA non è colmabile "aggiungendo feature": prima va resa **vera** la pipeline dichiarata (fix di correttezza), poi va costruito il layer di **misurazione** (eval seria), e solo dopo ha senso il layer **agentico** che il mercato 2026 considera standard.

---

## 1. Bug di correttezza (bloccanti — producono risposte sbagliate oggi)

### Corpus / parsing (services/ingestion)
1. **CCP = allegati, non codice.** L'euristica formato A/B (`parsers/normattiva_akn.py:409`) fa scartare i 233 articoli del d.lgs. 36/2023 e indicizza al loro posto 295 articoli degli allegati tecnici: 27 articoli distinti con `number="1"`, rubrica coverage 11.2%. Ogni risposta su appalti è non verificabile.
2. **Commi `<list>` persi.** `_parse_article_canonical` (`normattiva_akn.py:451-455`) salta i `<paragraph>` senza `<content>` diretto: persi fino al **16.9%** dei commi (TUSL), 13.6% (CCP), 10.6% (TUF) — proprio definizioni, requisiti, cause di esclusione.
3. **Numerazione oltre `decies` collassata.** Le regex (`normattiva_akn.py:260-300`) non coprono `undecies…vicies` né `.1`: nel Codice Privacy `2-undecies`→"2", `2-quaterdecies`→"2-quater". Articoli centrali per il GDPR si sovrascrivono a vicenda.
4. **`effective_from` falso per costruzione.** Il loader propaga la data storica del catalogo (es. CdS 1993) al testo consolidato 2026 (`loader.py:82`, `chunker.py:64`): una query `effective_at=1995` restituisce il testo vigente oggi dichiarandolo vigente nel 1995. Il `<meta>` AKN con `FRBRdate`, 241 `eventRef` e 1747 `textualMod` machine-readable **non viene mai letto**.
5. **Idempotenza falsa.** Nessun unique constraint su `norm_partition`, nessun `on_conflict` nel loader (`loader.py:165-199`): rieseguire il seed **duplica l'intero corpus** silenziosamente.
6. **Rubriche sporche formato B** (`(( (Oggetto). ))` → `"(Oggetto)."`, `normattiva_akn.py:446`); coverage rubriche reale: ccp 11%, cpriv 45%, cad/tui ~65% (soglia dichiarata ≥85% verificata solo su cc/cp).
7. **Fixture CLI rotte per 21/23 fonti** (`cli.py:40-47`: mappa con nomi sbagliati/KeyError); Makefile seeda solo cc/cp: il popolamento delle altre 21 fonti non è riproducibile.
8. **Refresh corpus inesistente**: `indexer/tasks.py:41` importa una funzione che non esiste (`ImportError` mascherato dai retry Dramatiq); `reindex_corpus` è uno stub TODO; nessun cron, nessuna change detection (il `source_hash` è scritto e mai letto); `data/sources/` vuota nonostante i doc promettano snapshot.

### Retrieval (services/rag-core)
9. **Hybrid search di fatto dense-only.** Solo `LocalBGEM3Provider` produce vettori sparse; il backend attivo è `openai` (`text-embedding-3-small`) → la collection ha zero sparse e l'RRF Qdrant degrada a dense puro (`qdrant_store.py:91,116`; `embeddings/openai.py:74`).
10. **Config contraddittoria**: `config.py:58-59` dichiara `bge-m3` con `embedding_dim=1536` (bge-m3 è 1024); su mismatch di dim `ensure_collection` fa **`delete_collection` silenziosa** (`qdrant_store.py:44-48`) — distruzione dati senza conferma.
11. **Reranker attivo = keyword.** Con `RERANKER_BACKEND=auto` e Cohere key vuota si finisce su `KeywordBoostReranker` (overlap lessicale + pesi hardcoded, segnale semantico pesato 0.1). Il boost rubrica è **codice morto**: cerca `\(Rubrica\)` ma il chunker scrive `[Rubrica]` (`reranker.py:203` vs `chunker.py:71`). Il fallback ImportError della factory non protegge (lazy load: crash alla prima query, `reranker_factory.py:27-31`).
12. **Bug RRF**: `hit_merge.py:25` sovrascrive i metadata con l'ultima lista — il boost +3.0 "direct lookup" non scatta proprio sui chunk confermati da più rami. Merge inter-collection che "normalizza" senza normalizzare (`retriever.py:69-71`).
13. **Multivigenza mai attiva di default**: `effective_at=None` significa "nessun filtro" (non "oggi" come dice il docstring); il ramo FTS e il lookup diretto **ignorano completamente** la vigenza (`fts_retriever.py:36-102`), e il lookup diretto è pinnato in cima con score 10.0. Articoli abrogati (~315 nel solo CC) indicizzati come chunk normali senza flag, in competizione con i vigenti.
14. **Chunk decontestualizzati e duplicati**: i chunk `comma` non contengono fonte/articolo/rubrica nel testo embeddato; ~1450 coppie articolo-full≡comma-unico duplicate nel solo CC; nessuna dedup per `partition_id` → context window ridondante.
15. **Rinvii normativi buttati**: l'XML ha 986 `<ref href>` già risolti; il parser li appiattisce; la tabella `norm_citation` esiste e non è mai scritta né letta. Nessun grafo dei rinvii, nessuna one-hop expansion.
16. **Gerarchia persa**: tutti gli articoli figli di un `libro_0` fittizio anche dove l'XML ha `<chapter>/<section>` (cds 17, cpriv 57, ccp 41); `path` è VARCHAR+trigram, non ltree → niente parent-document retrieval né context expansion.

### API (apps/api)
17. **`effective_at` non parsato in try/except** (`chat_service.py:95-103`): data malformata → crash del generatore SSE senza evento error.
18. **Validazione citazioni**: verifica solo che `(source, articolo)` esista in DB — un articolo abrogato risulta `valid`, un articolo reale citato a sproposito pure; `grounding: "weak"` (l'allucinazione più insidiosa) calcolato e **mai inviato al client** se non ci sono anche errori duri; il testo con citazioni promosse è calcolato e scartato (`chat_service.py:144-150,354-380`).
19. **SSE fragile**: `done` emesso solo su `finish_reason` — stream chiuso senza → UI bloccata su "streaming"; `str(exc)` rimandato al client (leak dettagli provider); retrieval fuori dal try; probabile **leak di connessioni DB** (dependency `yield` chiusa prima dello streaming, lavoro DB dentro il generatore — `deps.py:36-38`).
20. **Memoria conversazionale interamente client-supplied**: un client può forgiare turni `assistant` per fare priming e bypassare l'unico guardrail (regola 3 del prompt). Nessuna persistenza server-side.

---

## 2. Assenze strutturali (gap di prodotto)

### Sicurezza / enterprise (tutto dichiarato in SECURITY.md, quasi nulla implementato)
- **Zero auth, zero rate limiting, zero tenancy** su endpoint LLM a pagamento; Terraform deployerebbe con `INGRESS_TRAFFIC_ALL`. `tenant_id` è oggi un parametro client-controlled nel body di `/search` (IDOR pronto).
- **Zero audit log** (SECURITY.md promette WORM 10 anni), zero persistenza conversazioni, zero feedback.
- **Contraddizione di sovranità**: SECURITY.md vieta "OpenAI diretta in fase 1" per l'art. 622 c.p.; il default di `.env.example` è OpenAI diretto. O DPIA+aggiornamento doc, o cambio default (Ollama/vLLM locale o endpoint EU).
- Guardrail = solo testo nel prompt; nessun classificatore input/output, nessuna gestione materie sensibili.
- CORS hardcoded localhost con `allow_credentials=True`; container root; Dockerfile che non builda (`uv.lock` mai copiato); nessun `.dockerignore` (il build context includerebbe `.env` con la chiave OpenAI reale — **da ruotare** prima di qualunque pubblicazione).

### Osservabilità
- Langfuse: container acceso, SDK installato, **zero righe di integrazione** (nessun callback LiteLLM, `trace_id` mai passato). Nessun OTel, nessun request-id (`bind_contextvars` mai chiamato), nessun /metrics.

### Corpus per "legal & compliance completo"
Mancano (in ordine di impatto): **giurisprudenza** (Cassazione/CED/Consulta/CdS/merito) · **d.lgs. 231/2001** (il gap singolo più grave lato compliance) e 231/2007 AML · **GDPR e diritto UE** (il corpus ha solo il d.lgs. 196/2003, che rinvia al Regolamento non indicizzato; niente AI Act, DORA, NIS2, MiCA — serve fetcher EUR-Lex/Cellar, che ha SPARQL+REST con URI ELI) · prassi (circolari AdE, interpelli, INPS) · regolamenti autorità (Garante, Consob, Banca d'Italia, ANAC) · CCNL (via CNEL) · codice deontologico CNF · monitoraggio Gazzetta Ufficiale.
Inoltre: tutte le 23 fonti in un'unica collection `codici` — `CorpusFilter.LEGGI` e `CASSAZIONE` sono enum vuoti.

### Eval (scripts/eval_lexroom_benchmark.py)
- Gold set **14 casi** (13 core), scritto a mano su articoli famosi, **non in git**, **modificato dopo l'ultima run per allinearsi all'output del sistema** (cc-1425→cc-1427): benchmark overfitting documentato.
- Varianza ±13.7 punti tra run identiche; il verdetto "COMPETITIVO vs Lexroom" dipende dal rumore ed è calcolato contro **claim di marketing hardcoded**, non misure.
- **Metrica anti-allucinazione invertita**: 15/100 punti per l'assenza di warning → una risposta senza citazioni prende 75/100 e passa (6/13 casi core della run finale non citavano nulla).
- Retrieval misurato ≠ retrieval usato per rispondere (due chiamate separate con pipeline diverse); latenza "TTFT" che in realtà è tempo di completamento; nessuna metrica di faithfulness a livello di claim; nessun caso temporale/abrogazioni; eval mai in CI.

### Test & CI
- 23 test totali su ~5.400 LOC; `pytest` e `mypy` in CI con `continue-on-error: true` (un test rosso non fallisce mai); `apps/api/tests/` dichiarato in testpaths e **inesistente**; i test rag-core untracked; zero test sul Formato B del parser (21 fonti su 23), zero su chat_service/validazione citazioni/loader/chunker; test esistenti overfittati sugli hardcode del router.

### Frontend
- Citazioni "cliccabili" → **404** (route `/norma` inesistente); zero persistenza ("Nuova conversazione" = `window.location.reload()`); filtri corpora decorativi (il backend supporta `corpora`/`sources`/`effective_at`, la UI non li invia); mobile inutilizzabile; niente stop/copy/regenerate/feedback; zero a11y; zero test; `packages/ui` e `shared-types` vuoti.

### Infra/DevOps
- Terraform non produce un sistema funzionante: **niente Qdrant** (il RAG non partirebbe), niente `google_sql_user`, niente secret definite, web su default SA (Editor), tfstate locale. `infra/k8s/` vuota. CD inesistente. 3 container su 6 del compose (Langfuse, MinIO, in parte Redis) accesi e mai usati dal codice.

### Open source readiness
- **Nessun LICENSE** e README che dichiara "Proprietaria" — incompatibile con l'obiettivo dichiarato. Mancano CONTRIBUTING, CODE_OF_CONDUCT, SECURITY policy, template, CHANGELOG, README riproducibile (manca perfino `cp .env.example .env` nel quick start). Bene: nessun secret nei file tracciati, licenza dei dati normativi documentata correttamente (pubblico dominio ex art. 5 L. 633/1941).

---

## 3. Cosa dice lo stato dell'arte (2025-26)

**Mercato.** Harvey ($11B, marzo 2026): 500+ agenti pre-costruiti + Agent Builder, Vault documentale, ~700k task/giorno. Lexis+ Protégé: 300+ workflow e **Shepard's Verify Trust Markers** — la citation verification esposta come trust marker è ormai lo standard. In Italia: Lexroom (~€20M+ raccolti, RAG su fonti verificate + libreria privata di studio), Simpliciter, Normo, Aptus, più gli incumbent (WK Libra, Lefebvre Giuffrè GenIA-L). Lo standard di prodotto = (1) agenti/workflow multi-step, (2) vault documenti privati, (3) drafting agentico, (4) citazioni verificate con trust markers, (5) integrazione Word/gestionale.

**Benchmark.** LegalBench/LegalBench-RAG (retrieval a livello snippet), LexRAG, LegalCiteBench (2026). Stanford RegLab: Lexis+ AI allucina il 17%, Westlaw 33%, LLM generici 59-88% su query legali. **Non esiste un benchmark legale italiano pubblico** (CALAMITA/ITALIC sono i più vicini): pubblicare un gold set italiano serio è un asset competitivo raro e perfetto per un progetto open source.

**Tecniche.** Hybrid BM25+dense+RRF con cross-encoder: +5-15 punti. **Contextual Retrieval** (Anthropic): −35% retrieval failure, −49% con BM25 contestuale, −67% con reranking — ideale per articoli di codice decontestualizzati. Late chunking (Jina). **Graph RAG sui rinvii normativi** (CRAwLeR, LegalGraphRAG 2026) — combacia esattamente con i 986 `<ref href>` che il parser oggi butta. Agentic RAG multi-hop batte le pipeline statiche sulle domande composte.

**Modelli open (per sovranità EU / self-host).** Generazione: Qwen 3/3.5, Mistral (migliore sulle lingue europee); i modelli italiani (Minerva, Velvet 25B, Domyn) valgono per sovranità più che per capacità. Embedding: **Qwen3-Embedding** (n.1 MTEB multilingual) o **BGE-M3** (unico con dense+sparse+ColBERT nativi — già previsto dal codice!). Reranker: **Qwen3-Reranker 0.6B/4B** o bge-reranker-v2-m3 (già implementato, mai attivo).

---

## 4. Roadmap prioritizzata verso il SOTA

### Fase 0 — Verità e sicurezza (1-2 settimane) — prerequisito di tutto
1. Fix parser: euristica A/B (CCP), commi `<list>`, regex `undecies…vicies`, rubriche `(( ))`.
2. Fix loader: unique constraint + upsert idempotente; `effective_from` da `FRBRExpression/FRBRdate` (o disattivare il filtro temporale finché non è vero); flag `abrogato` dai `textualMod`.
3. Fix retrieval: overwrite metadata in RRF, `[Rubrica]`, vigenza su FTS+direct lookup+validazione citazioni, `effective_at` default = oggi, niente `delete_collection` silenziosa.
4. Sicurezza minima: auth (anche solo API key), rate limit, CORS da env, no `str(exc)` al client, cap su history, rotazione chiave OpenAI, `.dockerignore`, fix Dockerfile, container non-root.
5. CI vera: togliere `continue-on-error`, trackare i test untracked e il gold set, test su chat_service/validazione citazioni/parser Formato B/loader.
6. Riproducibilità: fixture path da catalogo, target Make per tutte le 23 fonti, re-ingest completo del corpus dopo i fix (il corpus attuale è corrotto e va rigenerato).

### Fase 1 — Retrieval SOTA misurabile (2-4 settimane)
7. **Eval prima delle feature**: gold set ≥100-150 quesiti su tutte le fonti (inclusi casi hard: bis/ter, abrogati, multivigenza, multi-hop, out-of-scope, adversarial), versionato, con recall@k/nDCG/MRR + faithfulness a livello di claim (LLM-judge) + misura TTFT reale; run ripetute con CI di confidenza; eval in CI notturna con baseline. Fixare la metrica anti-allucinazione (una risposta senza citazioni non è "pulita").
8. **Hybrid vero**: BGE-M3 (dense+sparse) o Qwen3-Embedding+FTS; reranker cross-encoder attivo (bge-reranker-v2-m3 locale o Qwen3-Reranker); RRF pesato per ramo.
9. **Contextual chunking**: prefisso `fonte + art. + rubrica + gerarchia` nei chunk comma; dedup articolo≡comma-unico; parent-document retrieval sfruttando `path` (migrato a ltree) e gerarchia reale da `<chapter>/<section>`.
10. **Grafo dei rinvii**: popolare `norm_citation` dai `<ref href>` + `textualMod`; one-hop expansion sui top-k; base per graph RAG.
11. Query understanding LLM al posto delle 14 regole hardcoded (structured output con `response_format`, già supportato dal router LLM).

### Fase 2 — Corpus completo legal+compliance (4-8 settimane, parallelizzabile)
12. Fetcher EUR-Lex/Cellar (GDPR, AI Act, NIS2, DORA, MiCA, direttive/regolamenti in italiano, URI ELI).
13. d.lgs. 231/2001 e 231/2007 + normativa AML; regolamenti autorità (Garante, Consob, Banca d'Italia, ANAC); codice deontologico.
14. Giurisprudenza: Cassazione (SentenzeWeb/Italgiure), Consulta, giustizia amministrativa; collection `cassazione` reale con `CaseLawCitation` già modellata.
15. Sync automatico: monitor GU/Normattiva con change detection su `source_hash` (finalmente letto), scheduling reale (i task Dramatiq vanno riscritti), multivigenza incrementale con chiusura `effective_to`.

### Fase 3 — Da RAG a agente (4-8 settimane)
16. Loop agentico: decomposizione quesiti, retrieval iterativo, follow-up sui rinvii, self-critique, ricerca combinata norme+giurisprudenza+prassi; structured outputs per le citazioni al posto del parsing regex.
17. Trust markers per citazione in UI (verificata / debole / non trovata) — il differenziatore che Lexis vende, e il vostro validatore è già a metà strada.
18. Persistenza conversazioni + audit log + feedback (che alimenta l'eval); route `/norma/[source]/art/[num]` con testo ufficiale e deep-link.
19. Guardrail reali: history server-side, classificatore input/output, gestione materie sensibili, disclaimer strutturale e posizionamento dichiarato (il prompt "difensore con 20 anni di foro" senza disclaimer è un'esposizione ex art. 348 c.p. verso utenti privati).
20. Osservabilità: Langfuse davvero cablato, request-id, costi per richiesta, /metrics.

### Fase 4 — Open source e distribuzione
21. Scegliere la licenza (AGPL-3.0 se si vuole proteggere da SaaS-wrapping, Apache-2.0 se si vuole adozione massima) e sostituire "Proprietaria" nel README; CONTRIBUTING, SECURITY policy, CoC, README EN+IT riproducibile, CHANGELOG.
22. Allineare docs e realtà (ARCHITECTURE/SECURITY/INGESTION descrivono un sistema inesistente: prima impressione fatale per un progetto OSS).
23. Default sovrano: stack self-host di riferimento (Ollama/vLLM + BGE-M3 + Qwen3-Reranker) con OpenAI/Claude come opzione dichiarata, DPIA-friendly.
24. **Pubblicare il benchmark legale italiano** (gold set + harness + risultati): non esiste nulla di simile ed è la mossa che posiziona il progetto come riferimento.
25. Infra deployabile: Qdrant in Terraform (o Qdrant Cloud EU), sql_user, secret, SA dedicate, CD, backup verificati.

---

## Punti di forza da preservare

- Modellazione del dominio (`schemas/norm.py`, `citation.py`): number-as-string con bis/ter, `NormComma` con vigenza propria, `NormCommaLetter`, 25 sigle canoniche, `to_display()`/`to_anchor()` — vera competenza giuridica italiana, rara.
- Architettura retrieval a 3 vie (dense + lessicale + lookup deterministico per articolo) con RRF: concettualmente corretta, va solo resa operativa.
- Validazione citazioni post-generazione + banner UI: l'embrione del trust layer che il mercato considera lo standard.
- Chunking multi-granularità, disciplina async, immutabilità, structlog, toolchain (uv, ruff, mypy strict): l'infrastruttura di qualità è montata, mancano i contenuti.
- Parser AKN con misure di qualità dichiarate e fixture reali committate con licenza dati documentata.
