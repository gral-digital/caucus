# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/) · versioni [SemVer](https://semver.org/).

## [Unreleased] — verso la prima release pubblica come **Caucus**

### Added
- **Landing page** a `/` (l'app vive su `/app`): hero «L'accuratezza legale
  non si dichiara. Si dimostra.», banda numeri onesti con varianza
  dichiarata, quattro moduli, sezione trust layer e self-hosting, CTA
  GitHub. Zero claim non verificabili.
- **Thinking onesto in chat**: eventi SSE `status` con le fasi REALI della
  pipeline (analisi, fonti selezionate, verifica citazioni, eventuale
  riparazione) mostrate live durante l'elaborazione — incluso il silenzio
  post-streaming che prima sembrava un blocco — e collassate a fine
  risposta in «N fonti consultate · N citazioni verificate», espandibili.
  L'evento `done` riporta i conteggi di verifica.
- **Add-in Word (v0, non ancora collaudato in Word reale)**: taskpane
  Office.js (`apps/word-addin/` + statici in `apps/web/public/word-addin/`)
  con ricerca giuridica via SSE, inserimento della risposta nel documento
  (citazioni in forma canonica) e **verifica delle citazioni del documento
  aperto** contro il corpus via `POST /citations/validate` — esistenza,
  vigenza, abrogazione, con esiti verde/giallo/rosso. Manifest validato,
  istruzioni di sideload nel README; fuori da Word la pagina degrada con
  avviso e ricerca comunque funzionante.
- **Endpoint `POST /citations/validate`**: il trust layer come servizio —
  estrae i riferimenti (tag e prosa) da un testo arbitrario e li valida
  contro il corpus.
- **Modulo Giurisprudenza**: ricerca negli orientamenti della Cassazione.
  In questa modalità l'ordine dei corpora si inverte (Cassazione primaria
  nel retrieval, normativa di supporto — l'ordine di `query.corpora` è ora
  semantico nel retriever) e il prompt raggruppa per orientamento
  (prevalente/minoritario), cita le decisioni in prosa con gli estremi e
  collega i principî alle norme con `<cite/>`; vietato estrapolare
  orientamenti da sentenze non recuperate.
- **Workspace a quattro moduli** (Ricerca giuridica / Analisi documenti /
  Redazione / Giurisprudenza): sidebar navigabile, welcome ed esempi dedicati per modulo,
  conversazioni indipendenti che sopravvivono al cambio modulo.
  `ChatRequest.mode` orienta il comportamento: in analisi l'assistente
  richiede il documento e struttura i rilievi per rischio con norme citate;
  in redazione produce subito una bozza d'atto completa (premesse/diritto/
  conclusioni, campi mancanti segnalati come [DA COMPLETARE]) pronta per
  l'export Word.
- **Analisi documentale (v1)**: upload di .docx/.pdf (`POST /documents`,
  testo estratto all'upload, file originale non conservato; PDF scansionati
  rifiutati con errore chiaro — niente OCR silenzioso), allegato alla chat
  via `document_ids`. Il documento entra nel prompt come fatti del caso
  (cap 30k char/doc con troncamento dichiarato al modello), l'incipit
  alimenta la query di retrieval (il dominio del documento fa emergere la
  normativa giusta), e le clausole si citano in prosa — i tag `<cite/>`
  restano riservati alle norme, così il trust layer non valida mai una
  clausola come fonte normativa. UI: graffetta + chip documento in chat.
- **Export del parere in Word** (`POST /export/docx` + bottone in chat): il
  server ri-verifica le citazioni contro il corpus al momento dell'export e
  produce un .docx con formattazione da studio (Times New Roman, corpo
  giustificato, numeri di pagina), riferimenti in forma citazionale canonica
  e allegato «Riferimenti normativi» con rubrica, testo e stato di vigenza —
  con avvertenza esplicita su disposizioni abrogate o non trovate. Nota di
  trasparenza AI in coda al documento.
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
  aperto — 171 casi, metriche source-aware, hallucination rate solo sulle
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
- **Query expansion strutturata**: l'espansione LLM restituisce, oltre alla
  query arricchita, fino a 6 articoli candidati in formato `sigla numero`
  validati contro il catalogo delle fonti (SOURCE_CATALOG); i candidati
  entrano nel merge come lookup non pinnato. Chiude il gap sulle query
  concettuali (fonti senza forma canonica: cts, cnav, cpriv, wb, tub…) e sui
  quesiti su articoli abrogati ("l'ingiuria è ancora reato?" → cp 594).
  Modello di espansione di riferimento: gpt-4o (misurato 8/14 vs 5/14 articoli
  attesi rispetto a gpt-4o-mini sui casi difficili). Con FTS ristretto alle
  fonti dei candidati e riparazione citazioni: pass 85%→96%, recall@8
  85%→97%, MRR 0.74→0.87-0.89 sul gold v2.3.
- **Trust layer auto-correttivo**: se la validazione post-generazione trova
  citazioni inesistenti, una singola passata di riparazione riscrive la
  risposta correggendo o rimuovendo i riferimenti non verificabili (prima:
  solo warning). Hallucination rate resta 0% anche nei run in cui la bozza
  ne conteneva.
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

### Fixed
- UX chat: campo input allineato in verticale (l'auto-grow misurava
  l'altezza durante il primo layout e bloccava il campo a 2-3 righe
  fantasma), focus ripristinato dopo l'invio, «Nuova conversazione» azzera
  il modulo attivo senza ricaricare la pagina (gli altri moduli mantengono
  lo stato).
- **Fallback silenzioso del reranker**: con `RERANKER_BACKEND=local` ma
  `sentence-transformers` assente dal venv, la factory ripiegava sul keyword
  reranker senza segnalarlo, degradando il ranking (parte del calo di recall
  attribuito alla crescita del corpus era questo). Ora l'extra
  `reranker-local` è installato di default (`caucus-rag-core[reranker-local]`
  in apps/api) e il fallback emette un warning esplicito.
- Parser dei riferimenti d'espansione: scarto degli intervalli («wb 1-21»)
  e della punteggiatura di coda («cpp 369-bis.»), che producevano lookup
  mai risolvibili.
- Router: riconoscimento guida in stato alterato da stupefacenti (art. 187
  CdS, prima suggeriva sempre il 186) e forme verbali colloquiali
  ("guido", "ubriaco", "bevuto").

### Security
- Endpoint chiusi di default fuori da `app_env=local`; errori interni mai
  esposti al client; sessione DB gestita correttamente nello streaming SSE.

> Storia dettagliata pre-release: `git log` (commit in italiano, con numeri
> di benchmark nei messaggi).
