#!/usr/bin/env bash
# Dev-only traffic generator: hit a random Kelvin GET endpoint in a loop so the
# Grafana dashboards (Kelvin HTTP metrics) have something to show.
#
# Usage:
#   ./generate-traffic.sh            # loop forever, ~1 req/s
#   COUNT=50 ./generate-traffic.sh   # send 50 requests then stop
#   INTERVAL=0.2 ./generate-traffic.sh
#
# Config via env (with defaults):
#   KELVIN_URL  base URL                (http://127.0.0.1:8911)
#   USERNAME    login for a token       (Administrator)
#   PASSWORD    password                (univention)
#   SCHOOL      school (OU) for the classes/workgroups searches, which require it
#               (auto-discovered from /v1/schools/ if unset, else DEMOSCHOOL)
#   COUNT       number of requests, 0 = forever (0)
#   INTERVAL    seconds between requests (1)
set -uo pipefail

KELVIN_URL="${KELVIN_URL:-http://127.0.0.1:8911}"
USERNAME="${USERNAME:-Administrator}"
PASSWORD="${PASSWORD:-univention}"
SCHOOL="${SCHOOL:-}"
COUNT="${COUNT:-0}"
INTERVAL="${INTERVAL:-0.2}"
BASE="/ucsschool/kelvin"

# Try to obtain a bearer token so authed endpoints return 2xx instead of 401.
# Not fatal if it fails — requests still generate metrics (just with 401s).
TOKEN="$(curl -sk -X POST "$KELVIN_URL$BASE/token" \
  -d "username=$USERNAME&password=$PASSWORD" \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
if [[ -n "$TOKEN" ]]; then
  echo "Got access token; sending authenticated requests."
else
  echo "No token (login failed?) — sending unauthenticated requests (expect 401s)." >&2
fi

# The classes/workgroups searches require a ?school= param (else FastAPI returns 422).
# Discover a real school from the schools list; fall back to a placeholder.
if [[ -z "$SCHOOL" && -n "$TOKEN" ]]; then
  SCHOOL="$(curl -sk -H "Authorization: Bearer $TOKEN" "$KELVIN_URL$BASE/v1/schools/" \
    | sed -n 's/.*"name":"\([^"]*\)".*/\1/p' | head -n1)"
fi
SCHOOL="${SCHOOL:-DEMOSCHOOL}"
echo "Using school=$SCHOOL for classes/workgroups searches."

# GET endpoints to pick from. /health needs no auth; the list endpoints do.
# classes/workgroups carry the required school param; one bogus path yields 404s.
ENDPOINTS=(
  "/health"
  "$BASE/v1/schools/"
  "$BASE/v1/roles/"
  "$BASE/v1/classes/?school=$SCHOOL"
  "$BASE/v1/workgroups/?school=$SCHOOL"
  "$BASE/v1/users/?school=$SCHOOL"
  "$BASE/v2/schools/"
  "$BASE/v2/roles/"
  "$BASE/v2/classes/?school=$SCHOOL"
  "$BASE/v2/users/?school=$SCHOOL"
  "$BASE/v1/does-not-exist/"
)

i=0
while :; do
  path="${ENDPOINTS[$((RANDOM % ${#ENDPOINTS[@]}))]}"
  auth=()
  [[ -n "$TOKEN" && "$path" != "/health" ]] && auth=(-H "Authorization: Bearer $TOKEN")

  status="$(curl -sk -o /dev/null -w '%{http_code}' "${auth[@]}" "$KELVIN_URL$path")"
  printf '%s  %-40s -> %s\n' "$(date +%T)" "$path" "$status"

  i=$((i + 1))
  [[ "$COUNT" -ne 0 && "$i" -ge "$COUNT" ]] && break
  sleep "$INTERVAL"
done
