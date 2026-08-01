#!/usr/bin/env bash
# Harvest massivo Giustizia Amministrativa (TAR + CdS) → Postgres + Qdrant.
# Resumabile e idempotente (external_id/ECLI): rilanciare riprende.
#
# Uso:   nohup scripts/harvest_ga_full.sh [ANNO_MIN] [MAX_PER_SEDE_ANNO] > /tmp/harvest_ga.log 2>&1 &
# Stato: grep -c "provvedimenti indicizzati" /tmp/harvest_ga.log
#
# Ordine: prima le sedi più citate, dall'anno corrente a ritroso fino a
# ANNO_MIN (default 2022). Costi embedding: ~7 € / 100k provvedimenti.
# Rate limit 0.5 req/s dentro al fetcher: un anno di una sede grande (~20k)
# richiede ~12 ore: è un processo di giorni, per questo è resumabile.
set -uo pipefail
cd "$(dirname "$0")/.."

ANNO_MIN="${1:-2022}"
MAX_PER_SEDE_ANNO="${2:-25000}"
ANNO_MAX=2026
MAX_CONSECUTIVE_FAILURES=5

SEDI=(
  "Consiglio di Stato"
  "Roma"
  "Milano"
  "Napoli"
  "C.G.A.R.S"
  "Torino"
  "Bologna"
  "Venezia"
  "Firenze"
  "Bari"
  "Palermo"
  "Catania"
  "Lecce"
  "Brescia"
  "Genova"
  "Salerno"
  "Cagliari"
  "Ancona"
  "Catanzaro"
  "Perugia"
  "Pescara"
  "Latina"
  "Trento"
  "Trieste"
  "Bolzano"
  "Parma"
  "Campobasso"
  "Potenza"
  "L'Aquila"
  "Reggio Calabria"
  "Aosta"
)

LOCKDIR=/tmp/harvest_ga.lock
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "harvest GA già in esecuzione (lock: $LOCKDIR), esco. Lock orfano: rmdir $LOCKDIR"
  exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

for anno in $(seq "$ANNO_MAX" -1 "$ANNO_MIN"); do
  for sede in "${SEDI[@]}"; do
    echo "=== GA $sede $anno ==="
    failures=0
    until out=$(uv run caucus-ingest ingest-ga --sede "$sede" --anno "$anno" \
        --max "$MAX_PER_SEDE_ANNO" 2>&1 | tail -3); do
      failures=$((failures + 1))
      echo "$sede $anno: batch fallito ($failures/$MAX_CONSECUTIVE_FAILURES): $out"
      if [ "$failures" -ge "$MAX_CONSECUTIVE_FAILURES" ]; then
        echo "$sede $anno: troppi fallimenti, passo oltre"
        break
      fi
      sleep $((60 * failures))
    done
    echo "$out"
  done
done
echo "=== harvest GA completo (>= $ANNO_MIN) ==="
