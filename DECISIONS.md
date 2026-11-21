# DECISIONS

One line per choice: what, why, licence. Product dependencies: MIT, Apache or BSD only.

## Template (prepared before the event, 2026-11-20)

| What                          | Why                               | Licence    |
| ----------------------------- | --------------------------------- | ---------- |
| react, react-dom 19.3         | UI                                | MIT        |
| vite 8, @vitejs/plugin-react  | dev server and build              | MIT        |
| tailwindcss 4, @tailwindcss/vite | styling with tokens in index.css | MIT       |
| typescript 7                  | type check in the gate            | Apache-2.0 |
| oxlint                        | lint in the gate                  | MIT        |
| vitest 5                      | unit tests                        | MIT        |
| @playwright/test 1.65         | e2e tests, test-only              | Apache-2.0 |
| @axe-core/playwright 4.14     | accessibility checks, test-only   | MPL-2.0    |
| fastapi 0.165, uvicorn 0.54   | API                               | MIT, BSD   |
| pytest, httpx, ruff           | backend tests and lint, test-only | MIT, BSD   |

Three MPL-2.0 packages are installed, none of them modified and none of them our source:

| Package                          | Comes from                    | Role                         |
| -------------------------------- | ----------------------------- | ---------------------------- |
| @axe-core/playwright, axe-core   | direct, test-only             | accessibility checks in e2e  |
| lightningcss                     | vite 8 and @tailwindcss/vite  | CSS build tool, not shipped  |
| certifi                          | httpx (httpcore)              | CA certificate bundle        |

Every other installed frontend package is MIT, Apache-2.0, BSD, ISC, 0BSD or BlueOak. If the
task rules require every dependency to be MIT, Apache or BSD, ask a mentor before submission.
Do not add a fourth exception.

Claude Code version used: (write `claude --version` here on the day)

## Event: web

(frontend dependencies and choices go here)

## Event: api

Decyzje lidera po recenzji P0 (2026-11-21). Kod: `backend/app/errors.py`, `backend/app/models.py`.

- **D1 – wyjątki.** `AppError(*, detail, status_code=None)`: argumenty tylko nazwane, `detail` to niepusty tekst, kod to liczba całkowita 400–599. `UploadError` przyjmuje 400, 413 i 415, `ExtractionError` zawsze 400, `LLMUnavailable` zawsze 503. Błędy przechodzą przez `pickle` i `copy`. Dlaczego: na `main` opisana była kolejność `(status, detail)` i pomyłka przechodziła bez błędu.
- **D2 – HTTP.** `POST /api/forms` zwraca 400, 413, 415, 503 i 500. Bez 422: błąd walidacji żądania FastAPI i nieczytelny plik to 400. `detail` jest zawsze tekstem po polsku. 401 wejdzie do `SPEC.md` razem z zadaniem M1.2 (JWT), nie wcześniej.
- **D3 – obrazy.** `ExtractedDocument.images` jest wewnętrzne: pomijane w `model_dump`, w JSON-ie i w `repr`. Limit to 20 obrazów i 40 MB łącznie (4 × limit pliku); przycina je `extract`. Błąd walidacji nie cytuje treści dokumentu. `source_format` to zamknięty zbiór: pdf, doc, docx, ods, xlsx, jpg, png.
- **D4 – analiza.** `FormAnalysis.model_validate` odrzuca puste teksty, nieznane klucze, pole wyboru bez opcji, opcje przy innym typie, powtórzone opcje oraz `show_if`, które wskazuje brak pola, brak opcji, samo siebie albo etykietę powtórzoną na stronie. Etykiety nie muszą być unikalne. Format `show_if` zostaje. K3 po ponowieniach zamienia `ValidationError` na `LLMUnavailable`.
- **D5 – zbiór kontrolny i materiały COI.** Folder 1 służy tylko niezależnej ocenie: nie trafia do opisów schematu, promptów ani fixture’ów. Oryginalnych plików COI nie ma w drzewie repozytorium. Testy czytają je z `materialy/` i są pomijane, gdy ich brak, więc przed mergem bramka idzie z `-rs` i ma 0 pominiętych. `fields.json` to nasz opis wniosku z folderu 5 i zostaje. Commit `9fe7f2e` z kopiami obu wzorców jest już na `origin/pawel/p0-models`: P0 wchodzi na `main` jako squash, a zdalną gałąź usuwamy po mergu. Prawo do publikacji wzorców potwierdza mentor.
- **D6 – testy P0.** Regresja obejmuje wyjątki, modele, serializację obrazów, warunki w `fields.json` i izolację folderu 1. Każdy test był widziany na czerwono po zepsuciu kodu (65 mutacji). JSONata i `flow.links` należą do P2.

## Event: whole project

- **D7 – odpowiedzialność.** Lider rozstrzyga kontrakty, zakres i integrację. `SPEC.md` określa kontrakty, `DECISIONS.md` zapisuje decyzje, `DELEGACJA.md` wyznacza wykonawców, a `PROGRESS*.md` rejestruje postęp i wyniki bramek.
