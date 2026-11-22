# Cyfryzacja formularzy

Aplikacja zamienia plik papierowego wniosku (PDF, DOC, DOCX, ODS, XLSX, JPG, JPEG, PNG) w JSON
konfiguracji eUsługi w formacie COI. Jest dla urzędnika gminy, który cyfryzuje formularze bez programowania.

Przepływ w `POST /api/forms` (`backend/app/main.py`):

```
validate_upload → extract → analyze → quality.ground → build_form → lint.check → JSON COI
kontrola pliku    tekst/OCR   model AI   strażnik         generator    linter
```

API przetwarza plik tylko w pamięci (Treść pkt 5: bez trwałego zapisu). Zastrzeżenie dotyczące bufora nginx opisuje [Znane ograniczenia](docs/ARCHITEKTURA.md#znane-ograniczenia).
Model zwraca opis formularza
(`FormAnalysis`). Strażnik (`quality.ground`) porównuje go z tekstem dokumentu: poprawia dane
wnioskodawcy i usuwa powtórzone pola. Przy `LLM_FIXTURE` jest pominięty. Generator buduje JSON COI,
a linter sprawdza schemat i Reguły techniczne.

[Dokumentacja architektury](docs/ARCHITEKTURA.md)

## Wymagania

- Maszyna x86, bez GPU (obrona odbywa się bez karty graficznej).
- Docker z Compose v2 albo Podman z `podman-compose`. Komendy niżej używają `docker compose`.
- Miejsce na dysku: obraz `api` ok. 0,3 GB, obraz `ollama` ok. 5 GB, model `qwen3.5:4b` 3,3 GB.
- Praca bez kontenerów: Python 3.14 i Node 22 na Linuksie, macOS albo WSL.

## Obrazy

| Serwis | Obraz | Użytkownik | Port na hoście | Uwagi |
|---|---|---|---|---|
| `api` | `backend/Dockerfile`, baza `python:3.14.10-slim-trixie` | `app` (UID 10001) | 8000 | Tesseract 5 z językiem `pol` do OCR skanów. System plików tylko do odczytu, `/tmp` w pamięci, `cap_drop: ALL`, `no-new-privileges` |
| `ollama` | `ollama/Dockerfile`, baza `ollama/ollama:0.40.15` | `ollama` (UID 10002) | brak | Lokalny serwer modelu. Model w wolumenie `ollama-models`. Usługi chmurowe Ollamy wyłączone (`OLLAMA_NO_CLOUD=1`) |
| `web` | `frontend/Dockerfile` (`node:22-slim`, potem `nginx:1.27-alpine`) | jak w obrazie nginx | 5173 | Front i proxy `/api/` do `api` |

Compose ma stałą nazwę projektu `hacknation-2026`. Wolumen z modelem jest więc wspólny dla każdego
katalogu (klon, worktree), a model nie pobiera się drugi raz.

Podczas Hackathonu **Docker Hub bez logowania** często zwraca `toomanyrequests`. Te same obrazy są w lustrze
`mirror.gcr.io`. Pobierz je stamtąd i nadaj nazwę z Dockerfile:

```bash
podman pull mirror.gcr.io/library/python:3.14.10-slim-trixie
podman tag  mirror.gcr.io/library/python:3.14.10-slim-trixie docker.io/library/python:3.14.10-slim-trixie
podman pull mirror.gcr.io/ollama/ollama:0.40.15
podman tag  mirror.gcr.io/ollama/ollama:0.40.15 docker.io/ollama/ollama:0.40.15
```

## Uruchomienie

```bash
cp env.example .env                 # ustawienia; .env nigdy nie trafia do repozytorium
bash scripts/pull_model.sh          # raz: pobiera model LLM_MODEL do wolumenu (ok. 3,3 GB)
docker compose up -d --build        # api :8000, web :5173, ollama w sieci compose
docker compose ps                   # api i ollama „healthy”
curl http://127.0.0.1:8000/health   # {"status":"ok"}
```

Aplikacja: http://127.0.0.1:5173. API: http://127.0.0.1:8000, opis OpenAPI: http://127.0.0.1:8000/docs.

- Z Podmanem bez roota używaj `127.0.0.1`, nie `localhost`. Przekierowanie portów nie obsługuje `::1`.
- API czyta `.env` raz, przy starcie. Po zmianie `.env` wykonaj `docker compose up -d api`.
- Po zmianie gałęzi albo `git pull` zbuduj obrazy od nowa: `docker compose up -d --build`. Bez
  `--build` kontener działa na starym kodzie.
- Zatrzymanie: `docker compose down`. **Bez `-v`**, bo `-v` usuwa wolumen z modelem.

### Model lokalny (domyślnie)

Domyślnie `api` woła lokalną Ollamę (`http://ollama:11434/v1`, model `qwen3.5:4b`). Na samym CPU
sam model w pomiarze K1 potrzebował 238–344 s na formularz. Tryb lokalny przekracza więc granicę
200 s na cały proces z D11 (cel to ok. 180 s). Do pomiarów lokalnych można zwiększyć `LLM_TIMEOUT_S`.

### Model w chmurze: Eden AI (D9)

`LLM_PROVIDER=edenai` włącza Eden AI organizatorów. D9 dopuszcza tylko modele otwarte, które można
uruchomić na własnej infrastrukturze. Zalecana trasa to `flexai/Qwen3.5-9B@eu`. W pomiarze E1
wyłączenie myślenia zadziałało na tej trasie. `ovhcloud/Qwen3.5-9B` zignorowała je i wyczerpała
limit 8192 tokenów, zwracając pustą treść lub ucięty JSON. Trasę zatwierdza lider (D9 pkt 8).
**W trybie Eden AI do dostawcy trafia tekst odczytany z pliku.** Skany i obsługiwane obrazy odczytuje lokalnie OCR Tesseract. Model otrzymuje tekst.

API nie wystartuje przy `edenai`, jeśli:

- `LLM_BASE_URL` nie wskazuje `https://api.edenai.run` ani `https://api.eu.edenai.run`
  (pusty daje `https://api.eu.edenai.run/v3`).
- brakuje klucza Eden AI w `LLM_API_KEY`. Wartość `ollama` z `env.example` jest tylko dla Ollamy.
- `LLM_MODEL` nie jest na liście modeli otwartych z `DECISIONS.md` (M1.7). Dziś to trasy Qwen3.5-9B.

Komunikat błędu podaje nazwę zmiennej, bez jej wartości. Adres Eden AI przy `LLM_PROVIDER=ollama`
też zatrzymuje start, żeby nie ominąć listy modeli.

Na macOS uruchom w Bashu lub zsh z kluczem Eden AI zapisanym w Pęku kluczy jako `hacknation-edenai`
dla konta `$USER`. Klucz API trafia do środowiska uruchomienia. Nie zapisuj go w `.env` ani w repozytorium.

```bash
(
  export LLM_PROVIDER=edenai
  export LLM_BASE_URL=https://api.eu.edenai.run/v3
  export LLM_MODEL=flexai/Qwen3.5-9B@eu
  export LLM_CONTEXT_TOKENS=65536
  export LLM_MAX_TOKENS=16384
  export LLM_REASONING_EFFORT=off
  export LLM_EXTRA_BODY='{"chat_template_kwargs":{"enable_thinking":false}}'
  export LLM_FIXTURE=
  LLM_API_KEY="$(security find-generic-password -a "$USER" -s hacknation-edenai -w)" || exit 1
  export LLM_API_KEY

  docker compose up -d --build api web
)
```

Żeby wygenerować pliki COI z tymi ustawieniami, wstaw w powyższym bloku zamiast polecenia Compose:

```bash
backend/.venv/bin/python scripts/generate_forms.py --out ../generated-forms-eden
```

- Jeśli trasa odrzuci `reasoning_effort` lub `temperature`, ustaw odpowiednio
  `LLM_REASONING_EFFORT=off` lub `LLM_TEMPERATURE=off`.
- Jeśli trasa odrzuci `strict: true`, ustaw `LLM_STRICT_SCHEMA=false`.
- Jeśli model zwraca tok rozumowania, wypróbuj
  `LLM_EXTRA_BODY='{"chat_template_kwargs":{"enable_thinking":false}}'`.

Przy prawdziwym uruchomieniu `LLM_FIXTURE` musi być pusty. Ustawiony zastępuje model plikiem, więc
każdy dokument dostaje tę samą analizę. Służy tylko testom.

## Konfiguracja

Zmienne z `env.example`. Compose przekazuje je do `api`, a pusta wartość daje wartość domyślną.

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `MAX_FILE_SIZE_MB` | `10` | Limit pliku w MB. Większy plik daje 413. Liczba całkowita > 0, inaczej API nie startuje |
| `JWT_ENABLED` | `false` | `true`: `POST /api/forms` wymaga tokenu JWT. `/health` i `/api/info` są otwarte |
| `JWT_SECRET` | – | Sekret JWT, co najmniej 32/48/64 bajty dla HS256/HS384/HS512 |
| `JWT_ALGORITHM` | `HS256` | `HS256`, `HS384` albo `HS512` |
| `LLM_PROVIDER` | `ollama` | `ollama` albo `edenai` (D9). Inna wartość zatrzymuje start |
| `LLM_BASE_URL` | Ollama w Compose `http://ollama:11434/v1`, lokalnie `http://localhost:11434/v1`. Eden AI `https://api.eu.edenai.run/v3` | Serwer modelu zgodny z OpenAI. Pusta wartość wybiera adres dostawcy. Przy `edenai` tylko host Eden AI |
| `LLM_OLLAMA_URL` | compose: `http://ollama:11434/v1` | Adres Ollamy dla pustego `LLM_BASE_URL`. Ustawia go compose; nie ma go w `env.example` |
| `LLM_MODEL` | Ollama `qwen3.5:4b`, Eden AI `flexai/Qwen3.5-9B@eu` | Nazwa modelu na serwerze. Przy `edenai` tylko model otwarty z listy w `DECISIONS.md` |
| `LLM_API_KEY` | `ollama`; Eden AI: brak | Klucz API. Ollama go nie sprawdza. Przy `edenai` wymagany; podawaj go w powłoce, nie w `.env` |
| `LLM_TIMEOUT_S` | `120` | Timeout dla pojedynczego zapytania w sekundach. Przekroczenie daje 503 |
| `LLM_CONNECT_TIMEOUT_S` | `10` | Limit na nawiązanie połączenia z modelem w sekundach |
| `LLM_CONTEXT_TOKENS` | Ollama `32768`, Eden AI `65536` | Kontekst analizy w tokenach, min. `8192`. Compose podaje tę samą liczbę Ollamie |
| `LLM_MAX_TOKENS` | Ollama `4096`, Eden AI `16384` | Limit tokenów odpowiedzi uwzględniany w budżecie kontekstu |
| `LLM_TEMPERATURE` | `0` | Temperatura od 0 do 2. Przy ponowieniu co najmniej 0,3. `off` pomija parametr także przy ponowieniu |
| `LLM_REASONING_EFFORT` | Ollama `none`, Eden AI `off` | Ustawienie toku rozumowania. `off` pomija parametr |
| `LLM_STRICT_SCHEMA` | `true` | Wartość `strict` w żądaniu schematu JSON. Dopuszczalne `true` i `false` |
| `LLM_EXTRA_BODY` | Ollama pusty, Eden AI `{"chat_template_kwargs":{"enable_thinking":false}}` | Dodatkowe parametry żądania. Pole `LLM_EXTRA_BODY={}` zastępuje domyślny obiekt pustym. Ustawienia klienta, w tym model, wiadomości i format odpowiedzi, mają pierwszeństwo |
| `LLM_ANALYSIS_BUDGET_S` | `170` | Budżet czasu prób w sekundach. Gdy suma czasów prób i 110% czasu ostatniej przekracza budżet, analiza próbuje naprawy ostatniej szansy zamiast ponowienia |
| `LLM_MAX_ATTEMPTS` | `2` | Łączna liczba prób analizy, od 1 do 3 |
| `LLM_FIXTURE` | pusty | Ścieżka do pliku `FormAnalysis`. Gdy ustawiona, model nie jest wołany (testy) |
| `OCR_LANG` | `pol` | Język Tesseract dla skanów |
| `ADD_VALIDATORS` | `true` | Walidatory (PESEL, NIP, REGON, ZIP_CODE, EMAIL) w JSON-ie. **Obecnie bez skutku**: generator używa stałej `app.generator.form.ADD_VALIDATORS` |

Serwis `ollama` dostaje `OLLAMA_CONTEXT_LENGTH` z `LLM_CONTEXT_TOKENS`, więc serwer i analiza znają
ten sam kontekst. Ma też `OLLAMA_KEEP_ALIVE` (domyślnie `24h`: model zostaje w pamięci). Kontekst
32768 kosztuje `qwen3.5:4b` ok. 4,2 GB pamięci (16384: 3,7 GB).

## REST API

### `GET /health`

```bash
curl http://127.0.0.1:8000/health
# 200 {"status":"ok"}
```

### `GET /api/info`

Zwraca skonfigurowanego dostawcę i model. Token JWT jest zbędny.

```bash
curl http://127.0.0.1:8000/api/info
# 200 {"llm":"ollama","model":"qwen3.5:4b"}
```

### `POST /api/forms`

`multipart/form-data`, jedno pole `file`. Odpowiedź 200 to sam JSON formularza COI, bez opakowania.

```bash
curl -s -o formularz.json -w 'HTTP %{http_code}, %{time_total} s\n' \
     -F "file=@Wniosek o wydanie zaświadczenia.pdf" http://127.0.0.1:8000/api/forms
```

Z `JWT_ENABLED=true` dodaj nagłówek `Authorization: Bearer <JWT_TOKEN>`:

```bash
TOKEN=$(docker compose exec -T api python -m app.auth token --hours 24)
curl -s -H "Authorization: Bearer $TOKEN" -F "file=@wniosek.pdf" http://127.0.0.1:8000/api/forms
```

Bez kontenerów token daje `cd backend && JWT_SECRET=<sekret> .venv/bin/python -m app.auth token`.

Kody błędów (`SPEC.md`, „API contract”). Ciało jest zawsze `{"detail": "<tekst>"}`. API nie zwraca 422.

| Kod | `detail` | Kiedy |
|---|---|---|
| 400 | `Wybierz plik formularza.` | brak pola `file`, pusta część pliku albo żądanie nie jest multipart |
| 400 | `Nazwa pliku jest za długa albo ma niedozwolone znaki.` | nazwa ponad 250 znaków albo z jednym ze znaków ``; : > < / \ \| ' * % $`` |
| 400 | `Nie udało się odczytać treści pliku.` | w pliku nie ma tekstu do odczytu, np. PDF bez warstwy tekstowej |
| 401 | `Brak tokenu dostępu albo token jest nieważny.` | `JWT_ENABLED=true`, a tokenu brak albo jest zły lub wygasł. Sprawdzany przed plikiem |
| 413 | `Plik jest za duży. Limit to 10 MB.` | plik ponad `MAX_FILE_SIZE_MB` (liczba w tekście pochodzi z ustawień) |
| 415 | `Zawartość pliku nie pasuje do rozszerzenia .pdf.` | treść nie pasuje do rozszerzenia (w tekście rozszerzenie pliku) |
| 415 | `Ten typ pliku nie jest obsługiwany. Wybierz PDF, DOC, DOCX, ODS, XLSX, JPG albo PNG.` | inne rozszerzenie |
| 503 | `Model AI nie odpowiada. Spróbuj ponownie za chwilę.` | model nie odpowiada, przekroczył limit czasu albo po 2 próbach nie dał poprawnej analizy |
| 500 | `Coś poszło nie tak. Spróbuj ponownie.` | nieoczekiwany błąd; szczegóły w `docker compose logs api` |

Stan obecny:
- `.doc`, `.xlsx` i `.ods` przechodzą kontrolę pliku, ale dają 400 „Nie udało się odczytać treści
  pliku.”, dopóki odczyt (K2) nie obsłuży tych formatów. Działają PDF, DOCX, JPG, JPEG i PNG.
- `.doc`, który w środku jest DOCX, jest czytany jak DOCX. `.jpe` jest traktowany jak `.jpg`.
- JSON odrzucony przez linter daje 500 z błędami w logu. To rozwiązanie tymczasowe, czeka na decyzję.

## JSON-y formularzy do oddania

`scripts/generate_forms.py` tworzy JSON-y COI dla folderów 2–4 i 6–9 z `materialy/` oraz raport
jakości. Ustawienia modelu bierze ze środowiska, tak jak API (zmienne `LLM_*`).

```bash
set -a; . ./.env; set +a
backend/.venv/bin/python scripts/generate_forms.py --out ../generated-forms
```

| Opcja | Domyślnie | Znaczenie |
|---|---|---|
| `--forms 3,8` | 2, 3, 4, 6, 7, 8, 9 | wybrane foldery; folder 1 (zbiór kontrolny) jest zawsze wykluczony |
| `--include-5` | wyłączone | dopuszcza folder 5 (wzorzec) |
| `--prefer pdf,docx` | `pdf,docx,doc,jpg,png` | kolejność formatów przy wyborze pliku z folderu |
| `--out <katalog>` | `../generated-forms` | katalog wyników, poza repozytorium |

Wynik: `F<numer>.coi.json`, `F<numer>.analysis.json`, `report.json` i `report.md`. Kod wyjścia 1
oznacza, że któryś formularz się nie udał.

## Praca lokalna, bez kontenerów

```bash
(cd frontend && npm ci && npx playwright install chromium)
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
bash scripts/gate.sh                # lint i testy; bez .hn-area obie strony
(cd frontend && npm run test:e2e)   # Playwright i axe; uruchamia web i api
```

API lokalnie: `cd backend && .venv/bin/uvicorn app.main:app --port 8000`. Testy nie wołają modelu,
tylko czytają `backend/tests/fixtures/fields.json` przez `LLM_FIXTURE`.

## Praca w zespole

Jedno repozytorium, każda osoba we własnym klonie.

Wymagania: Linux, macOS albo Windows z WSL. Skrypty w `scripts/` i ścieżka
`backend/.venv/bin` nie działają w natywnym Windows. Sprawdzone na Node 22 i Pythonie 3.14.
Do pełnego startu potrzebny jest Docker.

1. Sklonuj repozytorium i wykonaj komendy z „Praca lokalna, bez kontenerów” powyżej.
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

Stan wdrożenia opisuje sekcja [Znane ograniczenia](docs/ARCHITEKTURA.md#znane-ograniczenia).

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
