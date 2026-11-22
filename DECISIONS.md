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

F1 (web):

| What                                   | Why                                                                                  | Licence    |
| -------------------------------------- | ------------------------------------------------------------------------------------ | ---------- |
| pdfjs-dist 6.5.438                     | pierwsza strona wczytanego PDF-a w przeglądarce; plik nie jest wysyłany drugi raz     | Apache-2.0 |
| @napi-rs/canvas (opcjonalna, z pdfjs-dist) | potrzebna pdfjs tylko w Node; w przeglądarce nieużywana i nie trafia do paczki   | MIT        |
| Atkinson Hyperlegible Next 2.001 (plik kroju) | krój warsztatu, projektowany dla osób słabowidzących; `google/fonts`, `ofl/atkinsonhyperlegiblenext` | OFL-1.1 (D15) |
| Brygada 1918 3.006 (plik kroju)        | tylko tytuły (h1, nazwa wniosku); `google/fonts`, `ofl/brygada1918`                  | OFL-1.1 (D15) |

- Kroje leżą bez zmian w `frontend/src/fonts/`, każdy z własnym `OFL.txt`. Bez CDN i bez subsetowania (D15).
- Kierunek warsztatu „Zakreślacz” (wybór lidera, 2026-11-22): żółty `#FFD60A` tylko jako wypełnienie
  zakreślenia pod ciemnym tekstem. Nigdy jako obrys fokusu, przycisk ani pasy. Obrys fokusu jest ciemny.
- Podgląd pierwszej strony: PDF przez pdfjs-dist, JPG i PNG natywnie, inne formaty dostają jedno zdanie.

F2 (web):

| What          | Why                                                                                   | Licence |
| ------------- | ------------------------------------------------------------------------------------- | ------- |
| jsonata 2.2.2 | warunki SHOW z JSON-a COI liczone w podglądzie tym samym językiem zapytań, bez własnego parsera | MIT     |

F2.5 (web):

- Kierunek „Jasny urząd” (decyzja lidera, 2026-11-22, DESIGN.md) zastępuje „Zakreślacz”. Żółtego nie ma
  w interfejsie, dopóki nie pokazujemy źródeł na papierze (F4).
- Jeden krój: Atkinson Hyperlegible Next, także w podglądzie eUsługi. Brygada 1918 nie jest używana;
  plik zostaje w `frontend/src/fonts/brygada/` do decyzji o usunięciu i nie trafia do paczki.
- Dane `MLPZ.*` w podglądzie mają podpowiedź „Przykładowe dane z rejestru”: podgląd nie łączy się z rejestrem.
- `look.mjs` sprawdza folder 9 na JSON-ie zbudowanym przez generator z `analysis_form9.json`, bez modelu.

## Event: api

Decyzje lidera po recenzji P0 (2026-11-21). Kod: `backend/app/errors.py`, `backend/app/models.py`.

- **D1 – wyjątki.** `AppError(*, detail, status_code=None)`: argumenty tylko nazwane, `detail` to niepusty tekst, kod to liczba całkowita 400–599. `UploadError` przyjmuje 400, 413 i 415, `ExtractionError` zawsze 400, `LLMUnavailable` zawsze 503. Błędy przechodzą przez `pickle` i `copy`. Dlaczego: na `main` opisana była kolejność `(status, detail)` i pomyłka przechodziła bez błędu.
- **D2 – HTTP.** `POST /api/forms` zwraca 400, 413, 415, 503 i 500. Bez 422: błąd walidacji żądania FastAPI i nieczytelny plik to 400. `detail` jest zawsze tekstem po polsku. 401 wejdzie do `SPEC.md` razem z zadaniem M1.2 (JWT), nie wcześniej.
- **D3 – obrazy.** `ExtractedDocument.images` jest wewnętrzne: pomijane w `model_dump`, w JSON-ie i w `repr`. Limit to 20 obrazów i 40 MB łącznie (4 × limit pliku); przycina je `extract`. Błąd walidacji nie cytuje treści dokumentu. `source_format` to zamknięty zbiór: pdf, doc, docx, ods, xlsx, jpg, png.
- **D4 – analiza.** `FormAnalysis.model_validate` odrzuca puste teksty, nieznane klucze, pole wyboru bez opcji, opcje przy innym typie, powtórzone opcje oraz `show_if`, które wskazuje brak pola, brak opcji, samo siebie albo etykietę powtórzoną na stronie. Etykiety nie muszą być unikalne. Format `show_if` zostaje. K3 po ponowieniach zamienia `ValidationError` na `LLMUnavailable`.
- **D5 – zbiór kontrolny i materiały COI.** Folder 1 służy tylko niezależnej ocenie: nie trafia do opisów schematu, promptów ani fixture’ów. Oryginalnych plików COI nie ma w drzewie repozytorium. Testy czytają je z `materialy/` i są pomijane, gdy ich brak, więc przed mergem bramka idzie z `-rs` i ma 0 pominiętych. `fields.json` to nasz opis wniosku z folderu 5 i zostaje. Commit `9fe7f2e` z kopiami obu wzorców jest już na `origin/pawel/p0-models`: P0 wchodzi na `main` jako squash, a zdalną gałąź usuwamy po mergu. Prawo do publikacji wzorców potwierdza mentor.
- **D6 – testy P0.** Regresja obejmuje wyjątki, modele, serializację obrazów, warunki w `fields.json` i izolację folderu 1. Każdy test był widziany na czerwono po zepsuciu kodu (65 mutacji). JSONata i `flow.links` należą do P2.
- **P1 – generator** (`backend/app/generator/`, dopowiedzenia lidera do SZABLONY i poprawki po recenzji). PERSON: radio Swoim i Innej osoby, bez sekcji podmiotu. ENTITY: jedna opcja osoby prawnej, bez sekcji innej osoby. BOTH: jak wzorzec. Czasownik w etykietach S2 z pierwszego słowa tytułu (wniosek, zgłoszenie, deklaracja; inaczej „wnioskujesz”); techName S2 stałe. techName unikalne w formularzu, najwyżej 60 znaków (cięcie na `_`), szablon ma pierwszeństwo, kolizje dostają _2, _3. Strona przedmiotu o tytule strony standardowej dostaje „ wniosku”, powtórzenie „ (2)”; tytuły porównywane po NFC i casefold. Jsonata używa końcowych tytułów i techName; w literałach escapuje `"` i `\`, a apostrof w literale w apostrofach (tytuł strony) zapisuje sekwencją `\u0027`, bo JSONata nie zna `\'`. UUID5 ze stałej przestrzeni nazw i kanonicznego JSON-a analizy (`sort_keys`). `ADD_VALIDATORS = True` w `form.py`; pola tylko do odczytu z rejestru mają `validation: []`; radio opłaty skarbowej (S10) ma `REQUIRED` (Standardy COI). Zgoda bazowa bez linku, dopóki `PRIVACY_CLAUSE_URL` jest pusty. Oświadczenia to kolejne wymagane zgody. Tekst od modelu w HTML-u jest escapowany.

- **P2 – linter** (`backend/app/lint.py`). Kontrolujemy `repeatingSectionGrid` zgodnie z eksportami COI, dopuszczamy dodatkowe klucze, `defaultValue` jako tekst lub tablicę, pusty `validation: {}`, brak `states` i `options[].techName` oraz `TEXT_BLOCK` obok `INFO_SECTION` na `FINISH` (Reguły, ak. 12, wymieniają wyłącznie `INFO_SECTION`). Opis importu, ak. 71, określa `validation` jako „tablica stringów przyjmująca nazwy predefiniowanych walidacji”. Przyjmujemy dziewięć nazw z Reguł, pola informacyjne mają pustą konfigurację walidatorów. Opis importu, ak. 96–98, i schemat, w. 109–111, umieszczają `required` w `consentSectionConfig`. Reguły, ak. 575–582, i oba wzorce umieszczają flagę przy każdej zgodzie, więc tam jest wymagana. Na poziomie konfiguracji sprawdzamy jej typ, gdy występuje. `techName` sekcji i pól są unikalne w formularzu. Różne pola mogą używać tych samych identyfikatorów i nazw technicznych opcji. JSONata dopasowuje literał do `id` lub `name` opcji, a pole słownikowe pomija kontrolę wartości. Sprawdzamy osiągalność stron od pierwszej i drogę z każdej `MAIN` do `FINISH`. Odwołanie JSONata musi wskazywać pole wyboru, siatka wymaga `x/y/rows/cols`, strona wymaga niepustych `id` i `title`, pole niepustych `id` i `type`, link niepustego `id`, a lista `consents` co najmniej jednej zgody, przy czym `id` stron, pól (w tym sekcji) i linków należą do jednej przestrzeni, a typy sprawdzamy przez `isinstance` z wyłączeniem `bool` jako liczby.

- **P1.2a – kontrakt.** `FormAnalysis` wymaga jawnych `applicants` i `applicant: ApplicantData`. Decyzje MVP mają przesłanki w papierze i są niezależne od ekstraktora. Dane spoza szablonu trafiają do `applicant_extra_fields`, a reguły D4 dla `show_if` obowiązują także w tej liście. Tekst analizy naprawia samotne surogaty do U+FFFD przed walidacją. Dobór sekcji należy do P1.2b, detektor do P1.2c, a tryby rozszerzone do P1.3. Test D5 pomija dokładne słowo »regon« – nazwa walidatora z Reguł i wartość kontraktu, nie tekst z folderu 1.

- **P1.2b – generator.** `FormAnalysis.applicant` wyznacza sekcje wnioskodawcy, korespondencję, pola dodatkowe i kontakt, a S2 wyświetla tylko faktyczne wybory, co zastępuje GD2 z radiem o jednej opcji dla ENTITY.

- **P1.3a.** Pola `TEXT_FIELD` z analizy dostają walidator typu po `REQUIRED`, jeśli etykieta po NFC, casefold i usunięciu polskich znaków pasuje do dokładnie jednej kategorii na granicach słów (PESEL, NIP, REGON, ZIP_CODE, EMAIL, SERIAL_NUMBER_ID_CARD, EPUAP, ADE). Etykieta złożona → bez walidatora typu, jeśli po usunięciu dopasowanej frazy pozostaje separator, spójnik lub słowo innej danej. Dobór odbywa się bez modelu, a `ADD_VALIDATORS = False` czyści wszystkie walidatory.

- **P1.4.** Alternatywy i koniunkcje SHOW na polach i sekcjach przedmiotu, wcześniejsze źródła między stronami i wykrywanie cykli. F9 jest jednym formularzem z czterema warunkowymi miejscami dla podopiecznych.

- **P4.** Strażnik wyłącza decyzje wnioskodawcy bez przesłanki, usuwa wskazane duplikaty z ochroną źródeł `SHOW` i raportuje pozostałe braki oparcia. Kontrola walidatorów respektuje wyjątek P1 dla `readOnly`. Reguła `Kraje` obejmuje etykiety kraju na polach bez odwołań z `show_if` i `show_if_all`. Dotyczy `TEXT_FIELD` oraz `SELECT` i `RADIO` z co najmniej pięcioma opcjami bez znormalizowanych wartości „tak”, „nie”, „inny” i „inne”.

M1.1 (Marcin):

| What                    | Why                                                         | Licence    |
| ----------------------- | ----------------------------------------------------------- | ---------- |
| python-multipart 0.0.34 | Starlette's multipart parser needs it for `POST /api/forms` | Apache-2.0 |

M1.2 (Marcin):

| What          | Why                                             | Licence |
| ------------- | ----------------------------------------------- | ------- |
| PyJWT 2.15.1  | JWT na `POST /api/forms` (Treść pkt 5, SPEC 401) | MIT     |

- Tylko algorytmy HMAC (HS256/384/512) i wymagany `exp`: sekret jest wspólny, token nie żyje wiecznie.
  Sekret ma co najmniej 32/48/64 bajty (RFC 7518, 3.2); krótszy albo inny algorytm to 500 i wpis w logu.
- Token sprawdzamy przed odczytem pliku, więc bez tokenu serwer nie czyta treści żądania.

- Plik tylko w pamięci: treść żądania czytamy sami do `MAX_FILE_SIZE_MB` + 64 KB (potem 413), a parser
  dostaje bufor większy niż żądanie, więc nie powstaje plik tymczasowy (Treść pkt 5).
- `.jpe` przyjmujemy jako `jpg` (DELEGACJA rozdz. 2.2), bo folder 7 materiałów COI ma plik `.JPE`.
- `.doc`, który w środku jest DOCX, przechodzi, a `validate_upload` zwraca `docx`. Takie są pliki
  `.DOC` w folderach 5 i 7. `extract` dostaje więc format treści, nie samo rozszerzenie.
- Konfiguracja błędna (`MAX_FILE_SIZE_MB` ≤ 0 lub niecałkowite, `LLM_TIMEOUT_S` ≤ 0) zatrzymuje start
  API z nazwą zmiennej, zamiast dawać 413 lub 500 przy każdym pliku. Compose przekazuje każdą
  zmienną z `env.example` jako `${NAZWA:-}`: ta forma działa też w podman-compose.
- ODS: wpis `mimetype` musi być dokładnie równy typowi (bez końca linii i dopisków), jak w ODF 1.2.

K1 (Mikołaj):

| What                                  | Why                                                                 | Licence      |
| ------------------------------------- | ------------------------------------------------------------------- | ------------ |
| httpx 0.28.1 (już w `requirements.txt`) | teraz też w runtime: klient modelu w `llm.py`, atrapa transportu w testach | BSD-3-Clause |

- **K1 – myślenie.** Na `/v1/chat/completions` Ollama ignoruje `think: false`: 641 znaków myślenia i 250 tokenów, jak bez flagi. `reasoning_effort: "none"` daje 0 znaków i 3 tokeny. `llm.py` wysyła tylko `reasoning_effort` (zmierzone 2026-11-21, Ollama 0.40.15).
- **K1 – kontekst.** `/v1` nie ustawia `num_ctx`, a serwer domyślnie ma 4096 tokenów. Nadpłata z DOCX to 2034 tokeny promptu i 1088 odpowiedzi, skan JPG 3437 i 690. Serwer dostaje `OLLAMA_CONTEXT_LENGTH=16384`.
- **K1 – pomiar.** Warunki: `qwen3.5:4b` Q4_K_M, `ollama/ollama:0.40.15` w Dockerze, sam CPU (Core Ultra 7 255U, limit 6 GB), temperature 0, folder 5. Wyniki:
  DOCX, 3 przebiegi: JSON poprawny 3/3, `FormAnalysis.model_validate` 0/3, czas 238–344 s (mediana 318 s), odpowiedzi identyczne. Jedyny błąd: RADIO z `show_if` na samo siebie. Zgodność etykiet z `fields.json`: recall 0,43, precision 0,30, typy dopasowanych pól 100%, adresat i wnioskodawcy poprawni. Model dodał PESEL i NIP, a resztę pól nazwał innymi słowami.
  JPG, 1 przebieg: JSON poprawny, walidacja nie (2 × `show_if` na nieistniejące pole), 575 s, recall 0,29, precision 0,22.
  Pierwsze zapytanie po starcie serwera trwa 16,7 s, krótkie zapytanie po rozgrzaniu 3,2 s. Bielika nie mierzyliśmy (decyzja lidera, mało pamięci).
- **K1 – wniosek.** Qwen3.5-4B zostaje: daje poprawny JSON, myślenie da się wyłączyć. Kryterium „< 60 s na CPU” jest niespełnione, więc `LLM_TIMEOUT_S=120` na takim laptopie to zawsze 503. Skan przez model był wolniejszy i gorszy niż tekst (jeden przebieg). Zalecenie dla K2: skany przez OCR, obraz w modelu tylko jako zapas. Surowe odpowiedzi i raporty leżą tylko w `materialy/bench-k1/`, poza gitem.

M1.3 (Marcin):

| What                                   | Why                                         | Licence    |
| -------------------------------------- | ------------------------------------------- | ---------- |
| obraz `python:3.14.10-slim-trixie`     | Treść pkt 5: Python 3.14, jawna wersja      | PSF-2.0 (Python), Debian |
| `tesseract-ocr` 5.5.0 + `tesseract-ocr-pol` (apt) | OCR skanów JPG/PNG i PDF bez tekstu (K2) | Apache-2.0 |

- Kontener `api`: użytkownik `app` (UID 10001) bez powłoki, kod tylko do odczytu, w compose `read_only`,
  `tmpfs /tmp`, `cap_drop: ALL`, `no-new-privileges`. Zapis poza `/tmp` w pamięci kończy się błędem.
- Do decyzji lidera lub mentora: pakiet Debiana `tesseract-ocr` ciągnie biblioteki systemowe na LGPL
  (pango, cairo, glib, gnutls, fribidi, libthai). Obraz bazowy ma już glibc (LGPL) i bash (GPL).
  To biblioteki systemu łączone dynamicznie, nie kod aplikacji. Lista: `dpkg-query -W` w obrazie.
- Docker Hub ogranicza pobrania bez logowania. Ten sam obraz jest w `mirror.gcr.io/library/python`:
  `podman pull mirror.gcr.io/library/python:3.14.10-slim-trixie` i `podman tag` na nazwę z Dockerfile.

M1.5 (Marcin):

| What                          | Why                                              | Licence |
| ----------------------------- | ------------------------------------------------ | ------- |
| obraz `ollama/ollama:0.40.15` | lokalny serwer modelu w compose (SPEC „Model”); wersja z pomiaru K1 | MIT |
| PyYAML 6.0.4 (tylko testy) | testy czytają `docker-compose.yml` parserem, nie regexami po wcięciach (recenzja M1.5) | MIT |

- `ollama/Dockerfile` dodaje użytkownika `ollama` (UID 10002), bo oficjalny obraz działa jako root (Treść pkt 5).
- Serwis `ollama` nie wystawia portu na hoście; `api` woła `http://ollama:11434/v1` w sieci compose.
- Model jest w wolumenie `ollama-models`, pobierany raz przez `scripts/pull_model.sh`. To jedyny trwały zapis.
- `OLLAMA_CONTEXT_LENGTH=16384` (K1) i `OLLAMA_KEEP_ALIVE=24h`: model zostaje w pamięci, demo nie czeka na ładowanie.
- `OLLAMA_NO_CLOUD=1`: bez modeli i usług w chmurze Ollamy (Treść pkt 5, prośba Mikołaja).
- `name: hacknation-2026` w compose: ten sam wolumen z modelem w każdym katalogu, bez ponownego pobierania 3,3 GB.

pypdf (Marcin, na prośbę Mikołaja do K2.3):

| What         | Why                                                        | Licence      |
| ------------ | ---------------------------------------------------------- | ------------ |
| pypdf 7.1.1  | tekst z PDF w pamięci (K2.3); czysty Python, obraz bez zmian | BSD-3-Clause |

- Bez dodatku `crypto`: zaszyfrowane PDF-y (AES) wymagają `cryptography` – decyzja przy K2.3, jeśli trafią się w materiałach.

K3 (Mikołaj):

- **K3 – ustawienia.** `analysis.analyze(doc, *, settings)` i `llm.chat_json(..., settings=...)` wymagają ustawień od wołającego. Żaden z nich nie czyta env, więc `dependency_overrides[get_settings]` obejmuje model i `LLM_FIXTURE` (uwaga R2 z recenzji K1).
- **K3 – atrapa.** Przy `LLM_FIXTURE` `llm.py` zwraca treść pliku bez sieci. Dalej idą ta sama walidacja i budżet co dla modelu. Nieczytelny plik daje 503, a ścieżka trafia do logu.
- **K3 – ponowienia.** Dwie próby (decyzja 2026-11-21: na CPU jedna próba to 240–344 s). Druga dostaje swoją odpowiedź i do 10 błędów walidatora z miejscem, np. `subject_pages[0]`. Ucięta odpowiedź (`finish_reason=length`) dostaje uwagę o długości. Gdy z poprzednią odpowiedzią ponowienie nie mieści się w kontekście, druga próba dostaje cały dokument i same błędy (recenzja Codexa, folder 9). Timeout i błąd sieci nie są ponawiane. Po drugiej złej odpowiedzi jest 503 (D4).
- **K3 – budżet kontekstu.** Szacunek: 2,5 znaku na token (K1 zmierzyło 3,6), 2500 tokenów na obraz strony, 4096 na odpowiedź, kontekst 16384. Budżet jest sprawdzany przed każdą próbą. Za długiego zapytania nie wysyłamy: 503 i ostrzeżenie w logu, bez przycinania i bez częściowej analizy (decyzja 2026-11-21).
- **K3 – przycięcie przez serwer.** Serwer z mniejszym kontekstem (domyślnie 4096) przycina prompt bez błędu. Dlatego `prompt_tokens` z odpowiedzi poniżej liczby znaków / 5 daje 503 (zmierzone: K1 3,6, K3 3,5 znaku na token). Wykrywa utratę ponad ok. 30% promptu. Bez `usage` w odpowiedzi kontrola jest pomijana (recenzja K3). Cache prefiksu nie zaniża licznika: w K1 trzy identyczne zapytania z rzędu dały po 2034 `prompt_tokens` (Ollama 0.40.15).
- **K3 – odczyt odpowiedzi.** `json.loads`, potem `FormAnalysis.model_validate`. Parser Pydantic (`model_validate_json`) odrzuca samotny surogat, zanim `models.py` zamieni go na U+FFFD (P1.2a). Błąd składni nadal opisuje Pydantic.
- **K3 – tekst dla modelu.** 4 i więcej kropek, podkreśleń lub wielokropków zamieniamy na „…”, scalamy spacje, usuwamy puste linie, dodajemy nagłówki stron. Litery i cyfry zostają wszystkie i w tej samej kolejności (test). Obrazy stron idą do modelu tylko bez tekstu (K1: skan wolniejszy i gorszy). Dokument bez tekstu i obrazów daje `ExtractionError` (400) bez zapytania.
- **K3 – prompt.** Zasady z SZABLONY rozdz. 6, kontrakt `applicant` i schemat `FormAnalysis` bez adnotacji `title` z Pydantic (opisy pól to instrukcje dla modelu). Zasada mentora: każdy element JSON-a ma podstawę w tekście formularza, a przy braku informacji jest `false` albo pusta lista. Kontraktu nie rozszerzamy. Test D5 sprawdza prompt tak samo jak schemat.
- **K3 – pomiar.** `qwen3.5:4b`, `ollama/ollama:0.40.15`, sam CPU (limit 6 GB), DOCX nadpłaty z folderu 5, tekst przez `docx_text` z `bench_model.py` (zastępstwo K2), jeden przebieg 2026-11-21. Próba 1: 2765 tokenów promptu (szacunek 3908), 1167 odpowiedzi, 584 s, 1 błąd walidatora. Próba 2 z błędem: 4022 i 1185 tokenów, 537 s, poprawny `FormAnalysis`. Razem 1121 s. Tytuł, adresat, `applicants` i `signature` zgodne z `fields.json`.
  Jakość: model powtórzył dane wnioskodawcy w `subject_pages` i rozbił wybór rozliczenia na dwa RADIO. Dodał też oświadczenie, pole „Inne dokumenty” i REGON, których nie ma w tekście papieru. `contact: []` i `proxy: false` zgadzają się z papierem, a `fields.json` opisuje wzorzec COI. Wniosek: zasada podstawy w treści w samym prompcie nie wystarcza modelowi 4B (Requests). Pomiar przeszedł przed dwiema poprawkami promptu z recenzji (`false` tylko w `applicant`, domyślny podpis). Wynik leży poza repozytorium.

K2.2 (Mikołaj): Tesseract CLI i dane językowe `pol` (Apache-2.0) do lokalnego OCR skanów JPG/PNG.
Stdin i stdout pozwalają odczytać obraz bez tworzenia pliku tymczasowego.

K2.3 (Mikołaj): `pypdf` 7.1.1 (BSD-3-Clause, bez wymaganych zależności) czyta warstwę tekstową PDF
z bajtów w pamięci. Odczyt K2 zostaje lokalny i deterministyczny: COI dopuściło Eden AI, ale K2 nie
używa zewnętrznego OCR ani kluczy API (decyzja lidera). Strona bez tekstu zostaje pusta między
separatorami `\f` i trafia do `warnings`; jej OCR to osobny krok.

LLM_CONTEXT_TOKENS (Marcin, prośba Mikołaja do K3):

- Jedna zmienna `LLM_CONTEXT_TOKENS` (domyślnie 32768, min. 8192) dla `Settings` i dla Ollamy w compose
  (`OLLAMA_CONTEXT_LENGTH: ${LLM_CONTEXT_TOKENS:-32768}`). Serwer z mniejszym kontekstem przycina prompt po cichu (K1),
  więc obie strony muszą znać tę samą liczbę. Test pilnuje, że domyślna w compose = domyślna w `Settings`.
- 32768 zamiast 16384: tekst formularza 8 (ok. 31 tys. znaków) nie mieści się w 16384, a 9 nie zostawia miejsca na ponowienie.
  Koszt na CPU zmierzony dla `qwen3.5:4b` w kontenerze `ollama`: 3,7 → 4,2 GB (`ollama ps`), kontener 4,28 → 4,84 GB.
  Modele w chmurze mają więcej (Qwen3.5-9B: 262144); wtedy `LLM_CONTEXT_TOKENS` można podnieść w `.env`.

M1.7 (Marcin): `LLM_PROVIDER` według D9 i DELEGACJA rozdz. 3 z gałęzi lidera `lead/mentor-2111`. Bez nowej zależności.

- **Dostawca.** `ollama` (domyślnie) albo `edenai`, wielkość liter bez znaczenia. Inna wartość zatrzymuje start API.
- **Host przy `edenai`.** Tylko `https://api.edenai.run` i `https://api.eu.edenai.run` (adres z README K3.1-2), port 443,
  bez użytkownika w adresie. Inny adres zatrzymuje start (D9 pkt 2).
- **Klucz przy `edenai`.** Wymagany. `ollama` z `env.example` też się nie liczy. Komunikat błędu nie podaje klucza.
- **Modele przy `edenai`** (D9 pkt 7 i 8): tylko trasy otwartego Qwen3.5-9B z publicznego katalogu Eden AI:
  `ovhcloud/Qwen3.5-9B`, `ionos/Qwen/Qwen3.5-9B`, `flexai/Qwen3.5-9B`, `flexai/Qwen3.5-9B@eu`,
  `greenference/qwen3.5-9b`, `tensorx/qwen/qwen3.5-9b`, `deepinfra/Qwen/Qwen3.5-9B`, `together_ai/Qwen/Qwen3.5-9B`.
  Ostatnie dwie mają w katalogu datę wycofania; są na liście, bo model jest otwarty, ale wybór trasy należy do lidera.
  Inny model wymaga wpisu tutaj i w `EDENAI_OPEN_MODELS` (`config.py`). Test pilnuje, że oba miejsca się zgadzają.
- **Adres domyślny.** Pusty `LLM_BASE_URL` daje adres dostawcy: przy `edenai` `https://api.edenai.run/v3`, przy `ollama`
  `LLM_OLLAMA_URL` albo `http://localhost:11434/v1`. Compose podaje `LLM_OLLAMA_URL: http://ollama:11434/v1` osobno,
  zamiast domyślnej w `LLM_BASE_URL`. Dzięki temu adres Ollamy nie trafia do dostawcy `edenai` (DELEGACJA, M1.7).
- **Adres Eden AI przy `ollama`** zatrzymuje start (recenzja M1.7). Inaczej `LLM_PROVIDER=ollama` z adresem Eden AI
  omijałby listę modeli otwartych. Komunikaty o dostawcy i modelu nie powtarzają wartości: klucz wklejony w złą
  zmienną trafiłby do logu (D9 pkt 3).
- **Sieć.** `api` zostaje w zwykłej sieci compose z wyjściem do internetu. Test pilnuje, że jego sieć nie jest `internal`.

K2.4 (Mikołaj): XLSX i ODS bez nowej zależności: `zipfile` i `ElementTree` z biblioteki standardowej,
jak DOCX w K2.1. `openpyxl` i `odfpy` z DELEGACJA niepotrzebne, więc `requirements.txt` bez zmian.

- **Układ tekstu.** Arkusz to strona (`\f`), w kolejności skoroszytu. Wiersz to niepuste komórki
  rozdzielone ` | `, jak wiersz tabeli DOCX. Puste arkusze, wiersze i komórki są pomijane. Nazw
  arkuszy nie dodajemy: nie są tekstem formularza. W 6 z 7 folderów XLSX i ODS dają identyczny tekst.
  W folderze 3 XLSX nie ma wiersza „Młynary, dnia…”, który ma ODS. To różnica w samych plikach.
- **Zakres.** Wchodzą wszystkie komórki z tekstem, także ukryte i przykryte scaleniem. Nie wchodzą
  komentarze, nagłówki i stopki wydruku ani kształty XLSX: tych części materiały COI nie mają.
  Wartość logiczna to „PRAWDA” albo „FAŁSZ”, jak w polskim Excelu i LibreOffice.
- **Liczby XLSX.** Liczby i daty zostają w postaci zapisanej w pliku, np. data jako numer seryjny.
  Format wyświetlania wymagałby odczytu stylów. ODS zapisuje tekst wyświetlany, więc go używamy.
- **Limity.** 8 MB rozpakowanych XML na cały plik, 1 MB na spis arkuszy i relacje. Do tego
  100 poziomów zagnieżdżenia XML, 10 000 elementów w jednej komórce i 1 mln znaków tekstu.
  Znaki liczymy przed rozwinięciem powtórzeń ODS. Pusty wiersz powtórzony 1 048 576 razy
  (tak zapisuje LibreOffice) jest pomijany bez pętli. Przekroczenie albo kodowanie XML, którego
  parser nie zna, daje 400.
- **Pamięć.** XML czytamy strumieniowo. Przetworzona komórka znika z drzewa, więc w pamięci są
  tylko otwarte elementy i jedna komórka.
- **Pomiar.** 16 plików COI (foldery 1–9): 0,8–51 ms na plik, szczyt pamięci procesu 43 MB.
  Najgorsze przypadki tuż pod limitem 8 MB, z ZIP-ów 9–25 KB: do 2,45 s CPU, szczyt procesu
  72 MB (39 MB po samym imporcie). Przed limitami recenzja zmierzyła 416–867 MB dla jednego
  długiego wiersza, głębokiego zagnieżdżenia i komórki z milionem elementów.

K3.1-3 – E1 na Eden AI i naprawy analizy

- Pomiar człowieka 22.11, 01:10–01:30. `ovhcloud/Qwen3.5-9B` ignorowała wyłączenie myślenia przy
  `reasoning_effort` ustawionym na `none` lub `disable` oraz przy `chat_template_kwargs.enable_thinking=false`.
  Odpowiedzi z limitem 8192 kończyły się `length`, bez treści lub z uciętym JSON-em. Na
  `flexai/Qwen3.5-9B@eu` z `reasoning_effort=off` i `enable_thinking=false` model nie zwracał toku
  rozumowania. Przepustowość wyniosła ok. 130–160 tok/s, a próby 3,5–65 s. Trasę zatwierdza lider (D9 pkt 8).
- E1 na flexai z kontekstem 65536, limitem odpowiedzi 8192 i trzema próbami: F4, F6, F7, F8 przeszły
  z lint 0 i oparciem 90–100%. F2, F3, F5, F9 dały 503. F9 przy limicie 16384 zakończył generację
  z 8549 tokenami i `stop`, po czym walidacja zgłosiła 29 błędów. Przy temperaturze 0 próby 2 i 3
  powtórzyły wynik z użyciem 5130/1387 tokenów.
- Walidacja surowych odpowiedzi F2–F9 potwierdziła W1, powtórzone alternatywy (25 błędów wobec 24 w
  pierwotnym histogramie), W2, CHECKBOX bez opcji (11 błędów, 15 pól po uwzględnieniu zamaskowanych),
  W3, sprzeczny wybór identyfikatora (1), W4, RADIO bez opcji (2 w F5 oraz 3 ujawnione po N1–N3 w F9)
  i W5, brakujące źródło w F4 lub opcja w F6. Po ostatniej szansie walidacja kontraktu dała 8/8.
- Kontrakt D4 zostaje. Przed walidacją każdej próby usuwamy duplikaty alternatyw, wyłączamy wybór
  identyfikatora przy mniej niż dwóch i uzupełniamy pustą opcję CHECKBOX. Tylko w ostatniej szansie
  zamieniamy puste RADIO/SELECT na CHECKBOX z `Tak`, aktualizujemy odwołania i usuwamy niepoprawne
  warunki. Każda naprawa jest oznaczona w logu. Temperatura ponowienia wynosi co najmniej 0,3, gdy jest włączona.
- Przy `edenai` domyślne są `https://api.eu.edenai.run/v3`, `flexai/Qwen3.5-9B@eu`, kontekst 65536,
  limit odpowiedzi 16384, `reasoning_effort=off` i `chat_template_kwargs.enable_thinking=false`.
  Kontekst 65536 zostawia miejsce dla F8 i 16384 tokenów odpowiedzi. Obowiązuje walidacja dostawcy M1.7.

## Event: whole project

- **D7 – odpowiedzialność.** Lider rozstrzyga kontrakty, zakres i integrację. `SPEC.md` określa kontrakty, `DECISIONS.md` zapisuje decyzje, `DELEGACJA.md` wyznacza wykonawców, a `PROGRESS*.md` rejestruje postęp i wyniki bramek.
- **D15 – kroje na licencji OFL-1.1.** Decyzja lidera (2026-11-21) przed pracą nad frontem, razem z sekcją „Two zones” w `DESIGN.md`. Dopuszczamy kroje na licencji SIL OFL-1.1 tylko jako niezmienione pliki krojów w repozytorium, bez CDN i bez subsetowania (to już modyfikacja). OFL nie wymaga publikacji kodu aplikacji: jej warunki dotyczą samego kroju, nie programu, który go używa. Treść pkt 5 zakazuje licencji, które tego wymagają, więc OFL jej nie narusza. To nie jest czwarty wyjątek MPL-2.0 z sekcji szablonu: D15 obejmuje wyłącznie pliki krojów, nie pakiety. Każdy dodany krój dostaje linię pod „Event: web” (nazwa, wersja, źródło, OFL-1.1), a obok plików leży tekst licencji z informacją o prawach autorskich.
