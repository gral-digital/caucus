#!/usr/bin/env bash
# Smoke test end-to-end del stack "Chiedi al Codice".
# Verifica: Postgres peupled, Qdrant popolato, /search funziona, /chat streama.

set -euo pipefail

API="${API:-http://localhost:8000}"
QDRANT="${QDRANT:-http://localhost:6333}"
QDRANT_KEY="${QDRANT_API_KEY:-local-dev-key}"
PG="psql -h localhost -p 55432 -U avvocato -d avvocato -tAX"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
ko()   { printf "  \033[31m✗\033[0m %s\n" "$1"; exit 1; }

bold "1. Postgres — conteggi"
sources=$(PGPASSWORD=avvocato $PG -c "SELECT count(*) FROM norm_source")
articoli=$(PGPASSWORD=avvocato $PG -c "SELECT count(*) FROM norm_partition WHERE kind='articolo'")
chunks=$(PGPASSWORD=avvocato $PG -c "SELECT count(*) FROM norm_chunk")
echo "  sources=$sources articoli=$articoli chunks=$chunks"
[ "$sources" -ge 2 ] && ok "2+ sources (CC + CP)" || ko "serve CC + CP"
[ "$articoli" -ge 4000 ] && ok "articoli in DB" || ko "troppo pochi articoli"
[ "$chunks" -ge 13000 ] && ok "chunk in DB" || ko "troppo pochi chunk"

bold "2. Qdrant — points"
codici_pts=$(curl -sf "${QDRANT}/collections/codici" -H "api-key: ${QDRANT_KEY}" | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['points_count'])")
echo "  codici points=$codici_pts"
[ "$codici_pts" -ge 13000 ] && ok "vettori in Qdrant" || ko "pochi vettori: $codici_pts"

bold "3. API — /health/ready"
curl -sf "${API}/api/v1/health/ready" | python3 -m json.tool
ok "health ready"

bold "4. API — /search"
curl -sf "${API}/api/v1/search" \
  -H "content-type: application/json" \
  -d '{"query": {"text": "risarcimento per fatto illecito extracontrattuale", "corpora": ["codici"], "top_k_retrieve": 20, "top_k_rerank": 5}}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
hits = d['result']['hits']
print(f'  latency: {d[\"result\"][\"latency_ms\"]} ms, {len(hits)} hits')
for h in hits[:3]:
    c = h.get('citation')
    cite = c['display_hint'] if c and 'display_hint' in c else (c['num'] if c else '-')
    cite = (f'art. {c[\"num\"]}' + (f', c. {c[\"comma\"]}' if c and c.get('comma') else '')) if c else '-'
    print(f'    score={h[\"score_final\"]:.3f}  {cite}  «{h[\"text\"][:70]}…»')
"
ok "search restituisce hit"

bold "5. API — /chat (SSE streaming)"
echo '  domanda: "qual è la differenza tra dolo e colpa?"'
echo '  risposta: '
curl -Ns "${API}/api/v1/chat" \
  -H "content-type: application/json" \
  -d '{"question": "qual è la differenza tra dolo e colpa?", "corpora": ["codici"]}' \
  | python3 -c "
import sys, json
buf = ''
for line in sys.stdin:
    line = line.rstrip()
    if line.startswith('event:'):
        evt = line.split(':',1)[1].strip()
    elif line.startswith('data:'):
        data = line.split(':',1)[1].strip()
        if not data: continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if evt == 'retrieval':
            print(f'    [retrieval] {len(payload[\"hits\"])} hit, {payload[\"latency_ms\"]} ms')
            for h in payload['hits'][:3]:
                print(f'        - {h.get(\"citation_display\") or \"(?)\"}: «{h[\"excerpt\"][:60]}…»')
        elif evt == 'token':
            buf += payload['text']
            sys.stdout.write(payload['text'])
            sys.stdout.flush()
        elif evt == 'done':
            print(f'\n    [done] {payload[\"finish_reason\"]}')
        elif evt == 'error':
            print(f'\n    [error] {payload[\"message\"]}')
"
ok "chat streamata"

bold "Tutti i check passati."
