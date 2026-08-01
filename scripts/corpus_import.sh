#!/usr/bin/env bash
# Importa un pacchetto corpus prodotto da corpus_export.sh in uno stack
# Caucus locale: sostituisce le tabelle corpus di Postgres e le collection
# Qdrant. Le tabelle utente (user_account, user_document, auth_session)
# non vengono toccate.
#
# Uso:
#   scripts/corpus_import.sh /percorso/directory-pacchetto
#   scripts/corpus_import.sh https://host/path/caucus-corpus-YYYYMMDD
#
# Con un URL, i file vengono scaricati in dist/corpus-download/ (ripresa
# automatica dei download interrotti) e poi importati.
set -euo pipefail

cd "$(dirname "$0")/.."

PG_CONTAINER="${PG_CONTAINER:-avvocato-postgres}"
PG_USER="${PG_USER:-avvocato}"
PG_DB="${PG_DB:-avvocato}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_API_KEY="${QDRANT_API_KEY:-$(grep -E '^QDRANT_API_KEY=' .env 2>/dev/null | cut -d= -f2- || true)}"
QDRANT_API_KEY="${QDRANT_API_KEY:-local-dev-key}"

SRC="${1:?Uso: corpus_import.sh <directory|url-base del pacchetto>}"

# --- Download (se SRC è un URL) --------------------------------------------
if [[ "$SRC" == http://* || "$SRC" == https://* ]]; then
  BASE_URL="${SRC%/}"
  DL="dist/corpus-download/$(basename "$BASE_URL")"
  mkdir -p "$DL"
  echo "==> Scarico il manifest da ${BASE_URL}…"
  curl -fL --retry 3 -o "${DL}/manifest.json" "${BASE_URL}/manifest.json"
  # I file possono essere pubblicati in parti (limite 2 GB di molti hosting):
  # in quel caso si scaricano le parti elencate nel manifest.
  DOWNLOADS=$(python3 -c '
import json
manifest = json.load(open("'"$DL"'/manifest.json"))
names = []
for name, meta in manifest["files"].items():
    names.extend(meta.get("parts") or [name])
print("\n".join(names))')
  for f in $DOWNLOADS; do
    echo "==> Scarico ${f}…"
    curl -fL --retry 3 -C - -o "${DL}/${f}" "${BASE_URL}/${f}"
  done
  SRC="$DL"
fi

MANIFEST="${SRC}/manifest.json"
[[ -f "$MANIFEST" ]] || { echo "ERRORE: manca ${MANIFEST}" >&2; exit 1; }

# --- Preflight -------------------------------------------------------------
docker exec "$PG_CONTAINER" true 2>/dev/null || {
  echo "ERRORE: container Postgres '$PG_CONTAINER' non raggiungibile (make up?)" >&2
  exit 1
}
curl -sf -H "api-key: ${QDRANT_API_KEY}" "${QDRANT_URL}/collections" >/dev/null || {
  echo "ERRORE: Qdrant non raggiungibile su ${QDRANT_URL}" >&2
  exit 1
}

echo "==> Riassemblo le eventuali parti e verifico i checksum…"
python3 - "$SRC" <<'PYEOF'
import hashlib, json, pathlib, sys
src = pathlib.Path(sys.argv[1])
manifest = json.loads((src / "manifest.json").read_text())
for name, meta in manifest["files"].items():
    path = src / name
    parts = meta.get("parts")
    if parts and not path.exists():
        for p in parts:
            if not (src / p).exists():
                sys.exit(f"ERRORE: parte mancante {p}")
        with open(path, "wb") as out:
            for p in parts:
                with open(src / p, "rb") as fh:
                    while block := fh.read(1 << 20):
                        out.write(block)
    if not path.exists():
        sys.exit(f"ERRORE: file mancante {name}")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    if h.hexdigest() != meta["sha256"]:
        sys.exit(f"ERRORE: checksum errato per {name} (download corrotto?)")
print("    checksum ok per", len(manifest["files"]), "file")
PYEOF

WANT_REV=$(python3 -c 'import json;print(json.load(open("'"$MANIFEST"'"))["alembic_revision"])')
HAVE_REV="$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc 'SELECT version_num FROM alembic_version' 2>/dev/null || echo none)"
if [[ "$HAVE_REV" != "$WANT_REV" ]]; then
  echo "ERRORE: il pacchetto è per la revisione schema ${WANT_REV}, il DB è a '${HAVE_REV}'." >&2
  echo "        Esegui 'make migrate' (o aggiorna il codice) e riprova." >&2
  exit 1
fi

# --- Postgres: truncate + restore ------------------------------------------
CORPUS_TABLES="norm_chunk, norm_citation, norm_comma, norm_partition, norm_source, case_law_chunk, case_law"
echo "==> Svuoto le tabelle corpus e ripristino il dump…"
docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" \
  -c "TRUNCATE ${CORPUS_TABLES} CASCADE" >/dev/null
docker exec -i "$PG_CONTAINER" pg_restore -U "$PG_USER" -d "$PG_DB" \
  --data-only --disable-triggers --exit-on-error \
  < "${SRC}/postgres_corpus.dump"

# --- Qdrant: recover degli snapshot ----------------------------------------
for snap in "${SRC}"/qdrant_*.snapshot; do
  c="$(basename "$snap" .snapshot)"; c="${c#qdrant_}"
  echo "==> Ripristino collection Qdrant '${c}' (può richiedere minuti)…"
  curl -sf -X POST -H "api-key: ${QDRANT_API_KEY}" \
    -F "snapshot=@${snap}" \
    "${QDRANT_URL}/collections/${c}/snapshots/upload?priority=snapshot" \
    | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r.get("result") is True, r'
done

# --- Verifica finale --------------------------------------------------------
echo "==> Verifica conteggi…"
python3 - "$SRC" <<PYEOF
import json, subprocess, sys, urllib.request
src = sys.argv[1]
manifest = json.loads(open(f"{src}/manifest.json").read())
ok = True
for table, want in manifest["postgres_tables"].items():
    have = int(subprocess.check_output(
        ["docker", "exec", "${PG_CONTAINER}", "psql", "-U", "${PG_USER}",
         "-d", "${PG_DB}", "-tAc", f"SELECT count(*) FROM {table}"]).strip())
    mark = "✓" if have == want else "✗"
    if have != want: ok = False
    print(f"    {mark} {table}: {have} (atteso {want})")
for coll, want in manifest["qdrant_collections"].items():
    req = urllib.request.Request(
        "${QDRANT_URL}/collections/" + coll,
        headers={"api-key": "${QDRANT_API_KEY}"})
    have = json.load(urllib.request.urlopen(req))["result"]["points_count"]
    # I conteggi Qdrant del manifest sono presi subito prima dello snapshot:
    # se l'export girava con un'ingestione attiva possono divergere di poco.
    # Oltre l'1% è un problema reale.
    if have == want:
        print(f"    ✓ qdrant/{coll}: {have} punti")
    elif abs(have - want) <= max(10, want // 100):
        print(f"    ⚠ qdrant/{coll}: {have} punti (manifest {want}; "
              "scarto da export con ingestione attiva)")
    else:
        ok = False
        print(f"    ✗ qdrant/{coll}: {have} punti (atteso {want})")
sys.exit(0 if ok else 1)
PYEOF

echo
echo "✓ Import completato. Avvia l'app con: make dev"
