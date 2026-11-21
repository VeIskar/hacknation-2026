# DELEGACJA – kto co robi (dla ludzi i agentów)

> **Agencie: przeczytaj ten plik w całości przed pracą**, potem `AGENTS.md`, potem swoją sekcję niżej.
> Pracujesz **tylko w plikach przypisanych do Twojej osoby** (kolumna „Pliki”). Interfejsy z rozdz. 2 są umową – nie zmieniaj ich bez zgody ludzi.
> Szczegóły formatu JSON COI: `SZABLONY_SEKCJI.md`. Kontekst: `docs/BRIEF_ZESPOL.md`. Testy jakości: `docs/ZESTAW_TESTOWY.md`.
> Wzorce COI (źródło prawdy): `materialy/1. …/konfiguracja_form_…NumeruPorządkowego….json` i `materialy/5. …/konfiguracja_form_…NadpłatyPodatku….json`.

Stan: sob. 12:40. `SPEC.md` zostaje bez zmian; różnice z tym plikiem są drobne i świadome (rozdz. 7).

---

## 0. Cel numer 1: REST API działa – front na końcu

```
docker compose up
curl -F "file=@materialy/3. …/Wniosek o wydanie zaświadczenia.pdf" http://localhost:8000/api/forms
→ 200 + JSON w formacie COI, który przechodzi nasz linter
```
To jest **Kamień M1**. Dopóki nie jest zielony, nikt nie robi frontu.

## 1. Osoby i obszary

| Osoba | Rola | Pliki (tylko te edytujesz) | `.hn-area` |
|---|---|---|---|
| **Marcin** | API i infrastruktura | `backend/app/main.py`, `config.py`, `files.py`, `auth.py`, `backend/Dockerfile`, `docker-compose.yml`, `env.example`, `backend/requirements.txt`, `README.md`, testy: `test_files.py`, `test_auth.py`, `test_api.py` | `api` |
| **Mikołaj** | Odczyt plików i model AI | `backend/app/extract/*`, `backend/app/llm.py`, `backend/app/analysis.py`, `backend/app/prompts/*`, `scripts/bench_model.py`, testy: `test_extract.py`, `test_analysis.py` | `api` |
| **Paweł** | Generator JSON COI, linter, eval, (na końcu) front | `backend/app/models.py`, `backend/app/generator/*`, `backend/app/lint.py`, `backend/app/eval.py`, `backend/tests/fixtures/*`, testy: `test_generator.py`, `test_lint.py`; później `frontend/` | `api` (front: `web`) |

Jeśli role trzeba zamienić (np. autor SPEC woli inną część) – zamieńcie imiona w tej tabeli, reszta pliku zostaje.

Zmiana w cudzym pliku: nie rób jej. Dopisz linię w „Requests” w `PROGRESS.api.md` (`kto → komu: co i dlaczego`) i powiedz tej osobie.
Zależność nowa: jedna linia w `DECISIONS.md` (po co, licencja). Tylko MIT / Apache / BSD.

---

## 2. Interfejsy (umowa między osobami – każdy koduje pod nie od razu)

```
bytes pliku ─► files.validate_upload ─► extract.extract ─► analysis.analyze ─► generator.build_form ─► lint.check ─► JSON
              (Marcin)                  (Mikołaj)          (Mikołaj)           (Paweł)                 (Paweł)
```

### 2.1 `backend/app/models.py` i `backend/app/errors.py` (P0 – na `main`, wszyscy importują)

**Źródłem prawdy jest kod** w `backend/app/models.py` – nie przepisuj go, importuj. Skrót:

| Model | Kto tworzy | Pola |
|---|---|---|
| `ExtractedDocument` | extract (Mikołaj) | `source_format`, `text` (strony rozdzielone `\f`), `ocr_used`, `images: list[bytes]` (PNG stron skanu – dla Qwen z obrazem), `warnings` |
| `FormAnalysis` | analysis (Mikołaj) → czyta generator (Paweł) | `title` (≤255), `addressee {type: URZAD/ORGAN, name}`, `applicants: PERSON/ENTITY/BOTH`, `signature`, `subject_pages[] → sections[] → fields[]`, `statements[]` |
| `SubjectField` | – | `label`, `type` (TEXT_FIELD, TEXTAREA, NUMBER, DATEPICKER, RADIO, CHECKBOX, SELECT, FILE_UPLOADER, TEXT_BLOCK), `required`, `description`, `options[]`, `show_if {field, equals}` |

Opisy pól (`description=`) są po polsku, bo trafiają do schematu JSON, który dostaje model: `FormAnalysis.model_json_schema()`.

`backend/app/errors.py`: `AppError(detail, status_code)` i podklasy `UploadError` (400; 413/415 przez `status_code`), `ExtractionError` (422), `LLMUnavailable` (503). `main.py` zamienia każdy `AppError` na `{"detail": ...}`.

### 2.2 Funkcje

| Funkcja | Właściciel | Sygnatura | Błędy |
|---|---|---|---|
| walidacja | Marcin | `files.validate_upload(filename: str, data: bytes, max_bytes: int) -> str` (zwraca rozszerzenie małymi literami, `jpeg`/`jpe` → `jpg`) | `errors.UploadError(detail, status_code)` – 400 / 413 / 415 |
| odczyt | Mikołaj | `extract.extract(data: bytes, ext: str) -> ExtractedDocument` | `errors.ExtractionError` → 422 |
| analiza | Mikołaj | `analysis.analyze(doc: ExtractedDocument) -> FormAnalysis` | `errors.LLMUnavailable` → 503 |
| generator | Paweł | `generator.build_form(a: FormAnalysis) -> dict` (gotowy JSON COI) | – (zawsze zwraca poprawny JSON) |
| linter | Paweł | `lint.check(form: dict) -> list[str]` (pusta lista = OK) | – |

`main.py` (Marcin) tylko skleja te funkcje i mapuje wyjątki na kody HTTP z `SPEC.md` („API contract”).

### 2.3 Fixtures (Paweł, w kroku P0)

- `backend/tests/fixtures/fields.json` – `FormAnalysis` dla nadpłaty (pełny przykład w `docs/BRIEF_ZESPOL.md`, pkt 3). To zwraca `llm.py`, gdy ustawione `LLM_FIXTURE`.
- `backend/tests/fixtures/expected_nadplata.json` – kopia wzorca COI z folderu 5.
- `backend/tests/fixtures/expected_numer_porzadkowy.json` – kopia wzorca COI z folderu 1 (tylko testy i linter, **nie do promptów**).

---

## 3. Zadania – kolejność i kryteria ukończenia

### ⭐ Pierwsze zadanie do oddelegowania: **Marcin – M1.1 „Szkielet API, który już odpowiada”**

Dlaczego pierwsze: odblokowuje wszystkich. Od razu jest działający `POST /api/forms`, w który pozostali tylko podpinają swoje funkcje. Dopóki generator i AI nie są gotowe, endpoint zwraca wzorzec COI z fixtures, a front i eval mogą już z nim pracować.

| | |
|---|---|
| Zakres | `config.py` (zmienne z rozdz. 5), `files.py` (nazwa ≤250 i bez `; : > < / \ | ' * % $`, rozmiar z `MAX_FILE_SIZE_MB`, rozszerzenie bez względu na wielkość liter z listy pdf, doc, docx, ods, xlsx, jpg, jpeg, png (+ jpe → zapytać mentora), **sygnatura pliku** zgodna z rozszerzeniem), `main.py` z `POST /api/forms` zwracającym na razie `fixtures/expected_nadplata.json`, `requirements.txt` + `python-multipart` |
| Sygnatury (bez nowych zależności) | PDF `%PDF` · PNG `\x89PNG` · JPG `\xFF\xD8\xFF` · DOC `\xD0\xCF\x11\xE0` · DOCX/XLSX ZIP `PK` + `word/` / `xl/` w środku · ODS ZIP `PK` + plik `mimetype` = `application/vnd.oasis.opendocument.spreadsheet` |
| Bez zapisu na dysk | plik tylko w pamięci (`await file.read()`), limit czytany strumieniowo |
| Gotowe, gdy | `test_files.py` + `test_api.py`: 200 dla każdego z 8 formatów (małe pliki-próbki budowane w teście), 400 nazwa, 413 rozmiar, 415 zły typ, 415 fałszywy PDF; `bash scripts/gate.sh api` zielone |
| Czas | ~1–1,5 h (do 14:00) |

### Równolegle od 12:45

| Kod | Osoba | Zadanie | Gotowe, gdy | Do |
|---|---|---|---|---|
| **P0** | Paweł | `models.py` (rozdz. 2.1) + fixtures (2.3) | import działa, commit na `main` | 13:00 |
| **P1** | Paweł | **Generator**: `FormAnalysis` → JSON COI wg `SZABLONY_SEKCJI.md` (strona „Dane” z szablonów, strony przedmiotu, „Kontakt i zgody”, „Strona końcowa”, `flow`) | `test_generator.py`: z `fields.json` powstaje JSON, którego techName sekcji i pól na stronach szablonowych = wzorzec COI; strona przedmiotu ma pola z fixture | 14:30 |
| **P2** | Paweł | **Linter**: JSON Schema COI (z poprawką `repeatingSectionGrid`) + reguły techniczne (≥2 strony, ostatnia FINISH, na FINISH tylko TEXT_BLOCK/INFO_SECTION, pola tylko w sekcjach, brak zagnieżdżeń, `flow` łączy wszystkie strony, jsonata wskazuje istniejące strony i techName, unikalne id i techName) | oba wzorce COI → 0 błędów; zepsute kopie → konkretne błędy | 15:30 |
| **K1** | Mikołaj | **Ollama na laptopie + sprawdzenie Qwen3.5-4B** (rozdz. 4) | `scripts/bench_model.py` – czas i poprawność JSON (`think: false`) na tekście nadpłaty i numeru porządkowego; Bielik jako porównanie; wynik w `DECISIONS.md` | 14:00 |
| **K2** | Mikołaj | **Odczyt**: pdf (pypdf), docx (python-docx: akapity + tabele; obrazy → OCR), xlsx (openpyxl), ods (odfpy), doc (olefile), jpg/png (OCR tesseract `pol` lub model z obrazem – wg K1) | `test_extract.py`: dla folderów 1 i 5 każdy z 8 formatów zwraca tekst zawierający „wniosek” i słowa kluczowe | 16:00 |
| **K3** | Mikołaj | **Analiza**: `llm.py` (OpenAI-compatible → **lokalna** Ollama, wymuszony JSON wg `FormAnalysis.model_json_schema()`, timeout → `LLMUnavailable`, `LLM_FIXTURE`) + `analysis.py` (prompt z zasadami z `SZABLONY_SEKCJI.md` rozdz. 6) | test z fixture; ręcznie: tekst nadpłaty → `FormAnalysis` waliduje się | 17:00 |

### Potem (Marcin, gdy M1.1 gotowe)

| Kod | Zadanie | Gotowe, gdy | Do |
|---|---|---|---|
| **M1.2** | JWT (`auth.py`, PyJWT): `JWT_ENABLED`, `JWT_SECRET`, `JWT_ALGORITHM`; 401 gdy brak/zły token; skrypt `python -m app.auth token` do wygenerowania tokenu | `test_auth.py` | 15:00 |
| **M1.3** | Docker zgodny z pkt 5: `python:3.14.x-slim` (jawna wersja), użytkownik `app` bez roota, tesseract + `tesseract-ocr-pol` z apt, tylko port 8000; web: nginx bez roota na 8080 | `docker compose build` OK; `docker compose exec api whoami` → `app` | 16:00 |
| **M1.4** | **Sklejenie**: `main.py` woła `validate_upload → extract → analyze → build_form → lint`; błędy → 400/401/413/415/422/503 | `test_api.py` z `LLM_FIXTURE`: PDF → JSON, linter 0 błędów | 17:30 |
| **M1.5** | **Model w compose**: serwis `ollama` (`ollama/ollama:<jawna wersja>`), wolumen z modelem, `scripts/pull_model.sh`, `LLM_BASE_URL=http://ollama:11434/v1` | `docker compose up` + `curl` na plik z folderu 3 → JSON w < 2 min | 18:30 |
| **M1.6** | README: build, uruchomienie, tabela konfiguracji, REST API z przykładami `curl` i kodami błędów | ktoś spoza backendu uruchamia z README | 19:30 |

### Po M1 (wieczór i noc)

| Kod | Osoba | Zadanie |
|---|---|---|
| E1 | Paweł | `python -m app.eval`: JSON-y dla folderów 2–4, 6–9 + raport zgodności ze wzorcami 1 i 5 dla 8 formatów (`docs/ZESTAW_TESTOWY.md`) |
| D1 | Marcin | `docs/ARCHITEKTURA.md` – **część minimum zadania** (moduły, przepływ, kontrakty, decyzje, koszt, uruchomienie on-prem) |
| Q1 | Mikołaj | jakość AI: prompt strojony na nadpłacie, sprawdzany na numerze porządkowym (zbiór kontrolny – nie wklejamy go do promptu); formularz 9 (3 wnioski w 1) |
| F1 | Paweł | **prosty front**: jedna strona – wybór pliku, „Analizuj formularz”, komunikat błędu (`role="alert"`), „Pokaż JSON”, „Pobierz JSON” (kroki 1–3, 7, 8 z SPEC) |
| F2 | Paweł | podgląd eUsługi z jsonatą i walidatorami (kroki 4–6) – tylko jeśli F1 i E1 gotowe |

**Draft w systemie HackNation do 20:00** (nazwa, zespół, repo, stolik, opis) – Marcin wysyła o 19:30.

---

## 4. Model lokalny

| | **Qwen3.5-4B** (`qwen3.5:4b`) | **Bielik-4.5B-v3.0-Instruct** (`SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0`) |
|---|---|---|
| Rozmiar w Ollamie | 3,4 GB (Q4_K_M) | 5,1 GB (Q8_0) |
| Licencja | Apache-2.0 | Apache-2.0 + Terms of Use SpeakLeash |
| Polski | dobry | **najlepszy w tej klasie** (trenowany na polszczyźnie) |
| Obraz na wejściu | **tak** (może czytać skany zamiast OCR) | nie |
| Uwaga | domyślnie „myśli” przed odpowiedzią → **wyłączyć** (`think: false`), inaczej wolno | starszy (2025), oficjalnie tylko Q8_0/FP16 w Ollamie |

**Decyzja zespołu (12:35): Qwen3.5-4B** – zapisane w `SPEC.md`, rozdz. „Model”. Pomiar K1 tylko potwierdza, że działa (czas, poprawny JSON); Bielik zostaje zapasem.
Dawne kryteria wyboru (dla zapasu): Kryteria w tej kolejności: (1) poprawny `FormAnalysis` z wymuszonym JSON, (2) jakość polskich etykiet, (3) czas < 60 s na formularz na CPU.
Domyślnie stawiamy na **Qwen3.5-4B** (mniejszy, czyta obrazy, dobry w strukturze), **Bielik jako alternatywa jednym `LLM_MODEL`** – to też argument na slajd „model wymienny, działa on-prem, koszt ~0”.
Nie używamy w produkcie modeli z chmury (Treść pkt 5). Claude/Gemini tylko do pisania kodu.

---

## 5. Konfiguracja (zmienne środowiskowe – Marcin w `config.py` i `env.example`)

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `MAX_FILE_SIZE_MB` | `10` | limit rozmiaru |
| `JWT_ENABLED` | `false` | wymóg tokenu |
| `JWT_SECRET` | – | tylko w runtime |
| `JWT_ALGORITHM` | `HS256` | |
| `LLM_BASE_URL` | `http://ollama:11434/v1` (lokalnie: `http://localhost:11434/v1`) | **lokalny** serwer modelu |
| `LLM_MODEL` | `qwen3.5:4b` | |
| `LLM_API_KEY` | `ollama` | Ollama go ignoruje |
| `LLM_TIMEOUT_S` | `120` | po przekroczeniu 503 |
| `LLM_FIXTURE` | – | ścieżka do `fields.json`; testy bez modelu |
| `OCR_LANG` | `pol` | |
| `ADD_VALIDATORS` | `true` | walidatory REQUIRED/PESEL/… (wzorce COI mają puste) |

---

## 6. Zasady pracy

1. Każde zadanie = jeden `/hn-krok` (agent: przeczytaj `.claude/skills/hn-krok/SKILL.md`): plan ≤10 linii w `PROGRESS.api.md` → kod + test → `bash scripts/gate.sh api` → stop → człowiek commituje.
2. Gałęzie: `marcin/…`, `mikolaj/…`, `pawel/…`; merge do `main` tylko z zieloną bramką. `git pull --rebase` przed pushem.
3. Testy nigdy nie wołają modelu (`LLM_FIXTURE`).
4. Materiały COI: skopiuj folder `Materiały do zadania dla Uczestników` do `hacknation-2026/materialy/` (poza gitem – dopisz `materialy/` do `.gitignore`, Marcin).
5. Zabronione zależności: PyMuPDF (AGPL), pdf2image/poppler (GPL), Ghostscript/ocrmypdf (AGPL), antiword (GPL). LibreOffice – tylko po zgodzie mentora.
6. Co 2 h krótki sync (2 min): co gotowe, co blokuje.

---

## 7. Różnice względem `SPEC.md` (świadome, SPEC zostaje)

- Priorytet: M1 (API) przed Must 3 i 4 (front).
- JWT robimy w M1 (SPEC: Later) – wymagają tego wymagania techniczne.
- Dokumentacja architektury (D1) – część minimum zadania.
- Model tylko lokalny; `env.example` do poprawy (teraz wspomina hostowane modele).
- Docker: Python 3.14 i użytkownik bez roota (wymóg pkt 5).
- 422 przy nieczytelnym pliku, 401 przy JWT – dodatkowe kody.

---

## 8. Gotowe prompty dla agentów (skopiuj do Claude Code / Antigravity)

**Marcin – M1.1**
```
Przeczytaj DELEGACJA.md (rozdz. 0–3, zadanie M1.1), AGENTS.md i SPEC.md (API contract).
Zrób zadanie M1.1: config.py, files.py, POST /api/forms zwracający na razie
backend/tests/fixtures/expected_nadplata.json, python-multipart w requirements + linia w DECISIONS.md.
Testy w test_files.py i test_api.py wg kolumny „Gotowe, gdy”. Pliki w pamięci, bez zapisu na dysk.
Nie ruszaj plików innych osób. Uruchom bash scripts/gate.sh api, wklej wynik, zatrzymaj się z komunikatem commita.
```

**Paweł – P0 + P1**
```
Przeczytaj DELEGACJA.md (rozdz. 2 i zadania P0, P1), SZABLONY_SEKCJI.md i oba wzorce COI z materialy/1. i materialy/5.
P0: utwórz backend/app/models.py dokładnie wg rozdz. 2.1 oraz fixtures z rozdz. 2.3.
P1: backend/app/generator/ – build_form(FormAnalysis) -> dict w formacie COI: wszystkie klucze pola zawsze obecne,
repeatingSectionGrid, cols 3, y/rows/questionOrder wg SZABLONY rozdz. 0, sekcje szablonowe wg rozdz. 3–4,
strony przedmiotu z FormAnalysis, jsonata w formacie COI, flow.links.
Test: z fields.json techName sekcji i pól na stronach szablonowych zgodne z wzorcem z folderu 5.
Uruchom bash scripts/gate.sh api, wklej wynik, zatrzymaj się z komunikatem commita.
```

**Mikołaj – K1 + K2**
```
Przeczytaj DELEGACJA.md (rozdz. 2, 4 i zadania K1, K2).
K1: scripts/bench_model.py – dla qwen3.5:4b (think wyłączone) i SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0 w lokalnej Ollamie
wyślij tekst wniosku z materialy/5. i materialy/1. z wymuszonym JSON wg FormAnalysis.model_json_schema();
zmierz czas i czy wynik waliduje się Pydantikiem. Wynik i decyzja → DECISIONS.md.
K2: backend/app/extract/ – extract(data, ext) -> ExtractedDocument dla 8 formatów (rozdz. 3, K2), tylko licencje MIT/Apache/BSD.
Test: dla folderów 1 i 5 każdy format daje tekst ze słowami kluczowymi.
Uruchom bash scripts/gate.sh api, wklej wynik, zatrzymaj się z komunikatem commita.
```
