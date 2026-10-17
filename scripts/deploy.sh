#!/usr/bin/env bash
# Deploy the committed HEAD to the server and (re)start the production stack.
# Usage: scripts/deploy.sh root@<server> [--seed]
#   --seed   first deploy only: load the golden data, then reset it to the deterministic golden state
# Needs deploy/.env on the server (template: deploy/env.production.example) and deploy/bootstrap.sh run once.
set -euo pipefail

target=${1:?usage: scripts/deploy.sh root@<server> [--seed]}
seed=${2:-}
ROOT=$(git rev-parse --show-toplevel)
DIR=/opt/ledgerwise
COMPOSE="docker compose -f $DIR/deploy/docker-compose.prod.yml"
fail() { echo "DEPLOY STOPPED: $1" >&2; exit 1; }

[[ -z $(git -C "$ROOT" status --porcelain) ]] || fail "uncommitted changes: deploy a commit (scripts/ship.sh first)"
ssh "$target" "test -s $DIR/deploy/.env" || fail "$DIR/deploy/.env missing on the server"

# Only tracked files reach the server (git archive), so .env files, .venv and node_modules never do.
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
git -C "$ROOT" archive HEAD | tar -x -C "$STAGE"
rsync -az --delete --exclude deploy/.env "$STAGE/" "$target:$DIR/"

ssh "$target" bash -s <<REMOTE
set -euo pipefail
chmod 600 $DIR/deploy/.env
$COMPOSE build --pull
$COMPOSE up -d db
$COMPOSE run --rm backend alembic upgrade head
if [[ "$seed" == "--seed" ]]; then
  $COMPOSE run --rm backend python -m seed.load
  $COMPOSE run --rm backend python -m seed.reset
fi
$COMPOSE up -d --remove-orphans
install -m 644 $DIR/deploy/cron/ledgerwise /etc/cron.d/ledgerwise
$COMPOSE ps
REMOTE
echo "deployed $(git -C "$ROOT" rev-parse --short HEAD) to $target"
