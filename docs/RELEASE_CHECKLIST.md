# Checklist di pubblicazione (prima release open source di Caucus)

Aggiornata al 2026-07-31. Preparato tutto, **non pubblicato**.

## Risolto ✅

- [x] **Rename dei package** `avvocato_*` → `caucus_*` completato (package
      Python, entry point CLI `caucus-ingest`, npm `@caucus/web`, Makefile,
      script, docs, Dockerfile). Restano volutamente invariati i nomi
      dell'infra locale (container docker `avvocato-*`, db/utente Postgres
      `avvocato`): rinominarli distruggerebbe i volumi locali con il corpus;
      sono default di sviluppo, non identità del progetto.
- [x] **Licenze decise**: codice **AGPL-3.0** (`LICENSE`), `benchmark/`
      **MIT** (`benchmark/LICENSE`, titolare "Caucus contributors").
- [x] **Verifica disponibilità nome** (2026-07-31):
      GitHub `caucus` e `caucus-legal` **liberi**; PyPI `caucus-bench`
      **libero** (`caucus` puro occupato → usare nomi `caucus-*`, già così);
      npm `caucus` occupato (irrilevante: scope `@caucus` da registrare
      creando l'org npm); domini: `caucus.it` registrato da terzi,
      `caucuslegal.it` e `getcaucus.com` senza DNS (probabilmente liberi;
      verificare sul registrar al momento dell'acquisto).
      ⚠️ La verifica **marchio** (EUIPO/UIBM, classe software/servizi legali)
      è una verifica legale: farla fare prima del lancio commerciale.
- [x] **Storia git: si pubblica integrale.** Decisione motivata: i commit
      documentano il percorso del benchmark (numeri prima/dopo in ogni
      messaggio) e sono l'asset di credibilità del posizionamento "numeri
      onesti"; verificato che non contengono segreti. In italiano: coerente
      con un progetto di diritto italiano.
- [x] Docs allineate alla realtà: `ARCHITECTURE.md` riscritto sul sistema
      reale; `SECURITY/INGESTION/DATA_MODEL.md` con banner di stato espliciti
      (design target vs implementato).
- [x] Governance completa: README EN+IT, CONTRIBUTING, CoC,
      `.github/SECURITY.md`, issue/PR template, CHANGELOG, CITATION.cff,
      `benchmark/RESULTS.md` (leaderboard con prima entry).
- [x] Chiave OpenAI: resta nel `.env` locale, che è gitignorato e non entra
      nel repo (deciso dall'owner).

## Da fare AL momento del publish (richiede il repo remoto)

- [x] **Pubblicato su `github.com/gral-digital/caucus`** (2026-08-01):
      l'org non è creabile via API, quindi si è partiti sotto l'account
      owner; un transfer futuro a un'org mantiene i redirect. Branch
      protection su `main` (CI obbligatoria, no force-push) attivata.
- [ ] Attivare **GitHub private vulnerability reporting** (Security tab):
      `.github/SECURITY.md` già lo indica come canale.
- [ ] Badge CI nel README dopo il primo run di GitHub Actions.
- [ ] Tag `v0.1.0` + GitHub Release con il CHANGELOG.
- [ ] Registrare scope npm `@caucus` e (se si pubblicherà) i nomi PyPI
      `caucus-*`.
- [ ] **Pubblicare il pacchetto corpus** (`make corpus-export`, ~3.9 GB) su
      hosting statico: lo snapshot `cassazione` (3 GB) supera il limite di
      2 GB dei release asset GitHub → HuggingFace datasets / R2 / split.
      Poi sostituire `SRC=<url>` nei README e in /docs con l'URL reale.
      Rifare l'export con l'harvest FERMO per conteggi Qdrant esatti.
- [ ] Aprire Discussions; creare 3-5 issue "good first issue" (candidati:
      nuove fonti dal catalogo, casi benchmark per materie scoperte,
      consolidato EUR-Lex).

## Facoltativi consigliati

- [ ] Fixture AKN (~51 MB nel repo): valutare Git LFS o release asset; nel
      frattempo il peso è accettabile e documentato (le fixture rendono i
      test del parser riproducibili offline: valore > costo).
- [ ] Screenshot/GIF della chat con pannello citazioni nel README.
- [ ] Annuncio: il claim centrale è il benchmark aperto con hallucination 0%
      misurato: non promettere oltre i numeri.
