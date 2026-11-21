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
- **P1 – generator** (`backend/app/generator/`, dopowiedzenia lidera do SZABLONY i poprawki po recenzji). PERSON: radio Swoim i Innej osoby, bez sekcji podmiotu. ENTITY: jedna opcja osoby prawnej, bez sekcji innej osoby. BOTH: jak wzorzec. Czasownik w etykietach S2 z pierwszego słowa tytułu (wniosek, zgłoszenie, deklaracja; inaczej „wnioskujesz”); techName S2 stałe. techName unikalne w formularzu, najwyżej 60 znaków (cięcie na `_`), szablon ma pierwszeństwo, kolizje dostają _2, _3. Strona przedmiotu o tytule strony standardowej dostaje „ wniosku”, powtórzenie „ (2)”; tytuły porównywane po NFC i casefold. Jsonata używa końcowych tytułów i techName; w literałach escapuje `"` i `\`, a apostrof w literale w apostrofach (tytuł strony) zapisuje sekwencją `\u0027`, bo JSONata nie zna `\'`. UUID5 ze stałej przestrzeni nazw i kanonicznego JSON-a analizy (`sort_keys`). `ADD_VALIDATORS = True` w `form.py`; pola tylko do odczytu z rejestru mają `validation: []`; radio opłaty skarbowej (S10) ma `REQUIRED` (Standardy COI). Zgoda bazowa bez linku, dopóki `PRIVACY_CLAUSE_URL` jest pusty. Oświadczenia to kolejne wymagane zgody. Tekst od modelu w HTML-u jest escapowany.

- **P2 – linter** (`backend/app/lint.py`). Kontrolujemy `repeatingSectionGrid` zgodnie z eksportami COI, dopuszczamy dodatkowe klucze, `defaultValue` jako tekst lub tablicę, pusty `validation: {}`, brak `states` i `options[].techName` oraz `TEXT_BLOCK` obok `INFO_SECTION` na `FINISH` (Reguły, ak. 12, wymieniają wyłącznie `INFO_SECTION`). Opis importu, ak. 71, określa `validation` jako „tablica stringów przyjmująca nazwy predefiniowanych walidacji”. Przyjmujemy dziewięć nazw z Reguł, pola informacyjne mają pustą konfigurację walidatorów. Opis importu, ak. 96–98, i schemat, w. 109–111, umieszczają `required` w `consentSectionConfig`. Reguły, ak. 575–582, i oba wzorce umieszczają flagę przy każdej zgodzie, więc tam jest wymagana. Na poziomie konfiguracji sprawdzamy jej typ, gdy występuje. `techName` sekcji i pól są unikalne w formularzu. Różne pola mogą używać tych samych identyfikatorów i nazw technicznych opcji. JSONata dopasowuje literał do `id` lub `name` opcji, a pole słownikowe pomija kontrolę wartości. Sprawdzamy osiągalność stron od pierwszej i drogę z każdej `MAIN` do `FINISH`. Odwołanie JSONata musi wskazywać pole wyboru, siatka wymaga `x/y/rows/cols`, strona wymaga niepustych `id` i `title`, pole niepustych `id` i `type`, link niepustego `id`, a lista `consents` co najmniej jednej zgody, przy czym `id` stron, pól (w tym sekcji) i linków należą do jednej przestrzeni, a typy sprawdzamy przez `isinstance` z wyłączeniem `bool` jako liczby.

- **P1.2a – kontrakt.** `FormAnalysis` wymaga jawnych `applicants` i `applicant: ApplicantData`. Decyzje MVP mają przesłanki w papierze i są niezależne od ekstraktora. Dane spoza szablonu trafiają do `applicant_extra_fields`, a reguły D4 dla `show_if` obowiązują także w tej liście. Tekst analizy naprawia samotne surogaty do U+FFFD przed walidacją. Dobór sekcji należy do P1.2b, detektor do P1.2c, a tryby rozszerzone do P1.3. Test D5 pomija dokładne słowo »regon« – nazwa walidatora z Reguł i wartość kontraktu, nie tekst z folderu 1.

- **P1.2b – generator.** `FormAnalysis.applicant` wyznacza sekcje wnioskodawcy, korespondencję, pola dodatkowe i kontakt, a S2 wyświetla tylko faktyczne wybory, co zastępuje GD2 z radiem o jednej opcji dla ENTITY.

- **P1.3a.** Pola `TEXT_FIELD` z analizy dostają walidator typu po `REQUIRED`, jeśli etykieta po NFC, casefold i usunięciu polskich znaków pasuje do dokładnie jednej kategorii na granicach słów (PESEL, NIP, REGON, ZIP_CODE, EMAIL, SERIAL_NUMBER_ID_CARD, EPUAP, ADE). Etykieta złożona → bez walidatora typu, jeśli po usunięciu dopasowanej frazy pozostaje separator, spójnik lub słowo innej danej. Dobór odbywa się bez modelu, a `ADD_VALIDATORS = False` czyści wszystkie walidatory.

- **P1.4.** Alternatywy i koniunkcje SHOW na polach i sekcjach przedmiotu, wcześniejsze źródła między stronami i wykrywanie cykli. F9 jest jednym formularzem z czterema warunkowymi miejscami dla podopiecznych.

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

## Event: whole project

- **D7 – odpowiedzialność.** Lider rozstrzyga kontrakty, zakres i integrację. `SPEC.md` określa kontrakty, `DECISIONS.md` zapisuje decyzje, `DELEGACJA.md` wyznacza wykonawców, a `PROGRESS*.md` rejestruje postęp i wyniki bramek.
- **D8 – sensowna cyfryzacja formularzy.** Mentor COI potwierdził 2026-11-21 trzy zasady. Repozytorium już je stosuje, więc D8 nie zmienia kontraktu ani generatora.
  1. Sekcje wnioskodawcy wynikają z papieru. PESEL, adresy, NIP/REGON/KRS, pełnomocnik, adres do korespondencji i kontakt pojawiają się tylko wtedy, gdy papier o nie pyta. Robią to kontrakt P1.2a (`FormAnalysis.applicant`) i generator P1.2b (tabela w SZABLONY rozdz. 1).
  2. Zostaje każda informacja potrzebna do załatwienia sprawy: dane innych osób, daty, załączniki, instrukcje, wybory i ich warunki (opis `subject_pages` w `models.py`, P1.2a).
  3. Prosty język i warunki. Etykiety w 2. osobie, bez „Na podstawie art. …”. Dane dopisywane przy opcji to pole z SHOW tej opcji (`label` i `show_if` w `models.py`, SZABLONY rozdz. 6).
  Pozostałe reguły SZABLONY rozdz. 6, np. lista „Usuwamy z papieru”, to nadal decyzje zespołu bez potwierdzenia mentora.
- **D9 – Eden AI: wyjątek od lokalnego modelu.** COI dopuściło 2026-11-21, po konsultacji lidera, Eden AI udostępnione zespołowi na potrzeby zadania „Cyfryzacja formularzy”. To jedyny wyjątek od zakazu zewnętrznych API (Treść pkt 5). Innych zewnętrznych API nie używamy, także chmury Ollamy (`OLLAMA_NO_CLOUD=1` zostaje). Wcześniej tego dnia mentor dopuszczał Eden AI tylko w eksperymentach; ta decyzja to zastępuje.
  1. Ollama zostaje jako alternatywa. Lokalny `qwen3.5:4b` w compose jest wartością domyślną repozytorium i działa bez klucza. Eden AI włącza człowiek ustawieniem `LLM_PROVIDER=edenai`. Adapter to zadanie K3.1, konfiguracja to M1.7 (`DELEGACJA.md` rozdz. 3 i 5).
  2. Model woła nadal tylko `backend/app/llm.py`. Przy `LLM_PROVIDER=edenai` dozwolony jest tylko host Eden AI: inny adres zatrzymuje start API.
  3. Klucz Eden AI leży poza repozytorium i poza dostępem agentów. Człowiek podaje go tylko na czas uruchomienia (demo, pomiar, eval), np. `docker compose --env-file` z plikiem spoza katalogów roboczych. Klucz nie trafia do `env.example`, logów, raportów, zrzutów ekranu ani promptów.
  4. Agenci nie czytają klucza i nie wysyłają zapytań do Eden AI. Testy i e2e też nie: używają atrapy transportu albo `LLM_FIXTURE`. Pomiary na żywo robi człowiek.
  5. Do Eden AI idzie treść wczytanego pliku. Wysyłamy puste formularze z materiałów COI; folder 1 zostaje poza promptami (D5). README i dokumentacja architektury mówią o tym wprost.
  6. Nowa zależność nie jest planowana: klient `httpx` już jest. Gdyby była potrzebna, dostaje linię z licencją w tym pliku.
  7. Tylko modele otwarte. Mentorzy COI (odpowiedź z Discorda, 2026-11-21) dopuszczają model w chmurze i komunikację przez API tylko wtedy, gdy model jest otwarty, a jego wagi pozwalają wdrożyć go samodzielnie na własnej infrastrukturze. Modeli zamkniętych, dostępnych wyłącznie przez API, nie wolno używać. Eden AI udostępnia też modele zamknięte, więc przy `edenai` `LLM_MODEL` to wyłącznie model otwarty zapisany w tym pliku.
  8. Model docelowy K3.1 to **Qwen3.5-9B** (decyzja lidera, 2026-11-21). Licencja Apache-2.0, wagi publiczne na Hugging Face (`Qwen/Qwen3.5-9B`). Ten sam model jest w Ollamie jako `qwen3.5:9b` (6,6 GB w Q4_K_M), więc da się go wdrożyć samodzielnie.
     Dostępność: publiczny katalog Eden AI (`GET https://api.edenai.run/v3/models`, odczyt bez klucza, 2026-11-21) ma go pod ośmioma identyfikatorami. Wszystkie deklarują kontekst 262 144 tokeny i `supports_response_schema: true`. Kandydaci z regionu UE, z obrazem na wejściu i bez daty wycofania: `ovhcloud/Qwen3.5-9B` i `ionos/Qwen/Qwen3.5-9B`. Pozostałe: `flexai/Qwen3.5-9B` (także `@eu`), `greenference/qwen3.5-9b` (tylko tekst), `tensorx/qwen/qwen3.5-9b` (fp8). `deepinfra/Qwen/Qwen3.5-9B` i `together_ai/Qwen/Qwen3.5-9B` mają w katalogu datę wycofania 2026-10-21, więc nie wybieramy ich bez sprawdzenia.
     Niepotwierdzone bez zapytania na żywo: czy wybrana trasa przyjmuje `reasoning_effort` (katalog deklaruje go tylko dla `together_ai`), jak wyłączyć myślenie (karta modelu: domyślnie włączone) i jaki jest czas odpowiedzi. Trasę wybiera lider po pomiarze człowieka z kluczem.
  Stan: kod woła dziś tylko Ollamę. Do Eden AI nie poszło jeszcze żadne zapytanie do modelu, więc czas i jakość są niezmierzone.
- **D10 – jeden dokument, jeden JSON; pola, warianty, zależności.** Decyzja lidera po konsultacji z COI (2026-11-21), podtrzymana tego samego dnia wieczorem razem z D11.
  1. Jeden plik wejściowy daje dokładnie jeden JSON COI. Dotyczy to także formularza 9 (trzy wnioski w jednym dokumencie): powstaje jeden formularz, nie trzy. `POST /api/forms` już tak działa (200 to jeden JSON), a E1 oddaje jeden JSON na formularz.
  2. Wiele pól, warianty i zależności mają być odwzorowane poprawnie. Wariant z papieru (np. rodzaj wniosku w formularzu 9) to pole wyboru, a dane potrzebne tylko w jednym wariancie mają warunek SHOW tej opcji. Żadne pole z papieru nie ginie (D8 pkt 2).
  3. Brak nieuzasadnionych pól: każde pole, opcja, sekcja i oświadczenie ma podstawę w dokumencie. Dotyczy analizy (zasada podstawy w treści w prompcie K3) i szablonu (D8 pkt 1).
  Stan kontraktu po P1.4 (na `main`): warunki SHOW działają na polach i sekcjach przedmiotu, przyjmują alternatywy i koniunkcje oraz źródła z wcześniejszych stron, a cykle są wykrywane. Formularz 9 jest jednym formularzem. Link `flow` w formacie COI nie ma warunku, więc stron alternatywnych nie zapisujemy.
- **D11 – cel wydajnościowy.** Cały proces, od przyjęcia pliku do JSON-a (kontrola, odczyt z OCR, analiza z ponowieniami, generator, linter), ma trwać około 180 s, także podczas live demo. Granica orientacyjna to 200 s. Decyzja lidera po konsultacji z COI (2026-11-21). Zastępuje „< 60 s na formularz na CPU” (DELEGACJA rozdz. 4), „JSON w < 2 min” (M1.5) i miarę M7 „< 60 s na plik” (`docs/ZESTAW_TESTOWY.md`).
  Stan pomiarów: lokalny Qwen na samym CPU nie mieści się w celu. K1: 238–344 s na jedną próbę z DOCX. K3 (gałąź `mikolaj/k3`, przed scaleniem): 1121 s w dwóch próbach. Eden AI jest niezmierzone.
  Skutek: suma limitów czasu ma się mieścić w budżecie. Dziś `LLM_TIMEOUT_S=120` i dwie próby K3 to do 240 s samej analizy. Budżet rozdzielają K3.1 i M1.4 po pomiarze. `LLM_TIMEOUT_S=600` (prośba z K1) nie może być wartością domyślną.
- **D12 – środowisko obrony.** Mentorzy COI (odpowiedź z Discorda, 2026-11-21): obrona działa na architekturze x86, bez dedykowanego GPU. Ilość RAM-u i stabilność internetu są niepotwierdzone.
  1. Obrazy i model lokalny muszą działać na x86-64 i na samym CPU. `docker-compose.yml` nie rezerwuje GPU, a K1 mierzono na x86 (Core Ultra 7 255U) bez GPU.
  2. Lokalny model na samym CPU nie spełnia D11 (K1), więc ścieżką na live demo jest Eden AI (D9). Wymaga ona internetu, którego stabilność jest niepotwierdzona.
  3. Ollama zostaje alternatywą bez internetu. Przełącza ją człowiek zmienną `LLM_PROVIDER`. `qwen3.5:9b` lokalnie jest niezmierzony, a jego plik ma 6,6 GB wobec 3,3 GB dla 4B. Przy niepotwierdzonym RAM-ie nie zakładamy, że się zmieści.
  4. Obrazy i model lokalny pobieramy przed obroną, nie w jej trakcie.
  Otwarte: ilość RAM-u i stabilność internetu.
- **D13 – walidatory potwierdzone.** Mentor COI (2026-11-21): puste tablice `validation` w przykładach nie zabraniają walidatorów. Należy używać odpowiednich dostępnych reguł, jeśli wynikają z analizy formularza. To zamyka pytanie 1 z `docs/BRIEF_ZESPOL.md` rozdz. 7 i potwierdza SZABLONY rozdz. 5, P1 (`ADD_VALIDATORS = True`) i P1.3a. Dostępne reguły to dziewięć nazw z Reguł technicznych (lista w `lint.py`). Walidator dodajemy tylko wtedy, gdy wynika z pola: z rodzaju danych albo z obowiązkowości. Kod bez zmian.
- **D14 – słowniki z pliku COI.** Mentor COI (2026-11-21): identyfikatory słowników i konkretne wartości bierzemy z przekazanego pliku słowników COI. Nie kopiujemy bez podstawy różniących się wartości z formularzy przykładowych i nie wymyślamy nowych.
  Plik „Hacknation - Słowniki” z `materialy/` wymienia: Województwo, Powiat, Gmina, Miejscowość, Kraje i Numery kierunkowe. Słownik wolno podpiąć do listy rozwijanej, radia i checkboxa, a słowniki adresowe i Kraje tylko do listy rozwijanej. Plik podaje nazwy, bez list wartości i bez identyfikatorów technicznych.
  Stan kodu: generator używa `Kraje` (jest w pliku) oraz `TERYT_4G_DOWODOWY` z `multiLevelTree` dla adresu w Polsce (`generator/template.py`). `TERYT_4G_DOWODOWY` podają Standardy COI (rozdz. „Adres”: „Zaimportowany słownik: TERYT_4G_DOWODOWY”) i oba wzorce. Plik słowników go nie wymienia, a osobno wymienia Województwo, Powiat, Gminę i Miejscowość. `TERYT_DOWODOWY` jest tylko we wzorcach, a wzorce 1 i 5 używają obu nazw różnie. Wartość domyślna `["Polska"]` w `Kraje` pochodzi z obu wzorców. Linter nie sprawdza nazwy słownika. Kontrakt `FormAnalysis` nie pozwala modelowi wskazać słownika w polach przedmiotu.
  Otwarte: słownik adresu zamieszkania, czyli `TERYT_4G_DOWODOWY` ze Standardów i wzorców albo Województwo, Powiat, Gmina, Miejscowość z pliku słowników. Dwa dokumenty COI mówią tu co innego, więc to pytanie do mentora. Do odpowiedzi generator zostaje bez zmian.
