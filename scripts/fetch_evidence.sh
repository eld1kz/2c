#!/usr/bin/env bash
# Export execution evidence from the deployed database into evidence/ and verify it:
#   scripts/fetch_evidence.sh root@<server>
# Run it right after a demo run, before the next scheduled reset clears the sandbox rows. Then commit
# evidence/ (scripts/ship.sh) so the anchored audit head lives outside the database.
set -euo pipefail

target=${1:?usage: scripts/fetch_evidence.sh root@<server>}
ROOT=$(git rev-parse --show-toplevel)
COMPOSE="docker compose -f /opt/ledgerwise/deploy/docker-compose.prod.yml"

ssh "$target" "set -e; $COMPOSE exec -T backend sh -c 'rm -rf /tmp/evidence && python -m app.sandbox.evidence_export --out-dir /tmp/evidence' \
  && rm -rf /tmp/evidence && $COMPOSE cp backend:/tmp/evidence /tmp/evidence \
  && $COMPOSE exec -T backend python -m app.sandbox.evidence_export --verify-anchor /tmp/evidence/anchor.json"
mkdir -p "$ROOT/evidence"
scp -q "$target:/tmp/evidence/*" "$ROOT/evidence/"
name=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['export_file'])" "$ROOT/evidence/anchor.json")
cd "$ROOT/backend"
.venv/bin/python -m app.sandbox.evidence_export --check-file "../evidence/$name" --anchor ../evidence/anchor.json
echo "evidence/$name + evidence/anchor.json ready to commit"
