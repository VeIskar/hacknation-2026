# DELEGACJA – kto co robi (dla ludzi i agentów)

> **Agencie: przeczytaj ten plik w całości przed pracą**, potem `AGENTS.md`, potem swoją sekcję niżej.
> Pracujesz **tylko w plikach przypisanych do Twojej osoby** (kolumna „Pliki”). Interfejsy z rozdz. 2 są umową – nie zmieniaj ich bez zgody ludzi.
> Szczegóły formatu JSON COI: `SZABLONY_SEKCJI.md`. Kontekst: `docs/BRIEF_ZESPOL.md`. Testy jakości: `docs/ZESTAW_TESTOWY.md`.
> Wzorce COI (źródło prawdy): `materialy/1. …/konfiguracja_form_…NumeruPorządkowego….json` i `materialy/5. …/konfiguracja_form_…NadpłatyPodatku….json`.

Stan: sob. 22:00. Na `main` są P0, P1, P2, P1.2a, P1.2b, P1.3a, P1.4 (złożone warunki SHOW, formularz 9 jako jeden formularz), M1.1–M1.5 (w tym sklejenie API w M1.4), K1, K2.1–K2.3 (DOCX, OCR obrazów, PDF z tekstem), K3 i P3 (`scripts/generate_forms.py`: JSON-y do oddania i raport jakości, czyli część E1). Niezaczęte na `origin`: pozostałe formaty K2, M1.6, M1.7, K3.1, D1, F1, F2. Z E1 zostaje raport zgodności ze wzorcami 1 i 5. Decyzje D1–D14 są w `DECISIONS.md`. D8 potwierdził mentor COI, a D9–D11 to decyzje lidera po konsultacji z COI (2026-11-21): Eden AI tylko z modelem otwartym (docelowo Qwen3.5-9B), jeden dokument → jeden JSON, cel 180–200 s. D12–D14 to odpowiedzi mentorów z Discorda: obrona na x86 bez GPU, walidatory dozwolone, słowniki z pliku COI. Otwarte: RAM i internet na obronie, słownik adresu zamieszkania. Nowe zadania: K3.1 i M1.7 (rozdz. 3). Pozostałe różnice: rozdz. 7.

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
| **Marcin** | API i infrastruktura | `backend/app/main.py`, `config.py`, `files.py`, `auth.py`, `backend/Dockerfile`, `docker-compose.yml`, `env.example`, `backend/requirements.txt`, `ollama/Dockerfile`, `scripts/pull_model.sh`, `README.md`, testy: `test_files.py`, `test_auth.py`, `test_api.py`, `test_config.py`, `test_docker.py`, `compose.py`, `samples.py` | `api` |
| **Mikołaj** | Odczyt plików i model AI | `backend/app/extract/*`, `backend/app/llm.py`, `backend/app/analysis.py`, `backend/app/prompts/*`, `scripts/bench_model.py`, testy: `test_extract.py`, `test_analysis.py`, `test_llm.py`, `test_bench_model.py`, `env_proxy.py` | `api` |
| **Paweł** | Generator JSON COI, linter, eval, (na końcu) front | `backend/app/models.py`, `backend/app/errors.py`, `backend/app/generator/*`, `backend/app/lint.py`, `backend/app/eval.py`, `backend/tests/fixtures/*`, `backend/tests/conftest.py`, testy: `test_models.py`, `test_errors.py`, `test_generator.py`, `test_lint.py`; później `frontend/` | `api` (front: `web`) |

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
| `ExtractedDocument` | extract (Mikołaj) | `source_format` (pdf, doc, docx, ods, xlsx, jpg, png), `text` (strony rozdzielone `\f`), `ocr_used`, `images: list[bytes]` (PNG stron skanu – dla Qwen z obrazem; najwyżej 20 sztuk i 40 MB, pomijane w `model_dump` i JSON-ie), `warnings` |
| `FormAnalysis` | analysis (Mikołaj) → czyta generator (Paweł) | `title` (≤255), `addressee {type: URZAD/ORGAN, name}`, `applicants: PERSON/ENTITY/BOTH` (wymagane), `applicant: ApplicantData` (wymagane), `signature`, `subject_pages[] → sections[] → fields[]`, `statements[]` |
| `ApplicantData` | analysis (Mikołaj) → czyta generator (Paweł) | decyzje z papieru: `proxy`, `applicant_pesel`, `person_address`, `entity_ids[]` (NIP, REGON, KRS), `entity_ids_one_of`, `entity_address`, `representative_proof`, `correspondence_address`, `contact[]` (PHONE, EMAIL), `applicant_extra_fields[]` (`SubjectField`) |
| `SubjectField` | – | `label`, `type` (TEXT_FIELD, TEXTAREA, NUMBER, DATEPICKER, RADIO, CHECKBOX, SELECT, FILE_UPLOADER, TEXT_BLOCK), `required`, `description`, `options[]`, `show_if {field, equals}` |

Opisy pól (`description=`) są po polsku, bo trafiają do schematu JSON, który dostaje model: `FormAnalysis.model_json_schema()`. Przykłady w opisach nie mogą pochodzić z folderu 1; nowy przykład trzeba dopisać do `SCHEMA_EXAMPLES` w `test_models.py`.

`FormAnalysis.model_validate` odrzuca niespójną analizę (D4 w `DECISIONS.md`): puste teksty, nieznane klucze, złe opcje i `show_if`, które nie wskazuje dokładnie jednego pola wyboru na tej samej stronie i jego opcji. Generator dostaje tylko poprawne dane.

Od P1.2a `applicants` i `applicant` są wymagane. Decyzje mają przesłanki w papierze i są niezależne od ekstraktora. `model_validate` odrzuca decyzje sprzeczne z `applicants` (np. PESEL przy ENTITY) i powtórzone identyfikatory, a reguły D4 dla `show_if` obowiązują też w `applicant_extra_fields`. Generator P1.2b dobiera z nich sekcje strony „Dane” i kontakt (tabela: `SZABLONY_SEKCJI.md` rozdz. 1; zasada D8). Kolejność: P1.2a → P1.2b (oba na `main`) → P1.2c (detektor) → P1.3 (tryby rozszerzone).

`backend/app/errors.py`: `AppError(*, detail, status_code=None)` – argumenty **tylko nazwane**, np. `UploadError(detail="…", status_code=415)`. Podklasy: `UploadError` (400, 413 albo 415), `ExtractionError` (zawsze 400), `LLMUnavailable` (zawsze 503). Wywołanie pozycyjne albo kod spoza zbioru kończy się `TypeError`/`ValueError`. `main.py` zamienia każdy `AppError` na `{"detail": ...}`.

### 2.2 Funkcje

| Funkcja | Właściciel | Sygnatura | Błędy |
|---|---|---|---|
| walidacja | Marcin | `files.validate_upload(filename: str, data: bytes, max_bytes: int) -> str` (zwraca format treści małymi literami: `jpeg`/`jpe` → `jpg`, `.doc` z treścią DOCX → `docx`, M1.1) | `errors.UploadError(detail=…, status_code=…)` – 400 / 413 / 415 |
| odczyt | Mikołaj | `extract.extract(data: bytes, ext: str) -> ExtractedDocument` | `errors.ExtractionError(detail=…)` → 400. Przed utworzeniem `ExtractedDocument` przycina `images` do 20 sztuk i 40 MB i dopisuje ostrzeżenie |
| analiza | Mikołaj | `analysis.analyze(doc: ExtractedDocument) -> FormAnalysis` | `errors.LLMUnavailable(detail=…)` → 503, także gdy wynik modelu nie przechodzi `FormAnalysis.model_validate` po ponowieniach |
| generator | Paweł | `generator.build_form(a: FormAnalysis) -> dict` (gotowy JSON COI) | – (wejście jest już zwalidowane; zawsze zwraca poprawny JSON) |
| linter | Paweł | `lint.check(form: dict) -> list[str]` (pusta lista = OK) | – |

`main.py` (Marcin) tylko skleja te funkcje i mapuje wyjątki na kody HTTP z `SPEC.md` („API contract”).

### 2.3 Fixtures (Paweł, w kroku P0)

- `backend/tests/fixtures/fields.json` – `FormAnalysis` dla nadpłaty. Źródłem prawdy jest ten plik: przykład w `docs/BRIEF_ZESPOL.md`, pkt 3, jest sprzed P1.2a i nie ma `applicant`. To zwraca `llm.py`, gdy ustawione `LLM_FIXTURE`.
- Wzorców COI **nie ma w gicie** (D5). Testy biorą je z `materialy/` przez fixture’y z `backend/tests/conftest.py`: `coi_working_reference` (folder 5) i `coi_control_reference` (folder 1, tylko testy i linter, **nie do promptów**). Bez `materialy/` takie testy są pomijane.

---

## 3. Zadania – kolejność i kryteria ukończenia

### ⭐ Pierwsze zadanie do oddelegowania: **Marcin – M1.1 „Szkielet API, który już odpowiada”**

Dlaczego pierwsze: odblokowuje wszystkich. Od razu jest działający `POST /api/forms`, w który pozostali tylko podpinają swoje funkcje. Dopóki generator i AI nie są gotowe, endpoint zwraca stały szkielet JSON, a front i eval mogą już z nim pracować.

| | |
|---|---|
| Zakres | `config.py` (zmienne z rozdz. 5), `files.py` (nazwa ≤250 i bez `; : > < / \ | ' * % $`, rozmiar z `MAX_FILE_SIZE_MB`, rozszerzenie bez względu na wielkość liter z listy pdf, doc, docx, ods, xlsx, jpg, jpeg, png (+ jpe → zapytać mentora), **sygnatura pliku** zgodna z rozszerzeniem), `main.py` z `POST /api/forms` zwracającym na razie stały szkielet `{"title": "…", "tabs": [], "flow": {"links": []}}` (do czasu P1; plików COI nie ma w repo), obsługa błędów wg `SPEC.md`: `AppError` → jego kod i `detail`, błąd walidacji żądania FastAPI → 400, każdy inny wyjątek → 500, `detail` zawsze tekstem, `requirements.txt` + `python-multipart` |
| Sygnatury (bez nowych zależności) | PDF `%PDF` · PNG `\x89PNG` · JPG `\xFF\xD8\xFF` · DOC `\xD0\xCF\x11\xE0` · DOCX/XLSX ZIP `PK` + `word/` / `xl/` w środku · ODS ZIP `PK` + plik `mimetype` = `application/vnd.oasis.opendocument.spreadsheet` |
| Bez zapisu na dysk | plik tylko w pamięci (`await file.read()`), limit czytany strumieniowo |
| Gotowe, gdy | `test_files.py` + `test_api.py`: 200 dla każdego z 8 formatów (małe pliki-próbki budowane w teście), 400 nazwa, 400 brak pola `file` (tekstowe `detail`, nie lista FastAPI), 413 rozmiar, 415 zły typ, 415 fałszywy PDF, 500 z tekstowym `detail` przy nieoczekiwanym wyjątku; `bash scripts/gate.sh api` zielone |
| Czas | ~1–1,5 h (do 14:00) |

### Równolegle od 12:45

| Kod | Osoba | Zadanie | Gotowe, gdy | Do |
|---|---|---|---|---|
| **P0** | Paweł | `models.py`, `errors.py` (rozdz. 2.1) + fixtures (2.3) + poprawki po recenzji (D1–D6) | import działa, bramka zielona, na `main` jako squash (bez kopii wzorców COI w historii) | 13:00 |
| **P1** | Paweł | **Generator**: `FormAnalysis` → JSON COI wg `SZABLONY_SEKCJI.md` (strona „Dane” z szablonów, strony przedmiotu, „Kontakt i zgody”, „Strona końcowa”, `flow`) | `test_generator.py`: z `fields.json` powstaje JSON, którego techName sekcji i pól na stronach szablonowych = wzorzec COI (`coi_working_reference`); strona przedmiotu ma pola z fixture. Walidacja nie pilnuje wszystkiego: generator sam nadaje unikalne techName (powtórzone etykiety, tytuły sekcji i stron), escapuje cudzysłów w opcjach i nie daje REQUIRED polom TEXT_BLOCK | 14:30 |
| **P2** | Paweł | **Linter**: JSON Schema COI (z poprawką `repeatingSectionGrid`) + reguły techniczne (≥2 strony, ostatnia FINISH, na FINISH tylko TEXT_BLOCK/INFO_SECTION, pola tylko w sekcjach, brak zagnieżdżeń, `flow` łączy wszystkie strony, jsonata wskazuje istniejące strony i techName, unikalne id i techName) | oba wzorce COI (fixture’y z `conftest.py`) → 0 błędów; zepsute kopie → konkretne błędy. Uwaga: jedna sekcja we wzorcu 1 nie ma klucza `states`, więc linter traktuje jego brak jak pustą listę | 15:30 |
| **K1** | Mikołaj | **Ollama na laptopie + sprawdzenie Qwen3.5-4B** (rozdz. 4) | `scripts/bench_model.py` – czas i poprawność JSON (`reasoning_effort: "none"`; `think` na `/v1` nie działa) na tekście nadpłaty i numeru porządkowego; Bielik jako porównanie; wynik w `DECISIONS.md` | 14:00 |
| **K2** | Mikołaj | **Odczyt**: pdf (pypdf), docx (python-docx: akapity + tabele; obrazy → OCR), xlsx (openpyxl), ods (odfpy), doc (kierunek: LibreOffice, konkretna zależność po sprawdzeniu licencji – rozdz. 6 pkt 5; `.doc` z treścią DOCX przychodzi już jako `docx`), jpg/png (OCR tesseract `pol`; obraz w modelu tylko jako zapas – wynik K1) | `test_extract.py`: dla folderów 1 i 5 każdy z 8 formatów zwraca tekst zawierający „wniosek” i słowa kluczowe | 16:00 |
| **K3** | Mikołaj | **Analiza**: `llm.py` (z K1 jest klient `/v1` → **lokalna** Ollama; Eden AI dochodzi w K3.1 (D9), wymuszony JSON wg `FormAnalysis.model_json_schema()`, błędy → `LLMUnavailable`; zostaje `LLM_FIXTURE`) + `analysis.py` (prompt z zasadami D8 i `SZABLONY_SEKCJI.md` rozdz. 6, w tym decyzje `applicant` z papieru – P1.2a; wynik niezgodny z `FormAnalysis.model_validate` → ponowienie z komunikatem walidatora, potem `LLMUnavailable`) | test z fixture; ręcznie: tekst nadpłaty → `FormAnalysis` waliduje się | 17:00 |

### Potem (Marcin, gdy M1.1 gotowe)

| Kod | Zadanie | Gotowe, gdy | Do |
|---|---|---|---|
| **M1.2** | JWT (`auth.py`, PyJWT): `JWT_ENABLED`, `JWT_SECRET`, `JWT_ALGORITHM`; 401 gdy brak/zły token; skrypt `python -m app.auth token` do wygenerowania tokenu. Przed startem lider dopisuje 401 do `SPEC.md` (D2) | `test_auth.py` | 15:00 |
| **M1.3** | Docker zgodny z pkt 5: `python:3.14.x-slim` (jawna wersja), użytkownik `app` bez roota, tesseract + `tesseract-ocr-pol` z apt, tylko port 8000; web: nginx bez roota na 8080 | `docker compose build` OK; `docker compose exec api whoami` → `app` | 16:00 |
| **M1.4** | **Sklejenie**: `main.py` woła `validate_upload → extract → analyze → build_form → lint`; błędy → 400/413/415/503, inne wyjątki → 500 (401 dopiero z M1.2) | `test_api.py` z `LLM_FIXTURE`: PDF → JSON, linter 0 błędów; jeden plik → jeden JSON (D10); suma limitów czasu mieści się w budżecie D11; brak internetu przy `edenai` kończy się szybkim 503, bez czekania na pełny limit (D12) | 17:30 |
| **M1.5** | **Model w compose**: serwis `ollama` (`ollama/ollama:<jawna wersja>`), wolumen z modelem, `scripts/pull_model.sh`, `LLM_BASE_URL=http://ollama:11434/v1` | `docker compose up` + `curl` na plik z folderu 3 → JSON; czas według D11 (około 180 s, granica 200 s), mierzony po M1.4 | 18:30 |
| **M1.6** | README: build, uruchomienie, tabela konfiguracji, REST API z przykładami `curl` i kodami błędów | ktoś spoza backendu uruchamia z README | 19:30 |

### Po decyzjach D9–D11 (sob. wieczór): Eden AI obok Ollamy

Kolejność: K3 (PR #11) na `main` → M1.7 → K3.1 → M1.4. Nazwa pola `Settings.llm_provider` jest ustalona tutaj, więc M1.7 i K3.1 mogą powstawać równolegle; K3.1 wchodzi na `main` po M1.7.

| Kod | Osoba | Zadanie | Gotowe, gdy |
|---|---|---|---|
| **M1.7** | Marcin | **Konfiguracja dostawcy modelu** (D9): `config.py` – `LLM_PROVIDER` (`ollama` domyślnie albo `edenai`; inna wartość zatrzymuje start), przy `edenai` tylko host Eden AI, wymagany klucz i `LLM_MODEL` wyłącznie z listy modeli otwartych (D9 pkt 7), budżet kontekstu z konfiguracji (`LLM_CONTEXT_TOKENS`, prośba z K3). `env.example` – nowe zmienne, komentarz o D9, bez klucza. `docker-compose.yml` – zmienne w `api.environment`; domyślny adres `http://ollama:11434/v1` nie może trafić do dostawcy `edenai`; `api` zachowuje wyjście do internetu. README (z M1.6): oba tryby i informacja, że przy `edenai` treść pliku idzie do Eden AI | `test_config.py` i `test_docker.py`: wartość domyślna `ollama`, zła wartość, `edenai` bez klucza, z obcym hostem albo z modelem spoza listy zatrzymują start z nazwą zmiennej; każda zmienna z `env.example` jest w compose; `gate.sh api -rs` zielone |
| **K3.1** | Mikołaj | **Adapter Eden AI z zachowaniem Ollamy** (D9), model docelowy Qwen3.5-9B: `llm.py` – wybór po `settings.llm_provider`, wspólny `ChatResult`, błędy → `LLMUnavailable`, klucz nigdy w logu ani w komunikacie błędu, ścieżka Ollamy i `LLM_FIXTURE` bez zmian zachowania. `analysis.py` – budżet kontekstu i liczba prób zależne od dostawcy (dziś stałe `CONTEXT_TOKENS = 16384` i `MAX_ATTEMPTS = 2` pod Ollamę), łączny czas analizy pod D11. `scripts/bench_model.py` – pomiar Eden AI uruchamiany przez człowieka (sonda `ollama_version` tylko dla Ollamy, folder 1 nadal odrzucany) | testy bez sieci (atrapa transportu) dla obu dostawców: adres, nagłówek, treść zapytania, błędy → 503; dotychczasowe testy Ollamy przechodzą bez zmian; `gate.sh api -rs` zielone. Pomiar człowieka z kluczem: formularze 5 i 9 przez Eden AI na Qwen3.5-9B → poprawny `FormAnalysis`, czas całego procesu wobec D11, wynik i wybrana trasa w `DECISIONS.md` |

Sprawdzone 2026-11-21 bez klucza (dokumentacja i publiczny katalog Eden AI, szczegóły w D9 pkt 8):
- endpoint zgodny z OpenAI: `POST https://api.edenai.run/v3/chat/completions`, model w postaci `dostawca/model`;
- Qwen3.5-9B jest w katalogu pod ośmioma identyfikatorami; kandydaci: `ovhcloud/Qwen3.5-9B` i `ionos/Qwen/Qwen3.5-9B` (UE, obraz na wejściu, bez daty wycofania);
- każda trasa deklaruje wymuszony schemat odpowiedzi i kontekst 262 144 tokeny, więc foldery 8 i 9 mieszczą się bez dzielenia na fragmenty.

Do potwierdzenia zapytaniem na żywo (człowiek z kluczem): czy trasa przyjmuje `reasoning_effort`, jak wyłączyć myślenie (w Qwen3.5 domyślnie włączone), czy `response_format: json_schema` z `strict` działa ze schematem `FormAnalysis` i ile trwa odpowiedź.

Klucz Eden AI ma tylko człowiek (D9 pkt 3 i 4, rozdz. 6 pkt 7). Agent pisze adapter i testy na atrapie transportu, a pomiar na żywo zostawia człowiekowi.

### Po M1 (wieczór i noc)

| Kod | Osoba | Zadanie |
|---|---|---|
| E1 | Paweł | `python -m app.eval`: JSON-y dla folderów 2–4, 6–9 + raport zgodności ze wzorcami 1 i 5 dla 8 formatów (`docs/ZESTAW_TESTOWY.md`). Jeden plik → jeden JSON, także folder 9 (D10). Raport podaje czas całego procesu na plik wobec D11, pola wyniku bez odpowiednika we wzorcu (precision; D10 pkt 3), użyty model i dostawcę oraz nazwy słowników spoza pliku COI (D14) |
| D1 | Marcin | `docs/ARCHITEKTURA.md` – **część minimum zadania** (moduły, przepływ, kontrakty, decyzje, koszt, uruchomienie on-prem; dwa tryby modelu i dane wysyłane do Eden AI, D9) |
| Q1 | Mikołaj | jakość AI: prompt strojony na nadpłacie, sprawdzany na numerze porządkowym (zbiór kontrolny – nie wklejamy go do promptu); formularz 9 (3 wnioski w 1) jako jeden JSON z wariantami w polach wyboru i warunkach SHOW; kontrola pól bez podstawy w papierze (D10) |
| F1 | Paweł | **prosty front**: jedna strona – wybór pliku, „Analizuj formularz”, komunikat błędu (`role="alert"`), „Pokaż JSON”, „Pobierz JSON” (kroki 1–3, 7, 8 z SPEC) |
| F2 | Paweł | podgląd eUsługi z jsonatą i walidatorami (kroki 4–6) – tylko jeśli F1 i E1 gotowe |

**Draft w systemie HackNation do 20:00** (nazwa, zespół, repo, stolik, opis) – Marcin wysyła o 19:30.

---

## 4. Model: lokalny (domyślny) i Eden AI (wyjątek COI)

| | **Qwen3.5-4B** (`qwen3.5:4b`) | **Bielik-4.5B-v3.0-Instruct** (`SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0`) |
|---|---|---|
| Rozmiar w Ollamie | 3,4 GB (Q4_K_M) | 5,1 GB (Q8_0) |
| Licencja | Apache-2.0 | Apache-2.0 + Terms of Use SpeakLeash |
| Polski | dobry | **najlepszy w tej klasie** (trenowany na polszczyźnie) |
| Obraz na wejściu | **tak** (może czytać skany zamiast OCR) | nie |
| Uwaga | domyślnie „myśli” przed odpowiedzią → **wyłączyć** (`reasoning_effort: "none"`; `think` na `/v1` nie działa), inaczej wolno | starszy (2025), oficjalnie tylko Q8_0/FP16 w Ollamie |

**Decyzja zespołu (12:35): Qwen3.5-4B** – zapisane w `SPEC.md`, rozdz. „Model”. Pomiar K1 tylko potwierdza, że działa (czas, poprawny JSON); Bielik zostaje zapasem.
Dawne kryteria wyboru (dla zapasu): Kryteria w tej kolejności: (1) poprawny `FormAnalysis` z wymuszonym JSON, (2) jakość polskich etykiet, (3) czas < 60 s na formularz na CPU.
Domyślnie stawiamy na **Qwen3.5-4B** (mniejszy, czyta obrazy, dobry w strukturze), **Bielik jako alternatywa jednym `LLM_MODEL`** – to też argument na slajd „model wymienny, działa on-prem, koszt ~0”.
Kryterium „< 60 s na CPU” zastąpił cel D11: około 180 s na cały proces, granica orientacyjna 200 s. Lokalny Qwen na samym CPU go nie spełnia (K1: 238–344 s na jedną próbę).

**Eden AI (D9).** COI dopuściło Eden AI udostępnione zespołowi na to zadanie. To jedyne zewnętrzne API w produkcie: innych nie używamy, także chmury Ollamy (`OLLAMA_NO_CLOUD=1` zostaje). Claude/Gemini służą tylko do pisania kodu.
- Ollama zostaje wartością domyślną i działa bez klucza. Eden AI włącza człowiek: `LLM_PROVIDER=edenai` (M1.7, K3.1).
- Przez Eden AI idą tylko modele otwarte, których wagi da się wdrożyć samodzielnie. Modele zamknięte są zakazane, choć Eden AI je udostępnia (D9 pkt 7).
- Model docelowy: Qwen3.5-9B (Apache-2.0, `Qwen/Qwen3.5-9B` na Hugging Face, lokalnie `qwen3.5:9b`). Trasę w Eden AI wybiera lider po pomiarze z K3.1. Dziś brak pomiaru czasu i jakości.
- Obrona: x86 bez dedykowanego GPU, RAM i internet niepotwierdzone (D12). Eden AI wymaga internetu, Ollama działa bez niego. Lokalnie zmierzony jest tylko 4B; 9B potrzebuje około dwa razy więcej pamięci na sam plik modelu.
- Do Eden AI idzie treść wczytanego pliku, czyli puste formularze z materiałów COI. Folder 1 zostaje poza promptami (D5).
- Testy, e2e i agenci nie wołają Eden AI.

---

## 5. Konfiguracja (zmienne środowiskowe – Marcin w `config.py` i `env.example`)

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `MAX_FILE_SIZE_MB` | `10` | limit rozmiaru |
| `JWT_ENABLED` | `false` | wymóg tokenu |
| `JWT_SECRET` | – | tylko w runtime |
| `JWT_ALGORITHM` | `HS256` | |
| `LLM_PROVIDER` | `ollama` | `ollama` albo `edenai` (D9). **Od M1.7** – dziś tej zmiennej nie ma w `config.py` |
| `LLM_BASE_URL` | `http://ollama:11434/v1` (lokalnie: `http://localhost:11434/v1`) | **lokalny** serwer modelu; przy `edenai` tylko host Eden AI (M1.7) |
| `LLM_MODEL` | `qwen3.5:4b` | przy `edenai` trasa Qwen3.5-9B wybrana po pomiarze K3.1, tylko model otwarty (D9 pkt 7 i 8) |
| `LLM_API_KEY` | `ollama` | Ollama go ignoruje; przy `edenai` klucz Eden AI, podaje go tylko człowiek (D9) |
| `LLM_TIMEOUT_S` | `120` | po przekroczeniu 503; wartość pod budżet D11 ustali pomiar (K3.1, M1.4) |
| `LLM_CONTEXT_TOKENS` | – | budżet kontekstu analizy; **od M1.7** (prośba z K3), dziś stała w `analysis.py` na gałęzi K3 |
| `LLM_FIXTURE` | – | ścieżka do `fields.json`; testy bez modelu |
| `OCR_LANG` | `pol` | |
| `ADD_VALIDATORS` | `true` | walidatory REQUIRED/PESEL/… (wzorce COI mają puste) |

---

## 6. Zasady pracy

1. Każde zadanie = jeden `/hn-krok` (agent: przeczytaj `.claude/skills/hn-krok/SKILL.md`): plan ≤10 linii w `PROGRESS.api.md` → kod + test → `bash scripts/gate.sh api` → stop → człowiek commituje.
2. Gałęzie: `marcin/…`, `mikolaj/…`, `pawel/…`; merge do `main` tylko z zieloną bramką. `git pull --rebase` przed pushem.
3. Testy nigdy nie wołają modelu ani Eden AI (`LLM_FIXTURE` albo atrapa transportu).
4. Materiały COI: rozpakuj zip tak, żeby foldery `1. …` – `9. …` leżały bezpośrednio w `hacknation-2026/materialy/` (poza gitem, `materialy/` jest w `.gitignore`); inaczej testy ze wzorcami są po cichu pomijane. Oryginalnych plików COI nie commitujemy, także jako fixture’ów (D5).
5. Zabronione zależności: PyMuPDF (AGPL), pdf2image/poppler (GPL), Ghostscript/ocrmypdf (AGPL), antiword (GPL). LibreOffice: mentor COI uznał go za dopuszczalny kierunek (2026-11-21). Każda konkretna zależność (pakiet apt, obraz, biblioteka) przed dodaniem wymaga sprawdzenia licencji i linii w `DECISIONS.md`. `AGENTS.md` dopuszcza MIT, Apache i BSD, a listę trzech wyjątków MPL-2.0 zamyka.
6. Co 2 h krótki sync (2 min): co gotowe, co blokuje.
7. Klucz Eden AI (D9): leży poza repozytorium i poza katalogami, w których pracują agenci. Agent go nie czyta, nie prosi o niego i nie wysyła zapytań do Eden AI. Zapytania na żywo (demo, pomiar, eval) uruchamia człowiek. Klucz nie trafia do `env.example`, logów, raportów, zrzutów ekranu ani promptów. Inne zewnętrzne API są zabronione. Przez Eden AI wolno wołać tylko modele otwarte.
8. Słowniki i walidatory: nazwy słowników bierzemy z pliku słowników COI, nie z formularzy przykładowych, i nie wymyślamy nowych (D14). Walidator dodajemy, gdy wynika z pola (D13).

---

## 7. Różnice względem `SPEC.md` (świadome)

- Priorytet: M1 (API) przed Must 3 i 4 (front).
- Dokumentacja architektury (D1) – część minimum zadania.
- Docker: Python 3.14 i użytkownik bez roota (wymóg pkt 5).
- Kodu 422 nie używamy: nieczytelny plik i błąd walidacji żądania to 400 (D2, już w `SPEC.md`).
- Eden AI (D9) jest w dokumentach, ale jeszcze nie w kodzie: do K3.1 i M1.7 `llm.py` woła tylko Ollamę, a `config.py` nie zna `LLM_PROVIDER`.
- Nieaktualne po D9 i D11, do poprawy przez właścicieli: komentarz „The model runs locally only” w `env.example` (Marcin, M1.7), „lokalny model (żadnych API…)” w `docs/BRIEF_ZESPOL.md` rozdz. 1 i miara M7 „< 60 s na plik” w `docs/ZESTAW_TESTOWY.md` (lider).
- Otwarte po odpowiedziach mentorów: ilość RAM-u i stabilność internetu na obronie (D12) oraz słownik adresu zamieszkania (D14). Do odpowiedzi `TERYT_4G_DOWODOWY` w generatorze zostaje.
- Strony alternatywne: link `flow` w formacie COI nie ma warunku, więc wariant zapisujemy warunkami SHOW na sekcjach i polach (P1.4, D10).

---

## 8. Gotowe prompty dla agentów (skopiuj do Claude Code / Antigravity)

**Marcin – M1.1**
```
Przeczytaj DELEGACJA.md (rozdz. 0–3, zadanie M1.1), AGENTS.md i SPEC.md (API contract).
Zrób zadanie M1.1: config.py, files.py, POST /api/forms zwracający na razie stały szkielet JSON
(rozdz. 3, „Zakres”), python-multipart w requirements + linia w DECISIONS.md.
Wyjątki z app/errors.py mają argumenty tylko nazwane: UploadError(detail="...", status_code=415).
Błąd walidacji żądania FastAPI zamień na 400, każdy inny wyjątek na 500; detail zawsze tekstem.
Testy w test_files.py i test_api.py wg kolumny „Gotowe, gdy”. Pliki w pamięci, bez zapisu na dysk.
Nie ruszaj plików innych osób. Uruchom bash scripts/gate.sh api, wklej wynik, zatrzymaj się z komunikatem commita.
```

**Paweł – P0 + P1**
```
Przeczytaj DELEGACJA.md (rozdz. 2 i zadania P0, P1), SZABLONY_SEKCJI.md i oba wzorce COI z materialy/1. i materialy/5.
P0 jest gotowe: backend/app/models.py i errors.py importuj, nie zmieniaj bez decyzji lidera.
P1: backend/app/generator/ – build_form(FormAnalysis) -> dict w formacie COI: wszystkie klucze pola zawsze obecne,
repeatingSectionGrid, cols 3, y/rows/questionOrder wg SZABLONY rozdz. 0, sekcje szablonowe wg rozdz. 3–4,
strony przedmiotu z FormAnalysis, jsonata w formacie COI, flow.links.
Test: z fields.json techName sekcji i pól na stronach szablonowych zgodne z wzorcem z folderu 5 (fixture coi_working_reference).
Uruchom bash scripts/gate.sh api, wklej wynik, zatrzymaj się z komunikatem commita.
```

**Mikołaj – K1 + K2**
```
Przeczytaj DELEGACJA.md (rozdz. 2, 4 i zadania K1, K2).
K1: scripts/bench_model.py – dla qwen3.5:4b (think wyłączone) i SpeakLeash/bielik-4.5b-v3.0-instruct:Q8_0 w lokalnej Ollamie
wyślij tekst wniosku z materialy/5. i materialy/1. z wymuszonym JSON wg FormAnalysis.model_json_schema();
zmierz czas i czy wynik waliduje się Pydantikiem. Wynik i decyzja → DECISIONS.md.
K2: backend/app/extract/ – extract(data, ext) -> ExtractedDocument dla 8 formatów (rozdz. 3, K2), tylko licencje MIT/Apache/BSD.
Błędy: ExtractionError(detail="...") z argumentem nazwanym. images przytnij do 20 sztuk i 40 MB, zanim utworzysz ExtractedDocument.
Test: dla folderów 1 i 5 każdy format daje tekst ze słowami kluczowymi.
Uruchom bash scripts/gate.sh api, wklej wynik, zatrzymaj się z komunikatem commita.
```

**Marcin – M1.7**
```
Przeczytaj DELEGACJA.md (rozdz. 3 „Po decyzjach D9–D11”, 4, 5, 6 pkt 7) i DECISIONS.md (D9, D11).
M1.7: config.py – LLM_PROVIDER (ollama domyślnie albo edenai; inna wartość zatrzymuje start API),
przy edenai tylko host Eden AI, wymagany klucz i model z listy modeli otwartych (D9 pkt 7), LLM_CONTEXT_TOKENS. Pole nazywa się Settings.llm_provider.
env.example: nowe zmienne i komentarz o D9, bez klucza. docker-compose.yml: zmienne w api.environment;
domyślny adres ollama nie może trafić do dostawcy edenai.
Nie czytaj klucza Eden AI i nie wysyłaj zapytań do Eden AI. Testy: test_config.py, test_docker.py.
Uruchom bash scripts/gate.sh api -rs, wklej wynik, zatrzymaj się z komunikatem commita.
```

**Mikołaj – K3.1**
```
Przeczytaj DELEGACJA.md (rozdz. 3 „Po decyzjach D9–D11”, 4, 6 pkt 7) i DECISIONS.md (D9, D10, D11).
K3.1 (po K3 na main, model docelowy Qwen3.5-9B – D9 pkt 8): llm.py – adapter Eden AI obok Ollamy, wybór po settings.llm_provider, wspólny ChatResult,
błędy → LLMUnavailable, klucz nigdy w logu. Ścieżka Ollamy i LLM_FIXTURE bez zmian zachowania.
analysis.py – budżet kontekstu i liczba prób zależne od dostawcy, łączny czas pod D11 (około 180 s, granica 200 s).
Testy tylko na atrapie transportu, dla obu dostawców. Nie czytaj klucza Eden AI i nie wysyłaj zapytań do Eden AI:
pomiar na żywo zrobi człowiek. Endpoint i identyfikatory modelu są w DELEGACJA.md rozdz. 3; nie zgaduj innych.
Uruchom bash scripts/gate.sh api -rs, wklej wynik, zatrzymaj się z komunikatem commita.
```
