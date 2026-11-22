# SPEC (one page; filled by /hn-spec)

## Task and criteria

„Cyfryzacja formularzy” (COI, HackNation 2026). AI zamienia plik formularza (PDF, DOC, DOCX, ODS,
XLSX, JPG, JPEG, PNG) w JSON konfiguracji eUsługi w formacie COI.
Kryteria (Treść pkt 8): kompletność 30% (minimum z pkt 3.2 i progi za rozszerzenia I–V),
intuicyjność 20%, jakość kodu 20%, potencjał wdrożeniowy z kosztem 20%, oryginalność 10%.
Pkt 8 numeruje rozszerzenia inaczej niż pkt 3.3 (V: walidacje czy wizualizacja?). Pytanie do mentora.
Oddajemy też (pkt 3.2, 4, 5): dokumentację architektury, README (obraz, uruchomienie, konfiguracja,
REST API), Docker bez roota z jawnymi wersjami obrazów, JSON-y formularzy do oceny, prezentację PDF
do 10 slajdów, film do 3 minut. Zakazane (pkt 5): zewnętrzne API i SaaS, modele dostępne tylko
przez API, licencje copyleft, trwały zapis plików. COI dopuszcza model w chmurze przez API, jeśli
jest otwarty i da się go wdrożyć samodzielnie; modele zamknięte są zakazane. Używamy tylko Eden AI
udostępnionego zespołowi na to zadanie (D9).

## User and problem

Urzędnik gminy, nie programista, który cyfryzuje formularze eUsług. Ręczne przerobienie jednego
papierowego wniosku na eUsługę to kilka dni analizy i konfiguracji.

## Demo flow

1. Otwórz aplikację: ekran „Wczytaj formularz”.
2. W polu „Plik formularza” wybierz PDF wniosku, którego system nie widział (foldery 2–4, 6–9).
3. Kliknij „Analizuj formularz”.
4. Zobacz „Podgląd eUsługi”: strony, sekcje i pola. „Twoje dane” mają dane inicjalne.
5. Zaznacz „Innej osoby”: pojawiają się „Dane innej osoby” i „Adres zamieszkania innej osoby”.
6. W tym adresie wpisz kod 12345 i kliknij „Dalej”: „Wpisz kod pocztowy w formacie 00-000”.
7. Kliknij „Pokaż JSON”, potem „Pobierz JSON”: plik gotowy do importu.
8. Wczytaj plik z nazwą .pdf, który nie jest PDF-em: komunikat o złym typie pliku.
9. Pokaż tabelę zgodności ze wzorcami z folderów 1 i 5, osobno dla każdego formatu.

## Must (at most 5, each visible in the demo; one owner per item)

1. API `POST /api/forms`: jeden plik w 8 formatach daje JSON COI. Kontrola: MIME zgodny
   z rozszerzeniem, nazwa do 250 znaków bez `; : > < / \ | ' * % $`, rozmiar z `MAX_FILE_SIZE_MB`.
   Wyjątki z materiałów COI: `.doc`, który w środku jest DOCX, jest czytany jak DOCX (pliki
   `.DOC` z folderów 5 i 7), a `.jpe` jak `.jpg` (plik `.JPE` z folderu 7). JSON spełnia schemat COI i Reguły techniczne (min. 2 strony, ostatnia FINISH, pola tylko
   w sekcjach, `flow` łączy strony). Jeden plik daje jeden JSON, także formularz 9 z trzema
   wnioskami w jednym dokumencie (D10). Cel czasu: około 180 s na cały proces, granica
   orientacyjna 200 s (D11). Pkt 3.2; kroki 2, 3, 8. Właściciel: do uzupełnienia.
2. Treść JSON-a według SZABLONY_SEKCJI.md: strona „Dane” z sekcji standardowych, strony tematyczne
   od AI, „Kontakt i zgody”, „Strona końcowa”. Dane inicjalne, słowniki z pliku słowników COI
   (D14), warunki SHOW, walidatory z rozdz. 5 (potwierdzone przez mentora, D13). Warianty i zależności z papieru to pola wyboru z warunkami SHOW. Każde pole ma
   podstawę w dokumencie, bez pól nieuzasadnionych (D10).
   Pkt 3.2, rozszerzenia I i III; kroki 4, 5. Właściciel: do uzupełnienia.
3. Ekran „Wczytaj formularz”: wybór pliku, postęp, komunikat błędu, „Pokaż JSON”, „Pobierz JSON”.
   Rozszerzenie IV; kroki 1–3, 7, 8. Właściciel: do uzupełnienia.
4. „Podgląd eUsługi” z JSON-a: strony, sekcje i pola, działające warunki SHOW, walidatory
   REQUIRED, PESEL, NIP, REGON, ZIP_CODE, EMAIL przy „Dalej”. Rozszerzenia V i VI; kroki 4–6.
   Właściciel: do uzupełnienia.
5. Wyniki i zgodność: jedno polecenie tworzy JSON-y formularzy z folderów 2–4 i 6–9 (do oddania).
   Liczy też procent pól zgodnych ze wzorcami z folderów 1 i 5, osobno dla każdego formatu.
   Krok 9. Właściciel: do uzupełnienia.

## Later (only if every Must is green)

Nowy słownik (rozszerzenie II) · wiele plików naraz w UI · strony alternatywne (przepływ
nieliniowy).

## Out (said out loud, so nobody builds it)

Edycja formularza w UI (kreator) · konta, logowanie, historia analiz, zapis plików · wysyłka
wypełnionego formularza i integracja z systemem docelowym · wersja w Javie · zewnętrzne API modeli
inne niż Eden AI i modele zamknięte (D9).

## API contract

`GET /health` → 200 `{"status": "ok"}` (już jest). Działa bez tokenu, także przy `JWT_ENABLED=true`.

`POST /api/forms`: `multipart/form-data`, jedno pole `file`.

```bash
curl -F "file=@Wniosek o wydanie zaświadczenia.pdf" http://localhost:8000/api/forms
```

JWT (Treść pkt 5): przy `JWT_ENABLED=true` żądanie ma nagłówek `Authorization: Bearer <JWT_TOKEN>`.
Token podpisuje `JWT_SECRET` algorytmem `JWT_ALGORITHM`. Przy `JWT_ENABLED=false` nagłówek nie jest wymagany.

- 200: ciało to sam JSON formularza (Field contract), bez opakowania.
- 401 `{"detail": "Brak tokenu dostępu albo token jest nieważny."}`, gdy `JWT_ENABLED=true`
  i nagłówka brak albo token jest zły lub wygasł. Sprawdzany przed plikiem.
- 400 `{"detail": "Nazwa pliku jest za długa albo ma niedozwolone znaki."}`, bez pliku w żądaniu
  `{"detail": "Wybierz plik formularza."}`, a gdy treści nie da się odczytać
  `{"detail": "Nie udało się odczytać treści pliku."}`
- 413 `{"detail": "Plik jest za duży. Limit to 10 MB."}`
- 415 `{"detail": "Zawartość pliku nie pasuje do rozszerzenia .pdf."}`, a dla innego rozszerzenia
  `{"detail": "Ten typ pliku nie jest obsługiwany. Wybierz PDF, DOC, DOCX, ODS, XLSX, JPG albo PNG."}`
- 503 `{"detail": "Model AI nie odpowiada. Spróbuj ponownie za chwilę."}`, także gdy model
  nie zwrócił poprawnej analizy
- 500 `{"detail": "Coś poszło nie tak. Spróbuj ponownie."}`

`detail` jest zawsze tekstem. API nie zwraca 422: błąd walidacji żądania wraca jako 400.
Front pokazuje `detail` bez zmian w komunikacie z `role="alert"`.

## Field contract

Pełny przykład to wzorzec COI z folderu 5:
`konfiguracja_form_wniosekOStwierdzenieNadpłatyPodatkuHacknation (2).json`. Format opisuje
SZABLONY_SEKCJI.md rozdz. 0, a nasze różnice od wzorca rozdz. 3 i 5 (`MLPZ.*`, walidatory).
Pola sekcji leżą w `repeatingSectionGrid`, jak we wzorcach. Schemat COI ma literówkę
`repetingSectionGrid`, której nie powielamy. Obiekt `field` ma zawsze wszystkie klucze.
`__userAnswer` nie występuje w pliku: podgląd ustawia go sam, zaczynając od `defaultValue`.
Pole z kroku 6 demo:

```
{"x": 0, "y": 5, "rows": 1, "cols": 3, "field": {"id": "27c0ee68-7e45-49ee-840d-61c079ee73f4",
 "type": "TEXT_FIELD", "techName": "kod_pocztowy_inna_osoba", "title": "Kod pocztowy",
 "description": "", "options": [], "validation": ["REQUIRED", "ZIP_CODE"], "readOnly": false,
 "repeatingSectionGrid": [], "states": [{"type": "SHOW", "query": "(\"Polska\" in tabs['Dane' in title].questions['adres_zamieszkania_osoby_ktorej_jestes_pelnomocnikiem' in field.techName].field.repeatingSectionGrid['kraj_inna_osoba' in field.techName].field.__userAnswer)"}],
 "questionOrder": 5, "tooltipMessage": ""}}
```

## Real and mocked

Prawdziwe: kontrola pliku, odczyt 8 formatów (skany przez OCR), analiza przez model (otwarty model
lokalnie w docker compose, a po K3.1 także Eden AI, D9), budowa JSON-a, podgląd, walidatory,
tabela zgodności.
Atrapy: wartości danych inicjalnych (`MLPZ.*`) i słowników (`Kraje`, `TERYT_4G_DOWODOWY`) w podglądzie
pochodzą z `frontend/src/data/demo.ts`. Słownik adresu w Polsce jest nierozstrzygnięty (D14). PESEL, NIP i REGON mają tam poprawne sumy kontrolne.
Testy nie wołają modelu ani Eden AI. Przy ustawionym `LLM_FIXTURE` moduł `backend/app/llm.py` zwraca
`backend/tests/fixtures/fields.json`, a `playwright.config.ts` ustawia tę zmienną dla API.
Ten fixture opisuje wniosek, który można złożyć w imieniu innej osoby (`applicants` = BOTH,
`applicant.proxy` = true; od P1.2b opcję „Innej osoby” daje `proxy`).
Materiały COI (zip z Discorda) leżą w `materialy/`, poza gitem. Foldery 1 i 5 to wzorce,
foldery 2–4 i 6–9 to formularze do oceny. Folder 1 to zbiór kontrolny: nie trafia do promptów,
opisów schematu modelu ani fixture’ów.

## Model

Model woła tylko `backend/app/llm.py`. Dostawcę wybiera `LLM_PROVIDER` (po M1.7 i K3.1).

Lokalnie (`ollama`, wartość domyślna): Qwen3.5-4B (`qwen3.5:4b`, Q4_K_M, ok. 3,4 GB, Apache-2.0),
serwis `ollama` w docker compose z jawną wersją obrazu, model w wolumenie. Interfejs zgodny
z OpenAI: `LLM_BASE_URL=http://ollama:11434/v1`, `LLM_MODEL=qwen3.5:4b`. Tryb myślenia wyłączony
(`reasoning_effort: "none"`; na `/v1` Ollama ignoruje `think`, pomiar K1), odpowiedź jako JSON
wymuszony schematem `FormAnalysis`. Skany JPG/PNG czyta OCR. Obraz w modelu to tylko zapas:
w K1 był wolniejszy i gorszy niż tekst. Bielik-4.5B-v3 to alternatywa: zmiana tylko `LLM_MODEL`.

Eden AI (`edenai`): wyjątek dopuszczony przez COI (D9), jedyne zewnętrzne API w produkcie.
Włącza go człowiek. Klucz leży poza repozytorium i poza dostępem agentów. Model docelowy to
Qwen3.5-9B (Apache-2.0, wagi otwarte, w katalogu Eden AI m.in. `ovhcloud/Qwen3.5-9B`). Przez
Eden AI idą tylko modele otwarte, nigdy zamknięte. Trasę i limity czasu ustali pomiar z K3.1.
Do tego czasu kod woła tylko Ollamę.

Cel czasu to około 180 s na cały proces podczas live demo, granica orientacyjna 200 s (D11).
Lokalny Qwen na samym CPU go nie spełnia (K1: 238–344 s na jedną próbę). Obrona działa na x86
bez dedykowanego GPU; RAM i stabilność internetu są niepotwierdzone (D12).

## Acceptance test

frontend/tests/e2e/acceptance.spec.ts walks the demo flow. It is locked after review.
Obejmuje kroki 1–8. Krok 9 to polecenie, nie ekran, więc nie ma go w teście e2e.
