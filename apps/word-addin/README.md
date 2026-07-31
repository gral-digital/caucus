# Caucus per Word (add-in)

Taskpane Office.js con due funzioni:

- **Ricerca**: domanda giuridica → risposta con citazioni verificate
  (stessa API della web app), inseribile nel documento al cursore.
- **Verifica citazioni**: legge il documento aperto, estrae i riferimenti
  normativi (tag e prosa, es. «art. 2043 c.c.») e li valida contro il
  corpus — esistenza, vigenza, **abrogazione** — via
  `POST /api/v1/citations/validate`.

Il pannello è servito dalla web app Next
(`apps/web/public/word-addin/taskpane.html`), stessa origin dell'API via
rewrite → niente CORS. Fuori da Word la pagina mostra un avviso e disabilita
le funzioni documento.

## Sviluppo locale

Word carica solo sorgenti **HTTPS**. Avviare la web app con TLS locale:

```bash
cd apps/web && pnpm dev --experimental-https
```

(genera certificati self-signed via mkcert; fidarli al primo avvio), con
l'API su :8000 come al solito.

### Sideload — Word per Mac

```bash
cp apps/word-addin/manifest.xml \
  ~/Library/Containers/com.microsoft.Word/Data/Documents/wef/
```

Poi in Word: **Inserisci → Componenti aggiuntivi → I miei componenti
aggiuntivi → Caucus**.

### Sideload — Word per Windows

Cartella condivisa attendibile: File → Opzioni → Centro protezione →
Cataloghi componenti aggiuntivi attendibili → aggiungere la cartella con il
manifest, poi Inserisci → Componenti aggiuntivi → Cartella condivisa.

## Stato e limiti (onesti)

- **Non ancora testato dentro Word reale**: sviluppato e verificato a
  livello di pagina (rendering, chiamate API, parsing SSE) nel browser;
  il primo collaudo in Word è nella checklist pre-release.
- Icone placeholder da produrre (`icon-16/32/80.png` in
  `apps/web/public/word-addin/`).
- In produzione: sostituire gli URL `localhost:3100` nel manifest col
  dominio pubblico e distribuire via Microsoft 365 admin (deployment
  centralizzato) — lo store richiede validazione Microsoft.
