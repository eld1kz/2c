#!/usr/bin/env bash
# Checks a deployed instance from the outside: scripts/check_deploy.sh <domain> [<server-ip>]
# TLS + HTTPS redirect, security headers, sign-in, gateway, chain verify, and (with the IP) that only
# 80/443 answer. Reachability from mainland China is checked separately (README → Deploy).
set -uo pipefail

domain=${1:?usage: scripts/check_deploy.sh <domain> [<server-ip>]}
ip=${2:-}
base="https://$domain"
jar=$(mktemp)
trap 'rm -f "$jar"' EXIT
failed=0
check() { if eval "$2" >/dev/null 2>&1; then echo "ok    $1"; else echo "FAIL  $1"; failed=1; fi; }

headers=$(curl -sS -D - -o /dev/null "$base/login")
check "login page over valid TLS" "[[ \$(curl -sS -o /dev/null -w '%{http_code}' '$base/login') == 200 ]]"
check "http redirects to https" "[[ \$(curl -sS -o /dev/null -w '%{http_code}' 'http://$domain/login') == 308 ]]"
for h in strict-transport-security x-content-type-options x-frame-options content-security-policy; do
  check "header $h" "grep -qi '^$h:' <<<\"\$headers\""
done
check "demo sign-in" "curl -sS -f -c '$jar' -H 'Origin: $base' -H 'Content-Type: application/json' \
  -d '{\"email\":\"viewer@emberoak.demo\",\"password\":\"emberoak-demo\"}' '$base/api/auth/login'"
check "session cookie is Secure + HttpOnly" "grep -q '^#HttpOnly_$domain.*TRUE.*lw_session' '$jar'"
check "gateway reaches the API" "curl -sS -f -b '$jar' '$base/api/backend/position'"
check "audit chain verifies" "curl -sS -f -b '$jar' '$base/api/backend/audit/verify' | grep -q '\"ok\":true'"
check "cross-site sign-in refused" "[[ \$(curl -sS -o /dev/null -w '%{http_code}' -H 'Origin: https://evil.example' \
  -H 'Content-Type: application/json' -d '{}' '$base/api/auth/login') == 403 ]]"
if [[ -n "$ip" ]]; then
  for port in 3000 5432 8000; do
    check "port $port closed" "! curl -sS -m 5 -o /dev/null 'http://$ip:$port/'"
  done
fi
exit $failed
