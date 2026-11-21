# PROGRESS (area: api, directory backend/)

## State

(rewritten by /hn-stan before sleep, at a usage limit, before switching agents)

## Plan

Krok P0.1: poprawki po recenzji P0 (decyzje lidera D1-D6 w `DECISIONS.md`).

- `backend/app/errors.py`: argumenty tylko nazwane, kontrola typu i kodu; bez 422.
- `backend/app/models.py`: zamknięty `source_format`, `images` poza JSON-em i z limitem,
  walidacja `FormAnalysis` (puste teksty, opcje, `show_if`, nieznane klucze), przykłady bez folderu 1.
- `backend/tests/`: `test_errors.py`, `test_models.py`, `conftest.py` (wzorce COI z `materialy/`).
- Usunięte z gita: `fixtures/expected_nadplata.json`, `fixtures/expected_numer_porzadkowy.json`.
- Dokumenty: `DECISIONS.md`, `SPEC.md` (API contract), `DELEGACJA.md` (rozdz. 1–3, 6–8), `docs/ZESTAW_TESTOWY.md` (uwaga w pkt 2).
- Dowód: `bash scripts/gate.sh api` oraz każdy nowy test widziany na czerwono po zepsuciu kodu.

Krok M1.1 (Marcin): `config.py` (env z DELEGACJA rozdz. 5), `files.py` (nazwa, rozmiar, typ, sygnatura;
multipart tylko w pamięci), `POST /api/forms` zwraca stały szkielet; `AppError` → kod, walidacja → 400,
inny wyjątek → 500. Testy: `test_files.py`, `test_api.py`, `samples.py`.

Krok P1: generator `build_form(FormAnalysis) -> dict` (SZABLONY_SEKCJI.md + dopowiedzenia lidera).

- `backend/app/generator/coi.py`: slug, unikalne techName, HTML z escapowaniem, literały jsonaty, pole/sekcja/strona z układem y/rows/questionOrder.
- `backend/app/generator/template.py`: „Dane” (warianty PERSON, ENTITY, BOTH), „Kontakt i zgody” (zgoda + oświadczenia), „Strona końcowa”.
- `backend/app/generator/form.py`: strony przedmiotu (tytuły bez kolizji, show_if po etykiecie), UUID5, flow, `ADD_VALIDATORS`.
- `backend/tests/test_generator.py` + fixtures `analysis_person.json`, `analysis_entity.json`, `analysis_edge_cases.json`.
- Dowód: techName i jsonata zgodne z `coi_working_reference`, format rozdz. 0, determinizm; `bash scripts/gate.sh api -rs` bez pominięć.

Krok M1.1-fix (Marcin, CHANGES REQUIRED od Pawła, gałąź `marcin/m1.1-fix`): `docker-compose.yml` przekazuje
do api wszystkie zmienne z `env.example` (`${NAZWA:-}`); `config.py` odrzuca `MAX_FILE_SIZE_MB` ≤ 0 lub
niecałkowite i `LLM_TIMEOUT_S` ≤ 0, API nie startuje; `files.py`: `mimetype` ODS dokładnie równy, błędy
metadanych ZIP → 415, `Content-Type` bez względu na wielkość liter. Testy: `test_config.py` (nowy),
`test_files.py`, `test_api.py` (też limit strumieniowy bez Content-Length, przez ASGI).

Krok P2: `lint.check(form)` dla M1.4 i E1 (schemat COI, Reguły techniczne, JSONata).

- `backend/tests/test_lint.py`: oba wzorce, wszystkie fixture’y generatora, warianty, uszkodzenia i odporność. Najpierw czerwony wynik.
- `backend/app/lint.py`: typy, układ, komponenty, stany, unikalność, przepływ w obie strony i odwołania JSONata. Tylko biblioteka standardowa.
- `DECISIONS.md`: jeden wpis z tolerancjami COI i rozstrzygnięciami z Fazy 0.
- Dowód: testy i mutacje dla każdej reguły, przegląd diffu, `bash scripts/gate.sh api -rs`, 0 pominiętych.

Krok M1.2 (Marcin): JWT według „API contract” (401, `Authorization: Bearer`, `/health` otwarte).
- `backend/app/auth.py`: zależność `require_token` (HS256/384/512, wymagany `exp`), `AuthError` 401,
  skrypt `python -m app.auth token [--hours N]`; brak `JWT_SECRET` przy włączonym JWT → 500.
- `backend/app/main.py`: `require_token` na `POST /api/forms` przed odczytem pliku, 401 z `WWW-Authenticate`.
- `backend/requirements.txt` + `DECISIONS.md`: PyJWT 2.15.1 (MIT).
- Dowód: `test_auth.py` (brak/zły/wygasły/obcy token, zły schemat, `/health`, JWT wyłączony, skrypt).

Krok P1.2a: wymagany kontrakt MVP `FormAnalysis.applicant` i jawne `applicants`.

- `backend/app/models.py`: decyzje z papieru, walidacja spójności, wspólne `show_if` i naprawa Unicode.
- `backend/tests/fixtures/*.json`: migracja czterech analiz i dodanie analizy F3.
- `backend/tests/test_models.py`: schemat, reguły, Unicode, każdy fixture przez generator i linter.
- `DECISIONS.md` i „Requests”: decyzja MVP oraz treści do zgłoszenia liderowi.
- Dowód: czerwone nowe testy, mutacje reguł i Unicode, `bash scripts/gate.sh api -rs` bez pominięć, przegląd nazw plików.

Krok K1 (Mikołaj, gałąź `mikolaj/k1`): pomiar `qwen3.5:4b` w lokalnej Ollamie (Docker 0.40.15, CPU).

- `backend/app/llm.py`: klient `/v1/chat/completions` (httpx) z ustawieniami z `config.Settings`; `reasoning_effort: "none"`, `response_format` ze schematem `FormAnalysis`; sieć, timeout, zła odpowiedź → `LLMUnavailable`.
- `scripts/bench_model.py`: DOCX albo JPG z folderu 5 → czas, tokeny, JSON, `FormAnalysis.model_validate`, zgodność pól z `fields.json`. Folder 1 odrzucony. Surowe odpowiedzi tylko w `materialy/` albo poza repo.
- Testy offline (atrapa transportu, bez modelu): `backend/tests/test_llm.py`, `backend/tests/test_bench_model.py`.
- Dokumenty: wynik pomiaru i httpx w runtime w `DECISIONS.md` (api); log tutaj. Bielik tylko opcjonalnie.
- Dowód: `bash scripts/gate.sh api -rs`, każdy nowy test widziany na czerwono.

Krok K1-fix2 (zakres zatwierdzony przez lidera 2026-11-21, także `scripts/bench_model.py`): uwagi Codexa #1 i #2.

- `backend/app/llm.py` i `ollama_version` w `scripts/bench_model.py`: `httpx.Client(trust_env=False)`, model zawsze bez proxy z env.
- `scripts/bench_model.py`: `check_input` odrzuca też plik o tej samej treści (sha256) co plik z folderu 1, w dowolnym miejscu.
- Testy bez sieci: proxy z env, host `ollama`, podmienione tylko wysyłanie w `httpx.HTTPTransport` (httpx pomija proxy z env przy własnym transporcie, więc atrapa nie wystarczy); kopia pliku kontrolnego w `tmp_path`, także przez `main`, bez materiałów COI.
- Wymaganie przed kolejnym pomiarem jakości pól (lider, uwaga Codexa #3): `field_quality` ma dawać wynik niezależny od kolejności etykiet. Najpierw dokładne etykiety, potem przydział 1:1 wśród reszty, z testem na zamienioną kolejność wzorców.
- Wymaganie przed kolejnym pomiarem (kontrakt P1.2a): prompt w `bench_model.py` każe pominąć dane wnioskodawcy i kontakt, a `FormAnalysis` wymaga teraz decyzji `applicant` i `applicant_extra_fields`. Pomiar ma też oceniać te decyzje, nie tylko pola przedmiotu.
- Dowód: `bash scripts/gate.sh api -rs`, każdy nowy test widziany na czerwono.

Krok P1.2b: dobór sekcji z `FormAnalysis.applicant` i warunki SHOW.

- `backend/tests/test_generator.py`: najpierw regresje F2–F4 i F6–F9, pełna macierz z P2 i dokładny wzorzec 5.
- `backend/app/generator/`: dobór ścieżek i sekcji, korespondencja, pola dodatkowe oraz kontakt.
- `DECISIONS.md`: zastąpienie GD2 i uzasadnienie wyjątku D5.
- Dowód: mutacje, porównanie z `origin/main` poza UUID, `bash scripts/gate.sh api -rs` i kontrola zakresu diffu.

Krok P1.3a: walidatory typu dla etykiet pól analizy.

- `backend/tests/test_generator.py`: czerwone testy kategorii, niejednoznaczności, typów pól, F9 i przełącznika.
- `backend/app/generator/form.py`: deterministyczne dopasowanie etykiety we wspólnej ścieżce generowania pól analizy.
- `DECISIONS.md`: reguła P1.3a.
- Dowód: mutacje, porównanie fixture’ów z `origin/main`, macierz z linterem, `bash scripts/gate.sh api -rs`.
- Po recenzji: odtworzyć fałszywe dopasowania w tabeli etykiet, odrzucić etykiety złożone i sprawdzić mutację tej reguły.

## Requests

(one line per change you need from another area: who asks, what, why)

- lider → Marcin (M1.1, `main.py`): `AppError` → jego kod i `detail`; błąd walidacji żądania FastAPI → 400; inny wyjątek → 500; `detail` zawsze tekstem (D2). Wyjątki wołaj nazwanymi argumentami (D1).
- lider → Marcin (M1.1): endpoint zwraca na razie stały szkielet JSON, bo wzorców COI nie ma już w `backend/tests/fixtures/` (D5).
- lider → Mikołaj (K3, `analysis.py`): `ValidationError` z `FormAnalysis.model_validate` po ponowieniach zamień na `LLMUnavailable` (D4).
- lider → Mikołaj (K2, `extract`): przytnij `images` do 20 sztuk i 40 MB przed utworzeniem `ExtractedDocument` i dopisz ostrzeżenie (D3).
- Marcin → lider (`SPEC.md`, Must 1 i „API contract”): dopisać wyjątek od zgodności typu z rozszerzeniem, np. „Plik `.doc`, który w środku jest DOCX, jest przyjmowany i czytany jak DOCX (tak są zapisane pliki `.DOC` z folderów 5 i 7). `.jpe` jest przyjmowane jak `.jpg` (plik `.JPE` w folderze 7).” Kod już tak działa (DECISIONS, M1.1); uwaga Pawła z recenzji M1.1.
- Paweł → lider (P1.2a, `SZABLONY_SEKCJI.md`, rozdz. 1): dodać tabelę „decyzja → sekcja” dla `ApplicantData` z zaznaczeniem, że dobór obowiązuje od P1.2b.
- Paweł → lider (P1.2a, `DELEGACJA.md`, rozdz. 2.1): dopisać wymagane `applicants` i `applicant: ApplicantData`, walidację i niezależność od ekstraktora oraz kolejność P1.2a → P1.2b/P1.2c.
- Mikołaj → lider (`SPEC.md`, „Model”): zamień `think: false` na `reasoning_effort: "none"`, bo `/v1` ignoruje `think` (pomiar K1 w `DECISIONS.md`).
- Mikołaj → Marcin (M1.5, `docker-compose.yml`): serwis `ollama/ollama:0.40.15` z `OLLAMA_CONTEXT_LENGTH=16384` i `OLLAMA_NO_CLOUD=1`, bez portu na hoście (API Ollamy nie ma haseł).
- Mikołaj → Marcin (`config.py`, `env.example`): `LLM_TIMEOUT_S=120` jest za małe na CPU (K1: 238–344 s na formularz); podnieś do 600 albo zmierz na maszynie demo.
- Mikołaj → web (`frontend/playwright.config.ts`): ustaw `LLM_FIXTURE` dla API, jak mówi SPEC „Real and mocked”. Dziś go nie ma, więc po K3 e2e wołałoby prawdziwy model (recenzja K1-fix2).

## Log

(one line per step: done / next / blocker)

- P0 `9fe7f2e`: done modele, wyjątki, fixture; recenzja lidera: CHANGES REQUIRED (5 ustaleń).
- P0.1 (poprawki D1–D6 na `9fe7f2e`): done `bash scripts/gate.sh api -rs` → `73 passed`, 0 pominiętych, `GATE: PASS (api)`; 65/65 mutacji wykrytych; niezależna recenzja: uwagi naniesione / next squash na `main` i usunięcie `origin/pawel/p0-models`, potem M1.1, K1–K3, P1 / blocker brak.
- M1.1: done na `c53fd46`, `gate.sh api -rs` → 155 passed, 0 pominiętych; prawdziwe pliki z folderów 2–9 przechodzą (.DOC będący DOCX → `docx`, .JPE → `jpg`) / next M1.2 JWT (po dopisaniu 401 do SPEC) / blocker brak.
- M1.1 recenzja (`aaa78da`): done uszkodzony .ods → 415 zamiast 500, pusta część pliku → 400 „Wybierz plik formularza.” (testy czerwone przed poprawką); `gate.sh api -rs` → 157 passed, 0 pominiętych / later: test limitu strumieniowego, walidacja `MAX_FILE_SIZE_MB` przy starcie, kopie pliku w pamięci (REVIEW.md) / next M1.2 JWT (po dopisaniu 401 do SPEC) albo M1.3 Docker / blocker brak.
- P1 (generator `build_form`): done `bash scripts/gate.sh api -rs` → `107 passed`, 0 pominiętych, `GATE: PASS (api)`; 34 testy w `test_generator.py`, 44/44 mutacji generatora wykrytych / next P2 linter / blocker brak.
- P1 poprawki po recenzjach (czasownik S2, zgoda bez linku przy pustym adresie, REQUIRED w S10, UUID5 z kanonicznego JSON-a, NFC w tytułach, slug i limit 60 znaków, mocniejsze testy, wyciek we wszystkich fixtures): done `bash scripts/gate.sh api -rs` → `124 passed`, 0 pominiętych, `GATE: PASS (api)`; 70/70 mutacji generatora wykrytych + test wycieku czerwony po wstrzyknięciu tekstu z folderu 1 / next P2 linter / blocker brak.
- M1.1-fix: done 4 ustalenia Pawła (limit z .env w compose + walidacja, ODS `mimetype`, błędy ZIP → 415, wielkość liter `Content-Type`) + test limitu strumieniowego; nowe testy czerwone przed poprawką, test strumieniowy czerwony po usunięciu kontroli w pętli; fuzz 200 000 uszkodzonych ZIP-ów: 0 wyjątków poza `UploadError`; `gate.sh api -rs` → 177 passed, 0 pominiętych / next zapis w SPEC (Request do lidera), potem M1.2 / blocker brak.
- P2 (linter `lint.check`): done oba wzorce COI i 4 wyniki generatora → `[]`, 119 testów lintera, 70/70 mutacji wykrytych; `bash scripts/gate.sh api -rs` → `327 passed`, 0 pominiętych, 1 ostrzeżenie Starlette, `GATE: PASS (api)` / next M1.4 i E1 mogą użyć `lint.check` / blocker brak.
- P2 po recenzji: done `isinstance` z wyłączeniem bool jako liczby, surowe znaki i obsługa błędu dekodowania JSONata, 20 nowych przypadków widzianych na czerwono, 25/25 mutacji recenzji i 70/70 mutacji P2; `bash scripts/gate.sh api -rs` → `347 passed`, 0 pominiętych, 1 ostrzeżenie Starlette, `GATE: PASS (api)` / next M1.4 i E1 / blocker brak.
- M1.2 kontrakt: done lider zatwierdził 401 w `SPEC.md` (`Authorization: Bearer <JWT_TOKEN>`, `detail` 401, JWT poza „Later”); prośba zamknięta / next M1.2 `auth.py`, `test_auth.py` / blocker: czy `/health` jest otwarte przy JWT – nierozstrzygnięte.
- M1.2: done `auth.py` (Bearer, HMAC, wymagany `exp`, sekret 32/48/64 B), 401 z `WWW-Authenticate` przed odczytem pliku, `/health` otwarte, `python -m app.auth token`, PyJWT 2.15.1 (MIT); `gate.sh api -rs` → 187 passed, 0 pominiętych; mutacje (bez zależności, bez `exp`, bez nagłówka) wykryte / next M1.3 Docker / blocker brak.
- M1.2 recenzja (subagent `reviewer`, werdykt SHIP): 0 CONFIRMED, 5 LATER (REVIEW.md): `JWT_*`/`MAX_FILE_SIZE_MB` w compose → M1.3, `securitySchemes` w OpenAPI → M1.6, kolejność w DECISIONS, walidacja sekretu przy starcie, 2 testy; `gate.sh` → 187 passed / next rebase na `origin/main`, M1.3 / blocker brak.
- P1.2a: done kontrakt MVP, 5 fixture’ów, 29 nowych przypadków czerwonych przed wdrożeniem i 25/25 mutacji wykrytych, `bash scripts/gate.sh api -rs` → `397 passed`, 0 pominiętych, 1 ostrzeżenie Starlette, `GATE: PASS (api)` / next commit człowieka i aktualizacja dokumentów przez lidera / blocker brak.
- K1 (pomiar na `2e7bdba`, gałąź przewinięta na `4e9d228`): done `llm.py` (klient `/v1`, `reasoning_effort: "none"`, `config.Settings`), `scripts/bench_model.py`, testy offline; pomiar `qwen3.5:4b`, folder 5: JSON 3/3, `FormAnalysis` 0/3, DOCX 238–344 s, JPG 575 s (`DECISIONS.md`); `gate.sh api -rs` na `4e9d228` → 259 passed, 0 pominiętych; 35/35 mutacji wykrytych / next K2 (skany przez OCR), K3 z ponowieniem po błędzie walidatora / blocker `LLM_TIMEOUT_S=120` krótszy niż czas na CPU (prośba do Marcina).
- K1 recenzja (Codex, baza `4e9d228`; P2 weszło potem na `main`): done 1/8 CONFIRMED, `llm.py` zamienia zły typ `usage`, tokenów i `reasoning` na brak wartości (wcześniej `AttributeError` omijał `LLMUnavailable`, czyli 503); 4 nowe przypadki czerwone przed poprawką, 5/5 mutacji wykrytych; `gate.sh api -rs` → 263 passed, 0 pominiętych, `GATE: PASS (api)` / later: 7 ustaleń (proxy w httpx, 6 w `bench_model.py`) w REVIEW.md / next scalenie z `main`: konflikt w PROGRESS.api.md, zostaw oba wpisy / blocker brak.
- K1-fix2 (zakres lidera; scalony `main` `d0c07fd` z M1.2 JWT i P1.2a): done #1 `trust_env=False` w `llm.py` i w sondzie wersji, #2 odrzucanie kopii folderu 1 po sha256 (na prawdziwych materiałach odrzuca 1 kopię), #3 i rozjazd promptu z P1.2a zapisane jako wymagania przed pomiarem; kolizja z P1.2a (`applicants` bez domyślnej wartości) rozwiązana w scaleniu: `applicants_ok` fałszywe przy braku klucza; 4 nowe testy bez sieci, czerwone przed poprawką, 6/6 mutacji wykrytych także po scaleniu; samo scalenie → 462 passed, całość `gate.sh api -rs` → 466 passed, 0 pominiętych, `GATE: PASS (api)`; recenzje: Codex (nowe zmiany) 8 uwag, w testach naniesione N3–N7, `reviewer` (cały PR do `c7d6cf1`) SHIP, 0 CONFIRMED / later: #4, #5, #7, #8, N1, N2, N8, K3: `chat_json` z ustawieniami z `Depends` i gałąź `LLM_FIXTURE` (REVIEW.md) / next K2 / blocker `LLM_TIMEOUT_S=120` (prośba do Marcina).
- P1.2b: done dobór sekcji i SHOW, regresje F2–F4 i F6–F9, 2 976 kombinacji z P2 (1,76 s), 36/36 mutacji; trzy fixture’y identyczne z `origin/main`, ENTITY zmieniony zgodnie z nowymi regułami; `bash scripts/gate.sh api -rs` → `441 passed`, 0 pominiętych, 1 ostrzeżenie Starlette, `GATE: PASS (api)` / next commit człowieka / blocker brak.
- P1.3a: done walidatory z etykiet w obu ścieżkach analizy, 16 czerwonych przypadków przed zmianą, 17/17 mutacji wykrytych, 5 fixture’ów identycznych z `origin/main`, pełna macierz 2 976 kombinacji (1,71 s), `bash scripts/gate.sh api -rs` → `516 passed`, 0 pominiętych, 1 ostrzeżenie Starlette, `GATE: PASS (api)` / next commit człowieka / blocker brak.
- P1.3a po recenzji: done etykieta złożona bez walidatora typu, 13 błędów odtworzonych przed zmianą i po wyłączeniu reguły, 5 fixture’ów identycznych z `origin/main`, `bash scripts/gate.sh api -rs` → `538 passed`, 0 pominiętych, 1 ostrzeżenie Starlette, `GATE: PASS (api)` / next commit człowieka / blocker brak.
