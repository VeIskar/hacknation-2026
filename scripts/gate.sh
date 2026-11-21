#!/usr/bin/env bash
# Bramka. web: lint z autofixem + tsc + vitest. api: ruff z autofixem + pytest.
# Uzycie: bash scripts/gate.sh             twoj obszar z pliku .hn-area, bez pliku calosc
#         bash scripts/gate.sh all         calosc, niezaleznie od .hn-area
#         bash scripts/gate.sh web [args]  tylko front, args ida do vitest
#         bash scripts/gate.sh api [args]  tylko backend, args ida do pytest
# Nazwy katalogow frontend/ i backend/ sa stale. Brak obu to FAIL, nie cichy PASS.
# .hn-area (poza gitem, tresc: web albo api) sprawia, ze czerwony cudzy obszar nie
# blokuje pracy w swoim. Calosc sprawdza osoba, ktora integruje.
set -euo pipefail
cd "$(dirname "$0")/.."
area=all
if [ -f .hn-area ]; then
  area=$(tr -d '[:space:]' < .hn-area)
  case "$area" in
    web|api) ;;
    *) echo "GATE: FAIL (.hn-area ma zawierac web albo api, jest: '$area')"; exit 1 ;;
  esac
fi
part="${1:-$area}"
[ $# -gt 0 ] && shift

has_web() { [ -f frontend/package.json ]; }
has_api() { [ -d backend ]; }

# Pusty zestaw testow jest dozwolony tylko bez argumentow (swiezy szablon). Gdy ktos podal
# filtr, a zaden test sie nie uruchomil, to FAIL: literowka w filtrze nie moze dac PASS.
web() {
  ( cd frontend
    npm run lint --silent -- --fix
    npx tsc -b
    if [ $# -eq 0 ]; then
      npx vitest run --dir src --passWithNoTests
    else
      npx vitest run --dir src "$@"
    fi )
}

api() {
  if [ ! -x backend/.venv/bin/python ]; then
    echo "GATE api: brak backend/.venv (uruchom 'setup' z AGENTS.md)"
    return 1
  fi
  ( cd backend
    .venv/bin/python -m ruff check --fix --quiet .
    # kod 5 = pytest nie uruchomil zadnego testu
    rc=0
    .venv/bin/python -m pytest -q "$@" || rc=$?
    if [ "$rc" -eq 5 ] && [ $# -eq 0 ]; then rc=0; fi
    exit "$rc" )
}

case "$part" in
  web) web "$@" ;;
  api) api "$@" ;;
  all)
    if ! has_web && ! has_api; then
      echo "GATE: FAIL (nie ma ani frontend/package.json, ani backend/)"
      exit 1
    fi
    if has_web; then web; else echo "GATE web: pominiete, brak frontend/"; fi
    if has_api; then api; else echo "GATE api: pominiete, brak backend/"; fi
    ;;
  *) echo "uzycie: gate.sh [all|web|api] [args]"; exit 2 ;;
esac
echo "GATE: PASS ($part)"
