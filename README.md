# (nazwa projektu)

(jedno zdanie: co to robi i dla kogo)

## Uruchomienie

```bash
docker compose up --build
```

Aplikacja: http://localhost:5173. API: http://localhost:8000/health.

Praca lokalna, bez kontenerów:

```bash
(cd frontend && npm ci && npx playwright install chromium)
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
bash scripts/gate.sh
(cd frontend && npm run test:e2e)
```

## Praca w zespole

Jedno repozytorium, każda osoba we własnym klonie.

Wymagania: Linux, macOS albo Windows z WSL. Skrypty w `scripts/` i ścieżka
`backend/.venv/bin` nie działają w natywnym Windows. Sprawdzone na Node 22 i Pythonie 3.12.
Do pełnego startu potrzebny jest Docker.

1. Sklonuj repozytorium i wykonaj komendy z „Praca lokalna" powyżej.
2. Wskaż swój obszar. Plik nie trafia do repozytorium.
   - front: `echo web > .hn-area`
   - backend: `echo api > .hn-area`
   - osoba, która integruje całość: bez pliku.
3. Pracujesz w swoim katalogu (`frontend/` albo `backend/`). Bramka sprawdza wtedy tylko
   Twoją stronę, więc cudzy czerwony kod Cię nie blokuje.
4. Wspólną umową jest `SPEC.md`, sekcje „API contract" i „Field contract". Zmienia je osoba
   integrująca, po uzgodnieniu z zespołem. Front buduje na przykładach z kontraktu, zanim
   backend je zaimplementuje.
5. Potrzebujesz zmiany poza swoim obszarem: dopisz jedną linię w „Requests" w swoim pliku
   `PROGRESS.web.md` albo `PROGRESS.api.md` i powiedz właścicielowi.
6. Commity robi człowiek, małe i często. Przed wysłaniem zmian kolejno: `git pull --rebase`,
   `bash scripts/gate.sh`, `git push`.

Komendy etapów w Claude Code: `/hn-krok` (jeden krok), `/hn-napraw` (jeden błąd),
`/hn-recenzja` (druga opinia Codexa), `/hn-stan` (zapis stanu). `/hn-spec` i `/hn-demo`
uruchamia osoba integrująca. Inny agent (Codex, Cursor, Copilot) czyta `AGENTS.md` i pliki
`.claude/skills/hn-*/SKILL.md`. Bez agenta wystarczy `bash scripts/gate.sh`.

## Co jest prawdziwe, a co jest atrapą

(wypełnia `/hn-demo`)

## Ograniczenia

(wypełnia `/hn-demo`)

## Licencje zależności

Lista z uzasadnieniem jest w `DECISIONS.md`.

## Narzędzia przygotowane przed wydarzeniem

Przed startem wydarzenia powstał wyłącznie szablon i narzędzia pracy. Nie zawierają kodu
rozwiązującego zadanie.

- Szkielet aplikacji: pusty front (Vite, React, TypeScript, Tailwind) z jedną stroną
  zastępczą, API FastAPI z jednym adresem `/health`, `docker-compose.yml` i dwa pliki
  Dockerfile.
- Reguły dla agentów: `AGENTS.md`, `CLAUDE.md`, `DESIGN.md`, puste szablony `SPEC.md`,
  `PROGRESS.md`, `PROGRESS.web.md`, `PROGRESS.api.md`, `DECISIONS.md`, `PITCH.md`.
- Uprawnienia i hook: `.claude/settings.json`.
- Bramka jakości: `scripts/gate.sh`, `scripts/stop-gate.sh`.
- Testy narzędziowe: `frontend/tests/e2e/a11y.spec.ts` (axe i klawiatura),
  `frontend/tests/e2e/shots.spec.ts` (zrzuty ekranów).
- Role agentów: `.claude/agents/` (reviewer, a11y, pitch).
- Procedury etapów: `.claude/skills/hn-*`.

## Zatrzask na testy

Po akceptacji `SPEC.md` i testu akceptacyjnego człowiek zapina zatrzask:

```bash
echo '{ "permissions": { "deny": ["Edit(frontend/tests/e2e/*.spec.ts)"] } }' > .claude/settings.local.json
```

Odpina się go usunięciem pliku `.claude/settings.local.json`.

## Wyłącznik bramki

`touch /tmp/gate.off` wyłącza bramkę po każdej turze, `rm /tmp/gate.off` włącza.
