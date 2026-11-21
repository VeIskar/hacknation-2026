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

Krok P2: `lint.check(form)` dla M1.4 i E1 (schemat COI, Reguły techniczne, JSONata).

- `backend/tests/test_lint.py`: oba wzorce, wszystkie fixture’y generatora, warianty, uszkodzenia i odporność. Najpierw czerwony wynik.
- `backend/app/lint.py`: typy, układ, komponenty, stany, unikalność, przepływ w obie strony i odwołania JSONata. Tylko biblioteka standardowa.
- `DECISIONS.md`: jeden wpis z tolerancjami COI i rozstrzygnięciami z Fazy 0.
- Dowód: testy i mutacje dla każdej reguły, przegląd diffu, `bash scripts/gate.sh api -rs`, 0 pominiętych.

## Requests

(one line per change you need from another area: who asks, what, why)

- lider → Marcin (M1.1, `main.py`): `AppError` → jego kod i `detail`; błąd walidacji żądania FastAPI → 400; inny wyjątek → 500; `detail` zawsze tekstem (D2). Wyjątki wołaj nazwanymi argumentami (D1).
- lider → Marcin (M1.1): endpoint zwraca na razie stały szkielet JSON, bo wzorców COI nie ma już w `backend/tests/fixtures/` (D5).
- lider → Mikołaj (K3, `analysis.py`): `ValidationError` z `FormAnalysis.model_validate` po ponowieniach zamień na `LLMUnavailable` (D4).
- lider → Mikołaj (K2, `extract`): przytnij `images` do 20 sztuk i 40 MB przed utworzeniem `ExtractedDocument` i dopisz ostrzeżenie (D3).

## Log

(one line per step: done / next / blocker)

- P0 `9fe7f2e`: done modele, wyjątki, fixture; recenzja lidera: CHANGES REQUIRED (5 ustaleń).
- P0.1 (poprawki D1–D6 na `9fe7f2e`): done `bash scripts/gate.sh api -rs` → `73 passed`, 0 pominiętych, `GATE: PASS (api)`; 65/65 mutacji wykrytych; niezależna recenzja: uwagi naniesione / next squash na `main` i usunięcie `origin/pawel/p0-models`, potem M1.1, K1–K3, P1 / blocker brak.
- M1.1: done na `c53fd46`, `gate.sh api -rs` → 155 passed, 0 pominiętych; prawdziwe pliki z folderów 2–9 przechodzą (.DOC będący DOCX → `docx`, .JPE → `jpg`) / next M1.2 JWT (po dopisaniu 401 do SPEC) / blocker brak.
- M1.1 recenzja (`aaa78da`): done uszkodzony .ods → 415 zamiast 500, pusta część pliku → 400 „Wybierz plik formularza.” (testy czerwone przed poprawką); `gate.sh api -rs` → 157 passed, 0 pominiętych / later: test limitu strumieniowego, walidacja `MAX_FILE_SIZE_MB` przy starcie, kopie pliku w pamięci (REVIEW.md) / next M1.2 JWT (po dopisaniu 401 do SPEC) albo M1.3 Docker / blocker brak.
- P1 (generator `build_form`): done `bash scripts/gate.sh api -rs` → `107 passed`, 0 pominiętych, `GATE: PASS (api)`; 34 testy w `test_generator.py`, 44/44 mutacji generatora wykrytych / next P2 linter / blocker brak.
- P1 poprawki po recenzjach (czasownik S2, zgoda bez linku przy pustym adresie, REQUIRED w S10, UUID5 z kanonicznego JSON-a, NFC w tytułach, slug i limit 60 znaków, mocniejsze testy, wyciek we wszystkich fixtures): done `bash scripts/gate.sh api -rs` → `124 passed`, 0 pominiętych, `GATE: PASS (api)`; 70/70 mutacji generatora wykrytych + test wycieku czerwony po wstrzyknięciu tekstu z folderu 1 / next P2 linter / blocker brak.
- P2 (linter `lint.check`): done oba wzorce COI i 4 wyniki generatora → `[]`, 119 testów lintera, 70/70 mutacji wykrytych; `bash scripts/gate.sh api -rs` → `327 passed`, 0 pominiętych, 1 ostrzeżenie Starlette, `GATE: PASS (api)` / next M1.4 i E1 mogą użyć `lint.check` / blocker brak.
- P2 po recenzji: done `isinstance` z wyłączeniem bool jako liczby, surowe znaki i obsługa błędu dekodowania JSONata, 20 nowych przypadków widzianych na czerwono, 25/25 mutacji recenzji i 70/70 mutacji P2; `bash scripts/gate.sh api -rs` → `347 passed`, 0 pominiętych, 1 ostrzeżenie Starlette, `GATE: PASS (api)` / next M1.4 i E1 / blocker brak.
