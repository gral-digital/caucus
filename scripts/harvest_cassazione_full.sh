#!/usr/bin/env bash
# Harvest massivo SentenzeWeb → Postgres + Qdrant. Resumabile e idempotente
# (external_id): rilanciare riprende da dove era arrivato.
#
# Uso:   nohup scripts/harvest_cassazione_full.sh [MAX_PER_KIND] > /tmp/harvest_cassazione.log 2>&1 &
# Stato: grep -c "batch_loaded" /tmp/harvest_cassazione.log
#
# Robustezza (l'harvest è morto tre volte per errori transitori con `set -e`):
# - retry con backoff sui batch falliti, si arrende solo dopo
#   $MAX_CONSECUTIVE_FAILURES fallimenti consecutivi;
# - lock file contro le doppie istanze (già successo: due copie in parallelo).
#
# Costi (embeddings OpenAI text-embedding-3-small): ~5.8 chunk/sentenza ×
# ~620 token ≈ 0.007 € per sentenza → 100k sentenze ≈ 7 €.
# Il corpus completo è ~426k sentenze ≈ 30 € di soli embeddings.
set -uo pipefail
cd "$(dirname "$0")/.."

MAX_PER_KIND="${1:-100000}"
BATCH=2000  # sentenze per invocazione: commit incrementali, ripartenza pulita
MAX_CONSECUTIVE_FAILURES=5

LOCKDIR=/tmp/harvest_cassazione.lock
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "harvest già in esecuzione (lock: $LOCKDIR), esco. Se è un lock orfano: rmdir $LOCKDIR"
  exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

for kind in snpen snciv; do
  echo "=== harvest $kind (max $MAX_PER_KIND) ==="
  done_count=0
  failures=0
  while [ "$done_count" -lt "$MAX_PER_KIND" ]; do
    if out=$(uv run caucus-ingest ingest-cassazione --kind "$kind" --max "$BATCH" --rows 50 2>&1 | tail -3); then
      failures=0
      echo "$out"
      # "✓ Cassazione snpen: N sentenze indicizzate."
      n=$(echo "$out" | grep -oE '[0-9]+ sentenze' | grep -oE '[0-9]+' || echo 0)
      done_count=$((done_count + n))
      if [ "$n" -eq 0 ]; then
        echo "$kind: nessuna sentenza nuova (fine archivio o tutte già presenti)"
        break
      fi
    else
      failures=$((failures + 1))
      echo "$kind: batch fallito ($failures/$MAX_CONSECUTIVE_FAILURES consecutivi), ultimo output:"
      echo "$out"
      if [ "$failures" -ge "$MAX_CONSECUTIVE_FAILURES" ]; then
        echo "$kind: troppi fallimenti consecutivi, passo oltre (rilanciare per riprendere)"
        break
      fi
      sleep $((60 * failures))  # backoff: rate limit / rete / servizio giù
    fi
  done
done
echo "=== harvest completo ==="
