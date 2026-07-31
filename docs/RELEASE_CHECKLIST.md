# Checklist di pubblicazione (prima release open source di Caucus)

Preparato tutto, **non pubblicato**. Prima di rendere pubblico il repo:

## Bloccanti

- [ ] **Ruotare la OPENAI_API_KEY** presente nel `.env` locale (dashboard
      OpenAI) — considerarla compromessa ai fini della pubblicazione.
- [ ] **Rename dei package** `avvocato_*` → `caucus_*` (o mantenere come
      omaggio storico — decidere). NB: rimandato finché gira l'harvest
      Cassazione (invoca la CLI `avvocato-ingest` installata). Il rename
      tocca: nomi package in `services/*/pyproject.toml` e `apps/api/`,
      import, entry point CLI, Makefile, script, docs.
- [ ] Decidere definitivamente le **licenze** (proposta attuale: codice
      AGPL-3.0, `benchmark/` MIT). Se si sceglie Apache-2.0 per adozione
      massima, sostituire LICENSE e aggiornare i README.
- [ ] Intestazione copyright in LICENSE/NOTICE con il titolare scelto
      (persona fisica o entità).
- [ ] Verificare che il nome **Caucus** sia libero (marchio, dominio, PyPI,
      npm, GitHub org) PRIMA di pubblicare.
- [ ] `git log` è in italiano con dettagli interni: decidere se pubblicare la
      storia completa o fare squash iniziale ("Initial public release").
- [ ] Canale di sicurezza: attivare GitHub private vulnerability reporting
      o pubblicare un indirizzo email in `.github/SECURITY.md`.

## Fortemente consigliati

- [ ] Aggiornare i vecchi design doc (`docs/ARCHITECTURE.md`,
      `docs/SECURITY.md`, `docs/INGESTION.md`, `docs/DATA_MODEL.md`):
      contengono ancora sezioni aspirazionali pre-audit. Marcare ciò che non
      è implementato o riscrivere.
- [ ] `CITATION.cff` per il benchmark (citazione accademica).
- [ ] Badge CI nel README dopo il primo run pubblico di GitHub Actions.
- [ ] Aprire GitHub Discussions; issue "good first issue" iniziali.
- [ ] Fixture AKN (~51 MB): valutare Git LFS o release asset per snellire il
      clone; in alternativa documentare il peso nel README.
- [ ] Screenshot/demo GIF della chat con il pannello citazioni nel README.
- [ ] `benchmark/RESULTS.md` (leaderboard) con la prima entry ufficiale.

## Al momento del publish

- [ ] Repo → GitHub, visibilità public; branch protection su `main`
      (CI verde obbligatoria, no force-push).
- [ ] Tag `v0.1.0` + GitHub Release con il CHANGELOG.
- [ ] Annuncio: il claim centrale è il benchmark aperto con hallucination
      0% misurato — non promettere oltre i numeri.
