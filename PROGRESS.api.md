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

Krok M1.1-fix (Marcin, CHANGES REQUIRED od Pawła, gałąź `marcin/m1.1-fix`): `docker-compose.yml` przekazuje
do api wszystkie zmienne z `env.example` (`${NAZWA:-}`); `config.py` odrzuca `MAX_FILE_SIZE_MB` ≤ 0 lub
niecałkowite i `LLM_TIMEOUT_S` ≤ 0, API nie startuje; `files.py`: `mimetype` ODS dokładnie równy, błędy
metadanych ZIP → 415, `Content-Type` bez względu na wielkość liter. Testy: `test_config.py` (nowy),
`test_files.py`, `test_api.py` (też limit strumieniowy bez Content-Length, przez ASGI).

## Requests

(one line per change you need from another area: who asks, what, why)

- lider → Marcin (M1.1, `main.py`): `AppError` → jego kod i `detail`; błąd walidacji żądania FastAPI → 400; inny wyjątek → 500; `detail` zawsze tekstem (D2). Wyjątki wołaj nazwanymi argumentami (D1).
- lider → Marcin (M1.1): endpoint zwraca na razie stały szkielet JSON, bo wzorców COI nie ma już w `backend/tests/fixtures/` (D5).
- lider → Mikołaj (K3, `analysis.py`): `ValidationError` z `FormAnalysis.model_validate` po ponowieniach zamień na `LLMUnavailable` (D4).
- lider → Mikołaj (K2, `extract`): przytnij `images` do 20 sztuk i 40 MB przed utworzeniem `ExtractedDocument` i dopisz ostrzeżenie (D3).
- Marcin → lider (`SPEC.md`, Must 1 i „API contract”): dopisać wyjątek od zgodności typu z rozszerzeniem, np. „Plik `.doc`, który w środku jest DOCX, jest przyjmowany i czytany jak DOCX (tak są zapisane pliki `.DOC` z folderów 5 i 7). `.jpe` jest przyjmowane jak `.jpg` (plik `.JPE` w folderze 7).” Kod już tak działa (DECISIONS, M1.1); uwaga Pawła z recenzji M1.1.

## Log

(one line per step: done / next / blocker)

- P0 `9fe7f2e`: done modele, wyjątki, fixture; recenzja lidera: CHANGES REQUIRED (5 ustaleń).
- P0.1 (poprawki D1–D6 na `9fe7f2e`): done `bash scripts/gate.sh api -rs` → `73 passed`, 0 pominiętych, `GATE: PASS (api)`; 65/65 mutacji wykrytych; niezależna recenzja: uwagi naniesione / next squash na `main` i usunięcie `origin/pawel/p0-models`, potem M1.1, K1–K3, P1 / blocker brak.
- M1.1: done na `c53fd46`, `gate.sh api -rs` → 155 passed, 0 pominiętych; prawdziwe pliki z folderów 2–9 przechodzą (.DOC będący DOCX → `docx`, .JPE → `jpg`) / next M1.2 JWT (po dopisaniu 401 do SPEC) / blocker brak.
- M1.1 recenzja (`aaa78da`): done uszkodzony .ods → 415 zamiast 500, pusta część pliku → 400 „Wybierz plik formularza.” (testy czerwone przed poprawką); `gate.sh api -rs` → 157 passed, 0 pominiętych / later: test limitu strumieniowego, walidacja `MAX_FILE_SIZE_MB` przy starcie, kopie pliku w pamięci (REVIEW.md) / next M1.2 JWT (po dopisaniu 401 do SPEC) albo M1.3 Docker / blocker brak.
- M1.1-fix: done 4 ustalenia Pawła (limit z .env w compose + walidacja, ODS `mimetype`, błędy ZIP → 415, wielkość liter `Content-Type`) + test limitu strumieniowego; nowe testy czerwone przed poprawką, test strumieniowy czerwony po usunięciu kontroli w pętli; fuzz 200 000 uszkodzonych ZIP-ów: 0 wyjątków poza `UploadError`; `gate.sh api -rs` → 177 passed, 0 pominiętych / next zapis w SPEC (Request do lidera), potem M1.2 / blocker brak.
