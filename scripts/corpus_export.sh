#!/usr/bin/env bash
# Esporta il corpus indicizzato (Postgres + Qdrant) in un pacchetto
# ridistribuibile, così un'installazione self-hosted può partire senza
# rifare l'ingestione né pagare gli embedding.
#
# Contenuto del pacchetto (directory dist/corpus/caucus-corpus-<data>/):
#   manifest.json               versione, conteggi, checksum, revisione schema
#   README.md                   cos'è, licenze dei dati, come importare
#   postgres_corpus.dump        pg_dump -Fc data-only delle tabelle corpus
#   qdrant_<collection>.snapshot  uno snapshot per collection
#
# I file sono separati (niente tar monolitico): si pubblicano così come sono
# su qualunque hosting statico (GitHub Release, HuggingFace, R2…) e
# corpus_import.sh li consuma da directory locale o da URL base.
#
# Uso: scripts/corpus_export.sh [outdir]   (default: dist/corpus)
set -euo pipefail

cd "$(dirname "$0")/.."

PG_CONTAINER="${PG_CONTAINER:-avvocato-postgres}"
PG_USER="${PG_USER:-avvocato}"
PG_PASSWORD="${PG_PASSWORD:-avvocato}"
PG_DB="${PG_DB:-avvocato}"
PG_PORT="${PG_PORT:-55432}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_API_KEY="${QDRANT_API_KEY:-$(grep -E '^QDRANT_API_KEY=' .env 2>/dev/null | cut -d= -f2- || true)}"
QDRANT_API_KEY="${QDRANT_API_KEY:-local-dev-key}"

# Solo dati del corpus: MAI tabelle utente (user_document, user_account,
# auth_session) né alembic_version (lo schema arriva dalle migration).
CORPUS_TABLES=(norm_source norm_partition norm_comma norm_citation norm_chunk case_law case_law_chunk)

DATE_TAG="$(date +%Y%m%d)"
OUT_ROOT="${1:-dist/corpus}"
OUT="${OUT_ROOT}/caucus-corpus-${DATE_TAG}"
mkdir -p "$OUT"

echo "==> Export corpus in ${OUT}"

# --- Preflight -------------------------------------------------------------
docker exec "$PG_CONTAINER" true 2>/dev/null || {
  echo "ERRORE: container Postgres '$PG_CONTAINER' non raggiungibile (make up?)" >&2
  exit 1
}
curl -sf -H "api-key: ${QDRANT_API_KEY}" "${QDRANT_URL}/collections" >/dev/null || {
  echo "ERRORE: Qdrant non raggiungibile su ${QDRANT_URL}" >&2
  exit 1
}

ALEMBIC_REV="$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc 'SELECT version_num FROM alembic_version')"
GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

if pgrep -f harvest_cassazione >/dev/null 2>&1; then
  echo "⚠  Harvest Cassazione attivo: dump e conteggi Postgres restano"
  echo "   consistenti (snapshot condiviso), ma i conteggi Qdrant possono"
  echo "   divergere di qualche punto. Per un pacchetto di release, ferma"
  echo "   prima l'harvest."
fi

# --- Postgres: dump data-only + conteggi sullo STESSO snapshot MVCC --------
# pg_export_snapshot(): i conteggi nel manifest fotografano esattamente il
# contenuto del dump anche se l'harvest sta scrivendo.
echo "==> pg_dump (data-only, formato custom compresso)…"
TABLE_ARGS=""
for t in "${CORPUS_TABLES[@]}"; do TABLE_ARGS+="--table=${t} "; done
COUNTS_JSON=$(uv run python - <<PYEOF
import asyncio, json, subprocess, sys

TABLES = "${CORPUS_TABLES[*]}".split()
DSN = "postgresql://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DB}"

async def main() -> None:
    import asyncpg
    conn = await asyncpg.connect(DSN)
    tx = conn.transaction(isolation="repeatable_read")
    await tx.start()
    snapshot = await conn.fetchval("SELECT pg_export_snapshot()")
    counts = {t: await conn.fetchval(f"SELECT count(*) FROM {t}") for t in TABLES}
    dump = subprocess.run(
        ["docker", "exec", "${PG_CONTAINER}", "pg_dump", "-U", "${PG_USER}",
         "-d", "${PG_DB}", "--data-only", "--format=custom", "--compress=6",
         f"--snapshot={snapshot}"] + "${TABLE_ARGS}".split(),
        stdout=open("${OUT}/postgres_corpus.dump", "wb"),
    )
    await tx.rollback()
    await conn.close()
    if dump.returncode != 0:
        sys.exit(dump.returncode)
    print(json.dumps(counts))

asyncio.run(main())
PYEOF
)
echo "    $(du -h "${OUT}/postgres_corpus.dump" | cut -f1)"

# --- Qdrant: uno snapshot per collection -----------------------------------
COLLECTIONS_JSON="$(curl -sf -H "api-key: ${QDRANT_API_KEY}" "${QDRANT_URL}/collections")"
COLLECTIONS=$(printf '%s' "$COLLECTIONS_JSON" | python3 -c '
import json, sys
print("\n".join(c["name"] for c in json.load(sys.stdin)["result"]["collections"]))')

QDRANT_COUNTS="{"
for c in $COLLECTIONS; do
  echo "==> Snapshot Qdrant '${c}'…"
  # Conteggio immediatamente prima dello snapshot (finestra di drift minima
  # se un'ingestione sta scrivendo).
  n=$(curl -sf -H "api-key: ${QDRANT_API_KEY}" "${QDRANT_URL}/collections/${c}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["points_count"])')
  QDRANT_COUNTS+="\"${c}\": ${n},"
  SNAP_NAME=$(curl -sf -X POST -H "api-key: ${QDRANT_API_KEY}" \
    "${QDRANT_URL}/collections/${c}/snapshots" | python3 -c '
import json, sys
print(json.load(sys.stdin)["result"]["name"])')
  curl -sf -H "api-key: ${QDRANT_API_KEY}" \
    -o "${OUT}/qdrant_${c}.snapshot" \
    "${QDRANT_URL}/collections/${c}/snapshots/${SNAP_NAME}"
  # Lo snapshot resta anche sul server: eliminarlo per non accumulare GB.
  curl -sf -X DELETE -H "api-key: ${QDRANT_API_KEY}" \
    "${QDRANT_URL}/collections/${c}/snapshots/${SNAP_NAME}" >/dev/null
  echo "    $(du -h "${OUT}/qdrant_${c}.snapshot" | cut -f1)"
done
QDRANT_COUNTS="${QDRANT_COUNTS%,}}"

# --- Manifest con conteggi e checksum --------------------------------------
echo "==> Manifest e checksum…"

# File sopra 1900 MB: divisi in parti, perché molti hosting (release asset
# GitHub inclusi) rifiutano file oltre 2 GB. Il checksum resta quello del
# file intero; l'import riassembla le parti e verifica.
SPLIT_BYTES=$((1900 * 1024 * 1024))
FILES_JSON="{"
for f in "$OUT"/*.dump "$OUT"/*.snapshot; do
  base="$(basename "$f")"
  sha=$(shasum -a 256 "$f" | cut -d' ' -f1)
  size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f")
  if [ "$size" -gt "$SPLIT_BYTES" ]; then
    echo "==> ${base} supera 1.9 GB: split in parti…"
    split -b 1900m "$f" "${f}.part"
    rm "$f"
    PARTS=$(cd "$OUT" && ls "${base}".part* | sort | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().split()))')
    FILES_JSON+="\"${base}\": {\"sha256\": \"${sha}\", \"bytes\": ${size}, \"parts\": ${PARTS}},"
  else
    FILES_JSON+="\"${base}\": {\"sha256\": \"${sha}\", \"bytes\": ${size}},"
  fi
done
FILES_JSON="${FILES_JSON%,}}"

python3 - "$OUT" <<PYEOF
import json, sys, datetime
out = sys.argv[1]
manifest = {
    "format_version": 1,
    "name": "caucus-corpus",
    "date": "${DATE_TAG}",
    "git_commit": "${GIT_COMMIT}",
    "alembic_revision": "${ALEMBIC_REV}",
    "embedding_model": "text-embedding-3-small",
    "embedding_dim": 1536,
    "postgres_tables": json.loads('''${COUNTS_JSON}'''),
    "qdrant_collections": json.loads('''${QDRANT_COUNTS}'''),
    "files": json.loads('''${FILES_JSON}'''),
    "note": "Conteggi Postgres esatti (stesso snapshot MVCC del dump). "
            "Conteggi Qdrant rilevati subito prima dello snapshot: con "
            "un'ingestione attiva possono divergere di poche unità.",
}
with open(f"{out}/manifest.json", "w") as fh:
    json.dump(manifest, fh, indent=2, ensure_ascii=False)
PYEOF

cat > "${OUT}/README.md" <<'MDEOF'
# Pacchetto corpus Caucus

Corpus legale italiano già indicizzato (Postgres + embedding Qdrant) per
installazioni self-hosted di Caucus: importandolo si salta l'ingestione
completa e non serve alcuna chiamata di embedding.

## Import

Dalla root del repository Caucus, con l'infra locale attiva (`make up`):

```bash
make corpus-import SRC=/percorso/a/questa/directory
# oppure direttamente da un hosting remoto:
make corpus-import SRC=https://esempio.org/caucus-corpus-YYYYMMDD
```

Lo script verifica i checksum, controlla la revisione dello schema,
sostituisce le tabelle corpus e ripristina le collection Qdrant.
Le tabelle utente (account, documenti caricati) non vengono toccate.

## Contenuto e licenze dei dati

- **Norme** (Normattiva, formato Akoma Ntoso) ed **atti UE** (EUR-Lex):
  atti ufficiali dello Stato e dell'Unione, esclusi dalla protezione del
  diritto d'autore (art. 5 L. 633/1941; decisione 2011/833/UE).
- **Giurisprudenza**: provvedimenti della Corte di Cassazione nella forma
  anonimizzata pubblicata da SentenzeWeb (pubblicità legale ex art. 51
  D.Lgs. 82/2005). Nessun dato personale aggiuntivo rispetto alla fonte.
- **Embedding e chunking**: prodotti dal progetto Caucus, rilasciati con
  la stessa licenza del benchmark (MIT). Il codice resta AGPL-3.0.

Il corpus è ricostruibile da zero dalle fonti pubbliche con
`make seed-all` + `make harvest-cassazione` (vedi documentazione).
MDEOF

echo
echo "✓ Export completato: ${OUT}"
du -sh "$OUT"
echo "  Pubblica il CONTENUTO della directory su hosting statico e importa"
echo "  con: make corpus-import SRC=<dir|url>"
