#!/usr/bin/env bash
# Harvest massivo SentenzeWeb → Postgres + Qdrant. Resumabile e idempotente
# (external_id): rilanciare riprende da dove era arrivato.
#
# Uso:   nohup scripts/harvest_cassazione_full.sh [MAX_PER_KIND] > /tmp/harvest_cassazione.log 2>&1 &
# Stato: grep -c "batch_loaded" /tmp/harvest_cassazione.log
#
# Costi (embeddings OpenAI text-embedding-3-small): ~5.8 chunk/sentenza ×
# ~620 token ≈ 0.007 € per sentenza → 100k sentenze ≈ 7 €.
# Il corpus completo è ~426k sentenze ≈ 30 € di soli embeddings.
set -euo pipefail
cd "$(dirname "$0")/.."

MAX_PER_KIND="${1:-100000}"
BATCH=2000  # sentenze per invocazione: commit incrementali, ripartenza pulita

for kind in snpen snciv; do
  echo "=== harvest $kind (max $MAX_PER_KIND) ==="
  done_count=0
  while [ "$done_count" -lt "$MAX_PER_KIND" ]; do
    out=$(uv run caucus-ingest ingest-cassazione --kind "$kind" --max "$BATCH" --rows 50 2>&1 | tail -3)
    echo "$out"
    # "✓ Cassazione snpen: N sentenze indicizzate."
    n=$(echo "$out" | grep -oE '[0-9]+ sentenze' | grep -oE '[0-9]+' || echo 0)
    done_count=$((done_count + n))
    if [ "$n" -eq 0 ]; then
      echo "$kind: nessuna sentenza nuova (fine archivio o tutte già presenti)"
      break
    fi
  done
done
echo "=== harvest completo ==="
