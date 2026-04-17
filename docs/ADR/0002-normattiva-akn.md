# ADR 0002 — Normattiva AKN XML come fonte primaria per i Codici

- **Data**: 2026-04-17
- **Stato**: Accettato
- **Decisori**: founder

## Contesto

Il progetto richiede il testo **integrale e vigente** del Codice Civile (~2969 articoli + bis/ter) e Codice Penale (~734 articoli + bis/ter), preservando gerarchia (Libro/Titolo/Capo/Sezione/Articolo/Comma) e citazioni machine-readable.

Sono state valutate 5 classi di fonti:

| Fonte | Autorevole | Aggiornata | Machine-readable | Licenza | Note |
|-------|:---:|:---:|:---:|---|---|
| Normattiva (AKN XML) | ✅ | ✅ (2026) | ✅ (OASIS) | Pubblico dominio | **Scelta** |
| Wikisource | ❌ | ❌ (2022) | ⚠ (wikitext) | CC-BY-SA | Obsoleta, squalificata |
| HuggingFace datasets | ⚠ | varia | ✅ | varia | Nessun dataset con CC/CP vigenti |
| Brocardi.it / Altalex | ✅ | ✅ | ❌ | Proprietaria | ToU vieta scraping |
| Gazzetta Ufficiale | ✅ | ⚠ (solo atti) | ❌ | PD | Non ha testi consolidati dei codici |

## Decisione

**Usare Normattiva (`normattiva.it`) come fonte primaria, in formato Akoma Ntoso 3.0 XML.**

Rationale:
- **Autorevolezza**: è la banca dati ufficiale dello Stato italiano (Istituto Poligrafico e Zecca dello Stato).
- **Aggiornamento**: i testi sono consolidati e "vigenti" con tutte le modifiche applicate (verificato empiricamente: fixture scaricato il 2026-04-17 include tutte le riforme 2022-2025 testate).
- **Formato machine-readable**: AKN XML è uno standard OASIS con gerarchia nativa.
- **Licenza**: testi normativi italiani = pubblico dominio (Berne Convention art. 2(4) + L. 633/1941 art. 5). Normattiva = distribuzione dello Stato per uso libero.
- **Precedente open**: progetto civic-tech `ondata/normattiva_2_md` (MIT, attivo 2026) usa lo stesso approccio, indicando fattibilità e stabilità.

## Dettagli tecnici

**Download flow**:
1. Session-authenticated GET alla pagina permalink dell'URN → estrazione param `dataGU`, `codiceRedaz`, `dataVigenza` dal link `caricaAKN`.
2. GET a `https://www.normattiva.it/do/atto/caricaAKN?...` → ritorna l'XML AKN completo (es. CC = 10 MB, CP = 4 MB).

**Serializzazione AKN di Normattiva**:
Più "flat" dell'AKN canonico: ogni articolo è un `<attachment>` con `<doc name="...">` e un singolo `<mainBody><paragraph><content><p>` che contiene rubrica + commi concatenati. Il parser estrae rubrica (multiple forme: singole parentesi, doppie parentesi di modifica, su linea propria) e divide i commi su separatori `\n \n` o numerazioni esplicite.

**Versioning**: il parametro `dataVigenza` permette di richiedere il testo vigente a qualunque data passata → supporto nativo al versioning normativo richiesto da `effective_from/effective_to` nel nostro data model.

## Conseguenze

**Positive**
- Autorevolezza massima; output legale difendibile ("citazione di Normattiva").
- Un'unica pipeline copre Codice Civile, Penale, di Procedura, leggi speciali, d.lgs.
- Versioning date-based nativo.

**Negative**
- Dipendenza da un endpoint non ufficialmente "API". Se Normattiva cambiasse
  la struttura del link `caricaAKN`, il fetcher rompe. Mitigazione: fixture XML
  committati come snapshot; test di parsing su fixture (no live); monitoring mensile.
- La gerarchia Libro/Titolo/Capo non è codificata a livello di articolo nell'XML
  servito — va arricchita con una seconda pass. Mitigazione: fase 2.
- Download lento (richiede session cookie + responses sizable). Mitigazione:
  fixture cache + schedule settimanale.

## Fonti rifiutate (rationale)

- **Wikisource italiano**: la pagina master Codice Civile è ferma al 2022-09-17, con flag "SAL 25%" (incompleto). Mancano riforma Cartabia 2022 (penale), riforma filiazione, modifiche 2023-2025. Inaffidabile per AI legale.
- **HuggingFace `mii-llm/gazzetta-ufficiale`**: contiene *atti* della GU, non testi consolidati dei codici.
- **HuggingFace `joelniklaus/Multi_Legal_Pile`**: pretraining corpus, non strutturato per RAG.
- **Brocardi / Altalex / StudioCataldi**: ToU vietano scraping; le annotazioni dottrinali sono coperte da copyright.
- **Gazzetta Ufficiale** (`gazzettaufficiale.it/anteprima/codici/...`): ha testo consolidato in HTML ma nessuna API, DOM instabile. Utile solo per verifica puntuale.

## Open issues / follow-up

- [ ] Arricchimento gerarchia Libro/Titolo/Capo/Sezione (parsing HTML index di Normattiva).
- [ ] Schedule di refresh settimanale automatizzato.
- [ ] Alerting su drift del formato (se parsing fallisce su >5% articoli, alert).
- [ ] Verifica integrità tramite cross-check con EUR-Lex (per leggi di recepimento UE).
