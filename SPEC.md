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
przez API, licencje copyleft, trwały zapis plików.

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
   JSON spełnia schemat COI i Reguły techniczne (min. 2 strony, ostatnia FINISH, pola tylko
   w sekcjach, `flow` łączy strony). Pkt 3.2; kroki 2, 3, 8. Właściciel: do uzupełnienia.
2. Treść JSON-a według SZABLONY_SEKCJI.md: strona „Dane” z sekcji standardowych, strony tematyczne
   od AI, „Kontakt i zgody”, „Strona końcowa”. Dane inicjalne, słowniki, warunki SHOW, walidatory
   z rozdz. 5. Pkt 3.2, rozszerzenia I i III; kroki 4, 5. Właściciel: do uzupełnienia.
3. Ekran „Wczytaj formularz”: wybór pliku, postęp, komunikat błędu, „Pokaż JSON”, „Pobierz JSON”.
   Rozszerzenie IV; kroki 1–3, 7, 8. Właściciel: do uzupełnienia.
4. „Podgląd eUsługi” z JSON-a: strony, sekcje i pola, działające warunki SHOW, walidatory
   REQUIRED, PESEL, NIP, REGON, ZIP_CODE, EMAIL przy „Dalej”. Rozszerzenia V i VI; kroki 4–6.
   Właściciel: do uzupełnienia.
5. Wyniki i zgodność: jedno polecenie tworzy JSON-y formularzy z folderów 2–4 i 6–9 (do oddania).
   Liczy też procent pól zgodnych ze wzorcami z folderów 1 i 5, osobno dla każdego formatu.
   Krok 9. Właściciel: do uzupełnienia.

## Later (only if every Must is green)

JWT na API (parametry z pkt 5) · nowy słownik (rozszerzenie II) · wiele plików naraz w UI ·
strony alternatywne (przepływ nieliniowy).

## Out (said out loud, so nobody builds it)

Edycja formularza w UI (kreator) · konta, logowanie, historia analiz, zapis plików · wysyłka
wypełnionego formularza i integracja z systemem docelowym · wersja w Javie · zewnętrzne API modeli.

## API contract

`GET /health` → 200 `{"status": "ok"}` (już jest).

`POST /api/forms`: `multipart/form-data`, jedno pole `file`.

```bash
curl -F "file=@Wniosek o wydanie zaświadczenia.pdf" http://localhost:8000/api/forms
```

- 200: ciało to sam JSON formularza (Field contract), bez opakowania.
- 400 `{"detail": "Nazwa pliku jest za długa albo ma niedozwolone znaki."}`
- 413 `{"detail": "Plik jest za duży. Limit to 10 MB."}`
- 415 `{"detail": "Zawartość pliku nie pasuje do rozszerzenia .pdf."}`, a dla innego rozszerzenia
  `{"detail": "Ten typ pliku nie jest obsługiwany. Wybierz PDF, DOC, DOCX, ODS, XLSX, JPG albo PNG."}`
- 503 `{"detail": "Model AI nie odpowiada. Spróbuj ponownie za chwilę."}`

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

Prawdziwe: kontrola pliku, odczyt 8 formatów (skany przez OCR), otwarty model uruchomiony lokalnie
w docker compose, budowa JSON-a, podgląd, walidatory, tabela zgodności.
Atrapy: wartości danych inicjalnych (`MLPZ.*`) i słowników (`Kraje`, `TERYT_4G_DOWODOWY`) w podglądzie
pochodzą z `frontend/src/data/demo.ts`. PESEL, NIP i REGON mają tam poprawne sumy kontrolne.
Testy nie wołają modelu. Przy ustawionym `LLM_FIXTURE` moduł `backend/app/llm.py` zwraca
`backend/tests/fixtures/fields.json`, a `playwright.config.ts` ustawia tę zmienną dla API.
Ten fixture opisuje wniosek, który można złożyć w imieniu innej osoby (`WNIOSKODAWCY` = OBA).
Materiały COI (zip z Discorda) leżą w `materialy/`, poza gitem. Foldery 1 i 5 to wzorce,
foldery 2–4 i 6–9 to formularze do oceny.

## Model

Qwen3.5-4B (`qwen3.5:4b` w Ollamie, Q4_K_M, ok. 3,4 GB, Apache-2.0), uruchomiony lokalnie:
serwis `ollama` w docker compose z jawną wersją obrazu, model w wolumenie. API woła go tylko
z `backend/app/llm.py` przez interfejs zgodny z OpenAI: `LLM_BASE_URL=http://ollama:11434/v1`,
`LLM_MODEL=qwen3.5:4b`. Tryb myślenia wyłączony (`think: false`), odpowiedź jako JSON wymuszony
schematem `FormAnalysis`. Model czyta też obrazy, więc skany JPG/PNG mogą trafić do niego
bezpośrednio, z OCR jako zapasem. Bielik-4.5B-v3 to alternatywa: zmiana tylko `LLM_MODEL`.
Modele dostępne wyłącznie przez API nie są używane w produkcie (Treść pkt 5).

## Acceptance test

frontend/tests/e2e/acceptance.spec.ts walks the demo flow. It is locked after review.
Obejmuje kroki 1–8. Krok 9 to polecenie, nie ekran, więc nie ma go w teście e2e.
