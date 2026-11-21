# PROGRESS (area: api, directory backend/)

## State

2026-11-21 19:00 · M1.5 gotowe do commita na `marcin/m1.5` (worktree `.claude/worktrees/m1.5`, baza `marcin/m1.3`,
już na `main` jako #9). Przed PR: scalić `origin/main` (konflikty w `PROGRESS.api.md`, `DECISIONS.md`).
Next: M1.4 (czeka na K2/K3; można zacząć z zaślepkami), `LLM_TIMEOUT_S` (prośba Mikołaja), M1.6 README.

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

Krok M1.3 (Marcin): obraz `api` zgodny z Treść pkt 5 (bez roota, jawne wersje, bez trwałego zapisu).
- `backend/Dockerfile`: `python:3.14.10-slim-trixie`, `tesseract-ocr` + `tesseract-ocr-pol` z apt, użytkownik
  `app` (UID 10001) bez powłoki, kod tylko do odczytu, `EXPOSE 8000`.
- `docker-compose.yml` (`api`): `read_only`, `tmpfs /tmp`, `cap_drop: ALL`, `no-new-privileges`.
- `DECISIONS.md`: obraz bazowy, tesseract (licencje). Web (nginx bez roota na 8080) → Request do `web`.
- Dowód: `test_docker.py` (statycznie: wersja obrazu, USER, port, compose); `docker compose build api`,
  `whoami` → `app`, `tesseract --list-langs` ma `pol`, `/health` 200, zapis poza `/tmp` odrzucony.

Krok M1.5 (Marcin): model w compose (DELEGACJA M1.5, ustalenia K1 w DECISIONS).
- `ollama/Dockerfile`: `ollama/ollama:0.40.15` (wersja z K1), użytkownik `ollama` (10002) bez roota.
- `docker-compose.yml`: serwis `ollama` bez portu na hoście, wolumen `ollama-models`, `OLLAMA_CONTEXT_LENGTH=16384`,
  `OLLAMA_KEEP_ALIVE`; `api` dostaje domyślnie `LLM_BASE_URL=http://ollama:11434/v1`.
- `scripts/pull_model.sh`: uruchamia `ollama` i pobiera `LLM_MODEL` (domyślnie `qwen3.5:4b`) do wolumenu.
- `backend/tests/test_config.py`, `test_docker.py`: domyślna wartość w compose, serwis `ollama` (statycznie).
- Dowód: `pull_model.sh`, z kontenera `api` zapytanie `/v1/chat/completions` do `ollama` → odpowiedź modelu.

Krok K3 (Mikołaj, gałąź `mikolaj/k3`): `ExtractedDocument` → `FormAnalysis` przez lokalny model.

- `backend/app/llm.py`: `settings` wymagane (bez `get_settings()`); `LLM_FIXTURE` zwraca plik bez sieci, nieczytelny → `LLMUnavailable`.
- `backend/app/analysis.py`: `analyze(doc, *, settings)`; prompt z kontraktem `applicant` i zasadą podstawy w treści; lekkie uporządkowanie tekstu; budżet kontekstu; 2 próby z błędami walidatora, potem 503.
- Testy bez modelu i bez K2 (przykładowy `ExtractedDocument`): `backend/tests/test_analysis.py` (nowy), `backend/tests/test_llm.py`.
- `DECISIONS.md` (api): K3. Requests: Marcin (M1.4, kontekst), lider (DELEGACJA 2.2, SPEC, nowe zadania).
- Dowód: mutacje, `bash scripts/gate.sh api -rs`, ręcznie DOCX nadpłaty → `FormAnalysis` na `qwen3.5:4b`.

Krok K2.1 (Mikołaj): pierwszy odczyt przez `extract(data, ext)` dla DOCX z tekstem.

- `backend/app/extract/`: odczyt akapitów, tabel i podziałów stron z głównego XML w pamięci.
- `backend/tests/test_extract.py`: syntetyczne DOCX, błędy odczytu i próbki COI z folderów 1 i 5.
- Dowód: zaobserwowany RED, przywrócenie bajtów po mutacjach i `bash scripts/gate.sh api -rs`.

Krok K2.2 (Mikołaj): lokalny OCR dla JPG i PNG, w tym aliasów normalizowanych podczas uploadu.

- `backend/app/extract/`: przekazanie bajtów przez stdin do Tesseract, `OCR_LANG`, limit czasu i tekst w `ExtractedDocument`.
- `backend/tests/test_extract.py`: wybór języka, przekazanie bajtów, brak tekstu i błędy OCR bez procesu zewnętrznego.
- Dowód: RED/GREEN, `bash scripts/gate.sh api -rs` oraz Tesseract `pol` na skanach z folderów 1 i 5.

Krok K2.3 (Mikołaj): odczyt warstwy tekstowej PDF przez `pypdf`, bez OCR.

- `backend/app/extract/`: strony z bajtów w pamięci, kolejność stron, separator `\f`, ostrzeżenie o stronach bez tekstu, błędy odczytu jako `ExtractionError`.
- `backend/tests/test_extract.py`: PDF wielostronicowy, pusta strona, PDF bez tekstu, pliki uszkodzone, polskie znaki, próbki COI z folderów 1 i 5; OCR nie jest wołany.
- Zależność `pypdf==7.1.1` (BSD-3-Clause): wpis w `DECISIONS.md`, a linia w `requirements.txt` to Request do Marcina.
- Dowód: RED/GREEN każdego testu i `bash scripts/gate.sh api -rs`.

Krok M1.4 (Marcin): sklejenie `POST /api/forms` (DELEGACJA M1.4; K2 z K2.3 i K3 są na `main`).
- `backend/app/main.py`: `process_file` = `extract` → `analyze` → `build_form` → `lint.check`, w wątku
  (`run_in_threadpool`), bo `analyze` trwa minuty i blokowałby `/health`. Błędy lintera → 500 + log (tymczasowo, pytanie do lidera).
- `backend/tests/test_api.py`: prawdziwy łańcuch z `LLM_FIXTURE` (PDF i DOCX → JSON, linter 0 błędów), 400 z odczytu,
  503 z analizy, 500 z lintera, `/health` odpowiada w trakcie analizy; testy warstwy uploadu i JWT podmieniają `process_file`.
- Bez zmian: `LLM_TIMEOUT_S` i model (czekają na pomiar Qwen3.5-9B i decyzję lidera).

## Requests

(one line per change you need from another area: who asks, what, why)

- lider → Marcin (M1.1, `main.py`): `AppError` → jego kod i `detail`; błąd walidacji żądania FastAPI → 400; inny wyjątek → 500; `detail` zawsze tekstem (D2). Wyjątki wołaj nazwanymi argumentami (D1).
- lider → Marcin (M1.1): endpoint zwraca na razie stały szkielet JSON, bo wzorców COI nie ma już w `backend/tests/fixtures/` (D5).
- lider → Mikołaj (K3, `analysis.py`): `ValidationError` z `FormAnalysis.model_validate` po ponowieniach zamień na `LLMUnavailable` (D4).
- lider → Mikołaj (K2, `extract`): przytnij `images` do 20 sztuk i 40 MB przed utworzeniem `ExtractedDocument` i dopisz ostrzeżenie (D3).
- Mikołaj → Marcin (K2, `backend/Dockerfile` i `backend/requirements.txt`): uzgodnić instalację Tesseract z `pol` i wersję `pypdf` do odczytu PDF.
- Mikołaj → Marcin (K2.3, `backend/requirements.txt`): dopisać `pypdf==7.1.1` (BSD-3-Clause, bez wymaganych zależności, Python ≥ 3.10). Bez tej linii `import app.extract` kończy się `ModuleNotFoundError` w obrazie API i w świeżym `.venv`, więc K2.3 nie może wejść na `main` przed nią.
- Marcin → lider (`SPEC.md`, Must 1 i „API contract”): dopisać wyjątek od zgodności typu z rozszerzeniem, np. „Plik `.doc`, który w środku jest DOCX, jest przyjmowany i czytany jak DOCX (tak są zapisane pliki `.DOC` z folderów 5 i 7). `.jpe` jest przyjmowane jak `.jpg` (plik `.JPE` w folderze 7).” Kod już tak działa (DECISIONS, M1.1); uwaga Pawła z recenzji M1.1.
- Paweł → lider (P1.2a, `SZABLONY_SEKCJI.md`, rozdz. 1): dodać tabelę „decyzja → sekcja” dla `ApplicantData` z zaznaczeniem, że dobór obowiązuje od P1.2b.
- Paweł → lider (P1.2a, `DELEGACJA.md`, rozdz. 2.1): dopisać wymagane `applicants` i `applicant: ApplicantData`, walidację i niezależność od ekstraktora oraz kolejność P1.2a → P1.2b/P1.2c.
- Mikołaj → lider (`SPEC.md`, „Model”): zamień `think: false` na `reasoning_effort: "none"`, bo `/v1` ignoruje `think` (pomiar K1 w `DECISIONS.md`).
- Mikołaj → Marcin (M1.5, `docker-compose.yml`): serwis `ollama/ollama:0.40.15` z `OLLAMA_CONTEXT_LENGTH=16384` i `OLLAMA_NO_CLOUD=1`, bez portu na hoście (API Ollamy nie ma haseł).
- Mikołaj → Marcin (`config.py`, `env.example`): `LLM_TIMEOUT_S=120` jest za małe na CPU (K1: 238–344 s na formularz); podnieś do 600 albo zmierz na maszynie demo.
- Mikołaj → web (`frontend/playwright.config.ts`): ustaw `LLM_FIXTURE` dla API, jak mówi SPEC „Real and mocked”. Dziś go nie ma, więc po K3 e2e wołałoby prawdziwy model (recenzja K1-fix2). Ścieżka względna liczy się od `frontend/` (cwd Playwrighta), np. `../backend/tests/fixtures/fields.json`. Przy `reuseExistingServer: true` już działające API bez tej zmiennej też wołałoby model.
- Marcin (M1.3) → web (`frontend/Dockerfile`, `frontend/nginx.conf`): nginx bez roota (`nginxinc/nginx-unprivileged:<jawna wersja>` albo `USER nginx`), nasłuch na 8080, `EXPOSE 8080`; Treść pkt 5. Potem Marcin zmienia w compose `5173:80` na `5173:8080`.
- Mikołaj → Marcin (M1.4, `main.py`): wołaj `analysis.analyze(doc, settings=settings)` z `settings` trasy (`Depends(get_settings)`). Funkcja jest synchroniczna i na CPU trwa minuty, więc przez `run_in_threadpool`. Dokument bez tekstu i obrazów → `ExtractionError` (400), reszta błędów → `LLMUnavailable` (503).
- Mikołaj → lider (`DELEGACJA.md`, rozdz. 2.2): sygnatura `analysis.analyze(doc, *, settings) -> FormAnalysis`, `settings` wymagane też w `llm.chat_json`; `analyze` rzuca `ExtractionError` dla dokumentu bez tekstu i obrazów (K3).
- Mikołaj → Marcin (M1.5, `docker-compose.yml`, `config.py`): budżet K3 zakłada `OLLAMA_CONTEXT_LENGTH=16384` (stała `CONTEXT_TOKENS` w `analysis.py`). Tekst z folderu 8 (ok. 31 tys. znaków) się nie mieści, a folder 9 mieści się bez miejsca na ponowienie. Rozważ 32768 i zmienną `LLM_CONTEXT_TOKENS` w `Settings`, żeby serwer i analiza znały tę samą liczbę. Recenzja Codexa (P1): bez tej zmiennej większy kontekst serwera nie pomoże folderowi 8, bo K3 liczy budżet od stałej; po jej dodaniu K3 przełączy `CONTEXT_TOKENS` na `settings`.
- Mikołaj → lider (`SPEC.md`, „API contract”): dokument za długi do analizy daje dziś 503 „Model AI nie odpowiada…”, a ponowienie nic nie da. Propozycja: osobny komunikat, np. 400 „Formularz jest za długi do analizy.”.
- Mikołaj → lider (`DELEGACJA.md`, rozdz. 3): zadania po K3: (a) analiza długich dokumentów fragmentami z kontrolą kompletności (foldery 8 i 9), (b) strojenie promptu (Q1) z pomiarem na folderze 5, (c) porównanie `qwen3.5:4b` z wersją 9B: czas, pamięć, poprawność `FormAnalysis`.
- Mikołaj → lider (mentor, kontrakt P0): uzasadnienie pól w K3 jest tylko regułą promptu. Sprawdzalne uzasadnienie wymaga pola ze źródłem w `SubjectField`, np. cytatu z papieru. To zmiana kontraktu, więc decyzja lidera.
- Mikołaj → lider (`DELEGACJA.md`, rozdz. 3, Q1): pomiar K3 pokazał elementy bez podstawy w papierze (oświadczenie, pole „Inne dokumenty”, REGON) i dane wnioskodawcy powtórzone w `subject_pages`. Proponuję zadanie: deterministyczna kontrola podstawy w treści po analizie, z ponowieniem jak przy błędzie walidatora, bez zmiany kontraktu. Do tego poprawa `fields.json`, bo jego `applicant` opisuje wzorzec COI zamiast papieru (Paweł).
- Mikołaj → lider (`DELEGACJA.md`, rozdz. 3, Q1, szybkość): na CPU czas zależy od tokenów odpowiedzi (2–4,6 tokenu/s). Kolejno: (1) pierwsza próba bez błędu oszczędza ok. połowę czasu, więc w logu warto zapisywać miejsca błędów; (2) zwarty JSON bez wcięć, bo w K1 135 przejść linii to ok. 12% z 1088 tokenów; (3) GPU albo mniej obciążona maszyna, bo ten sam prompt trwał w K1 238–344 s; (4) porównanie 4B z mniejszym i większym modelem (zadanie c). Qwen 4B nie jest gotowy do demo: K3 dało wynik dopiero w 2. próbie po 1121 s, z polami bez podstawy w papierze.
- Marcin → lider (`SPEC.md`, „API contract”): jaki kod, gdy wygenerowany JSON nie przechodzi lintera? M1.4 daje tymczasowo 500 „Coś poszło nie tak. Spróbuj ponownie.” z błędami w logu (błąd po naszej stronie, nie użytkownika).

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
- M1.3 (api): done obraz `python:3.14.10-slim-trixie`, tesseract 5.5.0 + `pol`, użytkownik `app` (10001), compose `read_only`/`tmpfs /tmp`/`cap_drop ALL`/`no-new-privileges`; `docker compose build api` OK, `whoami` → `app`, `/health` 200, PDF → 200, fałszywy PDF → 415, JWT 401/200 w kontenerze, zapis poza `/tmp` odrzucony; `test_docker.py` 7/7 mutacji wykrytych; `gate.sh` → 403 passed / next web: nginx bez roota na 8080 (Request), M1.4 / blocker: licencje LGPL bibliotek tesseracta – decyzja lidera/mentora (DECISIONS M1.3).
- M1.5: done `ollama/Dockerfile` (0.40.15, UID 10002), serwis `ollama` bez portu na hoście, wolumen `ollama-models`, `read_only`/`cap_drop ALL`, `OLLAMA_CONTEXT_LENGTH=16384`, `OLLAMA_KEEP_ALIVE=24h`, `OLLAMA_NO_CLOUD=1` (prośba Mikołaja), `name: hacknation-2026` w compose (ten sam wolumen w każdym katalogu), `LLM_BASE_URL` domyślnie `http://ollama:11434/v1`, `scripts/pull_model.sh`; ręcznie: `id` → 10002, zapis poza wolumenem odrzucony, `pull_model.sh` → `qwen3.5:4b` 3,3 GB, z kontenera `api` `/v1/chat/completions` → poprawny JSON w 10,5 s, 0 znaków myślenia, `ollama ps` 16384 / 100% CPU; `gate.sh` → 409 passed / next merge `origin/main`, M1.4 / blocker: kryterium „curl na plik z folderu 3 → JSON < 2 min” dopiero po M1.4 (K2, K3).
- M1.5 recenzja (subagent `reviewer`, werdykt FIX): 1 CONFIRMED – `env.example` miał `LLM_BASE_URL=http://localhost:11434/v1`, więc `cp env.example .env` kierował `api` w compose na samego siebie (503); teraz pusty, test `test_env_example_does_not_override_compose_defaults` czerwony przed poprawką; 6 LATER (REVIEW.md): `LLM_TIMEOUT_S` 120 < 238–344 s na CPU → z M1.4, skutki `name:`, `depends_on`, sieć tylko api–ollama, komentarz w `.env` w `pull_model.sh`, kruchy `_compose_block` / next commit M1.5, merge `origin/main` / blocker brak.
- M1.5 testy compose: done regexy po wcięciach zastąpione parserem YAML (`backend/tests/compose.py`, PyYAML 6.0.4, MIT, wpis w DECISIONS) w `test_docker.py` i `test_config.py`; 5 równoważnych zapisów compose przechodzi (tmpfs skalarnie i z opcjami, `no-new-privileges` bez `:true`, komentarze w serwisie, cały plik z wcięciem 4 i posortowanymi kluczami), 8 regresji wykrytych; `gate.sh` → 410 passed / next commit M1.5 / blocker brak.
- M1.5 recenzja testów compose (`c62614a`, subagent `reviewer`, werdykt SHIP): 0 CONFIRMED, 5 LATER (REVIEW.md): PyYAML w obrazie produkcyjnym (jak pytest/ruff; `requirements-dev.txt` – lider), `safe_load` przy imporcie, anonimowe wolumeny i `- FOO` w `environment` w normalizatorach, `read_only is True` / next merge `origin/main`, PR M1.5 / blocker brak.
- pypdf (Marcin, prośba Mikołaja do K2.3): done `pypdf==7.1.1` (BSD-3-Clause) w `requirements.txt` + `DECISIONS.md`; Docker bez zmian (czysty Python); Tesseract `pol` potwierdzony w obrazie `api` tak, jak woła go K2.2 (`tesseract stdin stdout -l pol`, `app`, `read_only`) na skanie z folderu 5 / next M1.4 na K2 + K3 / blocker brak.
- P1.4: done F9 lint `[]`, 5/5 wyjść identycznych, 6/6 mutacji wykrytych, API 602/0, K3 49/0, schemat promptu +9,11% / next commit człowieka / blocker brak.
- K3: done `llm.py` (`settings` wymagane, `LLM_FIXTURE` bez sieci), `analysis.py` (prompt z kontraktem `applicant` i zasadą podstawy w treści, lekkie uporządkowanie tekstu, budżet kontekstu i kontrola przycięcia przez serwer, 2 próby, potem 503); 31/31 mutacji i mutacja D5 wykryte, 5 przebiegów bez niestabilności; ręcznie `qwen3.5:4b` na CPU: DOCX nadpłaty → poprawny `FormAnalysis` w 2. próbie, 1121 s, jakość pól do poprawy (Requests); recenzja `reviewer`: FIX (1, 2), naniesione 1–4; `bash scripts/gate.sh api -rs` → 566 passed, 0 pominiętych, `GATE: PASS (api)` / next commit człowieka, M1.4 (Marcin) z `analyze(doc, settings=settings)`, Q1 kontrola podstawy w treści / blocker `LLM_TIMEOUT_S=120` przy 537–584 s na próbę na CPU; folder 8 nie mieści się w kontekście 16384.
- K3 recenzja (Codex `--uncommitted`, baza `4e9603e`; `origin/main` = `7788a2f` z M1.3): done 2/5 CONFIRMED naprawione w obszarze: ponowienie bez długiej odpowiedzi, gdy z nią nie mieści się w kontekście (folder 9), i `json.loads` przed walidacją (samotny surogat jak w P1.2a, `RecursionError` → ponowienie); 1 CONFIRMED poza obszarem (`LLM_CONTEXT_TOKENS`, prośba do Marcina), 2 LATER, 1 FALSE (REVIEW.md); 36/36 mutacji i mutacja D5 wykryte; K3 na `origin/main` → 575 passed, konflikty tylko w dopiskach `DECISIONS.md` i `PROGRESS.api.md`; `bash scripts/gate.sh api -rs` → 569 passed, 0 pominiętych, `GATE: PASS (api)` / next commit człowieka, scalenie z `main` z zachowaniem obu dopisków, Q1 szybkość i podstawa w treści / blocker: Qwen 4B niegotowy do demo (2. próba, 1121 s, pola bez podstawy).
- K2.1 (`mikolaj/k2`, baza `4e9d228`): done tekst akapitów i tabel DOCX w pamięci, w tym próbki COI 1/5 oraz `.DOC` wykryty jako DOCX. 9/9 nowych przypadków widzianych na czerwono, po przywróceniu kodu `gate.sh api -rs` → 237 passed, a na kopii `c7d6cf1` z tym samym kodem → 406 passed, bez pominiętych / next PDF, arkusze, OCR i binarny DOC / blocker dla OCR: Tesseract z `pol` w obrazie API.
- K2.2 (`mikolaj/k2`): done lokalny OCR JPG/PNG przez Tesseract `pol`; 8 nowych przypadków RED/GREEN, 7/7 skanów COI z wymaganymi słowami (foldery 1, 5, `.JPE` z 7), 0,64–5,44 s. `gate.sh api -rs` → 245 passed w worktree, 444 passed na kopii `d0c07fd` z P1.2a, bez pominiętych / next tekst PDF, arkusze i binarny DOC / blocker wdrożenia OCR: Tesseract z `pol` w obrazie API.
- K2.1/K2.2 po recenzji: done odczyt `w:sdt` i kontrolowane 500 przy braku programu Tesseract, 3 przypadki RED/GREEN, 7/7 rzeczywistych skanów; `gate.sh api -rs` → 248 passed na bazie K2 i 558 passed na `4e9603e` z kodem K2, 0 pominiętych / next pierwszy commit po decyzji lidera / blocker integracji: konflikty w `DECISIONS.md` i `PROGRESS.api.md`, uwagi w `REVIEW.md`.
- K2.3 (`mikolaj/k2`, baza `2892e6a`): done warstwa tekstowa PDF przez `pypdf` 7.1.1: kolejność stron, separator `\f`, ostrzeżenie o stronach bez tekstu, każdy błąd odczytu jako 400, bez OCR. 13 nowych przypadków, każdy widziany na czerwono (RED albo mutacja kodu); fuzz 5877 uszkodzonych PDF-ów: 0 zawieszeń, wyjątki spoza `PyPdfError` potwierdzone; 9/9 PDF-ów COI ma tekst na każdej stronie, odczyt do 0,39 s. `gate.sh api -rs` → 261 passed, 0 pominiętych / next OCR stron PDF bez tekstu (wymaga decyzji o rendererze), obrazy w DOCX, XLSX, ODS, binarny DOC / blocker: `pypdf` w `requirements.txt` (Request do Marcina) i synchronizacja z `main`.
- K2.3 recenzja (Codex, `--uncommitted`, kopia bez `.env` i materiałów): 3 ustalenia, 0 do poprawy w K2 (brak `pypdf` w `requirements.txt` rozwiązany na `main` przez PR #13; budżet zasobów i PDF z AES jako LATER w `REVIEW.md`). Własne sondy: 1 CONFIRMED – font PDF oddawał NUL, `\f` i niesparowany surogat jako tekst (fałszywy podział stron, tekst nie do zapisania w UTF-8); poprawione, test czerwony przed poprawką. `gate.sh api -rs` → 262 passed, 0 pominiętych / next commit lidera, potem scalenie `main` / blocker brak.
- K2-merge: scalenie `main` `cb3daaa` (P2, JWT, K1, M1.3, M1.5, pypdf, K3) do `mikolaj/k2` po K2.3 `6bcbf75`; konflikty tylko w `DECISIONS.md` i `PROGRESS.api.md`, rozwiązane przez zachowanie wpisów obu stron; `gate.sh api -rs` → 616 passed, 0 pominiętych / next merge PR #12, potem pozostałe formaty K2 (XLSX, ODS, binarny DOC, OCR stron PDF i obrazów DOCX) / blocker brak.
- M1.4: done `process_file` = `extract` → `analyze` → `build_form` → `lint.check` w `run_in_threadpool`; błędy lintera → 500 + log (tymczasowo); testy: PDF i DOCX z `LLM_FIXTURE` → JSON równy `build_form(fields.json)`, linter 0 błędów; PDF bez tekstu i XLSX (brak czytnika) → 400, brak atrapy → 503, JSON odrzucony przez linter → 500, `/health` odpowiada w trakcie analizy; testy uploadu i JWT z atrapą `process_file`; 4/4 mutacje wykryte; `gate.sh api -rs` → 622 passed, 1 failed (test K3 czerwony już na `main`, Request do Mikołaja) / next pomiar Qwen3.5-9B przez API i `LLM_TIMEOUT_S` (lider), DOC/XLSX/ODS w K2 / blocker: czerwona bramka `main` przez test K3.
- K3-fix (Marcin, w uzgodnieniu z Mikołajem, plik K3): `test_deeply_nested_answer_is_a_validation_error_not_a_crash` czerwony na `main` od `cb3daaa`, bo na Pythonie 3.14 (venv i obraz `api`) `json.loads` nie rzuca `RecursionError` (sprawdzone do 100 000 poziomów) i błąd to `model_type`, nie „recursion limit exceeded”; test sprawdza teraz zachowanie niezależne od wersji (błąd walidacji całego JSON-a, ponowienie, bez 500), nowy `test_recursion_error_from_json_loads_falls_back_to_pydantic_parser` pilnuje gałęzi `RecursionError` na każdym Pythonie; `analysis.py` bez zmian; 2/2 mutacje wykryte; `gate.sh api -rs` zielony / next merge do `main`, M1.4 / blocker brak.
- P4: done strażnik w API i P3, kontrole walidatorów i słowników, ochrona źródeł SHOW przy regule Kraje, 5/5 snapshotów identycznych, 6/6 mutacji wykrytych, `bash scripts/gate.sh api -rs` → `767 passed`, 0 pominiętych, `GATE: PASS (api)` / next commit człowieka / blocker brak.
