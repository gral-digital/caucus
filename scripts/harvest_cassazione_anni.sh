#!/usr/bin/env bash
# Harvest SentenzeWeb per ANNI SPECIFICI → Postgres + Qdrant. Colma il buco
# di copertura temporale: l'harvest standard pagina dal più recente e il
# corpus resta schiacciato sugli ultimi anni (misurato in prod 2026-08-10:
# solo 2025+; mancava perfino Cass. SS.UU. n. 41570/2023).
#
# Uso:   nohup scripts/harvest_cassazione_anni.sh [ANNI...] > /tmp/harvest_cassazione_anni.log 2>&1 &
#        default: 2024 2023 2022 2021 (dal più recente: prima il valore più alto)
# Stato: tail -f /tmp/harvest_cassazione_anni.log
#
# Disponibilità misurata su SentenzeWeb (2026-08-10): snpen 2022-2024
# ~50k/anno, snciv 2021-2024 ~19-38k/anno, 2020 assente (finestra di
# retention). Costi embeddings: ~0.007 €/sentenza → l'intero 2021-2024
# (~280k sentenze) ≈ 20 € OpenAI.
#
# Resumabile e idempotente (external_id): rilanciare riprende da dove era.
set -uo pipefail
cd "$(dirname "$0")/.."

ANNI=("${@:-}")
if [ -z "${ANNI[0]:-}" ]; then
  ANNI=(2024 2023 2022 2021)
fi
BATCH=2000  # sentenze per invocazione: commit incrementali, ripartenza pulita
MAX_CONSECUTIVE_FAILURES=5

LOCKDIR=/tmp/harvest_cassazione.lock  # stesso lock del full: mai due harvest insieme
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "harvest già in esecuzione (lock: $LOCKDIR), esco. Se è un lock orfano: rmdir $LOCKDIR"
  exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

for anno in "${ANNI[@]}"; do
  for kind in snpen snciv; do
    echo "=== harvest $kind anno $anno ==="
    failures=0
    while true; do
      if out=$(uv run caucus-ingest ingest-cassazione --kind "$kind" --anno "$anno" --max "$BATCH" --rows 50 2>&1 | tail -3); then
        failures=0
        echo "$out"
        n=$(echo "$out" | grep -oE '[0-9]+ sentenze' | grep -oE '[0-9]+' || echo 0)
        if [ "$n" -eq 0 ]; then
          echo "$kind $anno: completo (fine archivio o tutte già presenti)"
          break
        fi
      else
        failures=$((failures + 1))
        echo "$kind $anno: batch fallito ($failures/$MAX_CONSECUTIVE_FAILURES consecutivi), ultimo output:"
        echo "$out"
        if [ "$failures" -ge "$MAX_CONSECUTIVE_FAILURES" ]; then
          echo "$kind $anno: troppi fallimenti consecutivi, passo oltre (rilanciare per riprendere)"
          break
        fi
        sleep $((60 * failures))  # backoff: rate limit / rete / servizio giù
      fi
    done
  done
done
echo "=== harvest per anni completo ==="
