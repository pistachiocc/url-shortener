#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "Checking API health..."
curl -fsS "$BASE_URL/health"
echo

echo "Creating a short URL..."
response=$(curl -fsS \
  -X POST "$BASE_URL/api/v1/urls" \
  -H "Content-Type: application/json" \
  -d '{"long_url":"https://example.com"}')

code=$(printf '%s' "$response" | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["code"])')

echo "Created short code: $code"

echo "Checking redirect..."
status=$(curl -sS \
  -o /dev/null \
  -w '%{http_code}' \
  "$BASE_URL/$code")

if [[ "$status" != "302" ]]; then
  echo "Expected 302, got $status"
  exit 1
fi 

echo "Checking Redis cache..."
cached=$(docker compose exec -T cache \
  redis-cli EXISTS "url:$code" | tr -d '\r')

if [[ "$cached" != "1" ]]; then
  echo "Redis cache entry not found"
  exit 1
fi

echo "Smoke test passed!"
