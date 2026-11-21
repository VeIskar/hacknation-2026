# Brief dla zespołu – Cyfryzacja formularzy (COI)

Stan: sob. 12:15. Jedna strona, żebyśmy wszyscy mieli ten sam obraz.

## 1. Co budujemy – w jednym zdaniu

**REST API: wrzucasz plik formularza (PDF/DOC/DOCX/ODS/XLSX/JPG/PNG) → dostajesz JSON w formacie Generatora Formularzy COI**, gotowy do importu. Do tego frontend (upload + podgląd JSON + podgląd eUsługi) i Docker.

Ograniczenia: **lokalny model** (żadnych API typu OpenAI/Claude w produkcie), Python 3.14+, tylko licencje bez copyleftu, Docker z użytkownikiem bez uprawnień, JWT, walidacja pliku (MIME, nazwa, rozmiar).

## 2. Najważniejsze odkrycie z materiałów

Papierowy wniosek o numer porządkowy ma **4 pola merytoryczne** (miejscowość, ulica, działka, obręb). Wzorcowy JSON COI ma **69 elementów**. Reszta to **stałe sekcje ze Standardów COI**: urząd, podmiot wniosku, Twoje dane z rejestru, adresy, pełnomocnictwo, opłata skarbowa, kontakt, zgoda, podgląd.

Wniosek: **~90% JSON-a generuje kod z szablonów. AI robi tylko dwie rzeczy:** ustala kilka parametrów (tytuł, adresat, kto może składać) i wyciąga z papieru pola przedmiotu wniosku.

Efekt: mały lokalny model wystarcza, wynik jest zawsze poprawny formalnie, a koszt niski (20% oceny to „potencjał wdrożeniowy, w tym koszt”).

## 3. Architektura (moduły i kontrakty między nimi)

```
 [1] API + walidacja pliku          FastAPI, JWT, MIME vs rozszerzenie, nazwa, rozmiar
        │ bytes + format
 [2] Ekstrakcja → Dokument          tekst + bloki + tabele; OCR dla JPG/PNG i DOCX-ów-obrazków
        │ ExtractedDocument
 [3] Analiza AI (lokalny LLM)       krótkie wywołania, wymuszony JSON
        │ FormAnalysis               ← GŁÓWNY KONTRAKT (niżej)
 [4] Generator                      szablony (SZABLONY_SEKCJI.md) + strony przedmiotu
        │ FormDefinition (JSON COI)
 [5] Linter / autopoprawa           JSON Schema + 12 reguł technicznych
        │
     Odpowiedź API                   JSON COI (+ raport zgodności)

 Frontend: upload → podgląd JSON → podgląd eUsługi (renderer z jsonatą)
```

### Kontrakt `FormAnalysis` (wyjście AI, wejście generatora) – przykład dla nadpłaty

```json
{
  "title": "Wniosek o stwierdzenie nadpłaty podatku",
  "addressee": { "type": "URZAD", "name": "Urząd Gminy Ulan-Majorat" },
  "applicants": "BOTH",
  "signature": true,
  "subject_pages": [
    { "title": "Informacje o nadpłacie",
      "sections": [
        { "title": "Informacje o nadpłacie", "description": "",
          "fields": [
            { "label": "Podatek, którego dotyczy nadpłata", "type": "TEXT_FIELD", "required": true },
            { "label": "Kwota", "type": "NUMBER", "required": true },
            { "label": "Uzasadnienie", "type": "TEXTAREA", "required": true,
              "description": "Uzasadnij dlaczego Twoim zdaniem powstała nadpłata i z czego wynika jej wysokość." } ] },
        { "title": "Rozliczenie nadpłaty",
          "fields": [
            { "label": "Wybierz, co mamy zrobić z nadpłatą", "type": "RADIO", "required": true,
              "options": ["Zaliczyć na poczet przyszłego zobowiązania podatkowego", "Zwrócić przelewem na rachunek bankowy"] },
            { "label": "Nazwa podatku", "type": "TEXT_FIELD", "required": true,
              "show_if": { "field": "Wybierz, co mamy zrobić z nadpłatą", "equals": "Zaliczyć na poczet przyszłego zobowiązania podatkowego" } },
            { "label": "Numer rachunku", "type": "TEXT_FIELD", "required": true,
              "show_if": { "field": "Wybierz, co mamy zrobić z nadpłatą", "equals": "Zwrócić przelewem na rachunek bankowy" } } ] },
        { "title": "Korekta deklaracji",
          "description": "Załącz poprawioną deklarację podatkową, z której wynika prawidłowa, niższa wysokość zobowiązania podatkowego, a w konsekwencji nadpłata.",
          "fields": [ { "label": "Plik deklaracji podatkowej", "type": "FILE_UPLOADER", "required": true } ] } ] } ],
  "statements": []
}
```
AI nie zna UUID-ów, siatki, jsonaty ani techName – to wszystko dokłada generator. Dzięki temu AI produkuje mało tokenów, a format COI jest zawsze poprawny.

## 4. Role

> **Aktualny podział z imionami (Paweł, Marcin, Mikołaj) i kolejność zadań: `DELEGACJA.md` – ma pierwszeństwo przed tabelą niżej.**

| Kto | Moduły | Pierwsze zadanie |
|---|---|---|
| **A – backend** | [1] API, [5] linter, Docker, README | endpoint z walidacją pliku + linter (służy też do testów) |
| **B – AI** | [2] ekstrakcja, [3] analiza AI, skrypt eval | ekstrakcja tekstu z 8 formatów + pierwsze wywołanie modelu → `FormAnalysis` |
| **Paweł – produkt** | [4] generator szablonów (z agentem, wg `SZABLONY_SEKCJI.md`), frontend + renderer, zestaw testowy, prezentacja, film | generator: `FormAnalysis` → JSON COI, sprawdzony na wzorcu nadpłaty |
| **Architekt (ziomek)** | spójność całości, kontrakty, wybór modelu i runtime, Docker compose | zatwierdza kontrakt `FormAnalysis` (pkt 3) |

Generator da się przetestować **bez AI**: ręcznie wpisany `FormAnalysis` dla nadpłaty → generator → porównanie z wzorcem COI. To pierwszy kamień milowy, niezależny od modelu.

## 5. Kamienie milowe

| Godz. | Co działa |
|---|---|
| 14:00 | Generator: ręczny `FormAnalysis` nadpłaty → JSON zgodny ze wzorcem COI (szablon 100%) |
| 15:00 | API przyjmuje plik, waliduje, zwraca JSON z generatora; eval liczy M0, M1 |
| 17:00 | AI: z PDF/DOCX nadpłaty i numeru porządkowego powstaje `FormAnalysis`; eval liczy M3 |
| **20:00** | **Draft w systemie** (nazwa, repo, stolik, opis) |
| noc | wszystkie formaty (OCR), formularze 2–9, warunki, słowniki, renderer |
| 7:00 | zamrożenie kodu → JSON-y do oddania, film ≤3 min, PDF ≤10 slajdów |

## 6. Dokumenty

- `SZABLONY_SEKCJI.md` – dokładny format JSON COI + wszystkie sekcje szablonowe + zasady przedmiotu wniosku
- `docs/ZESTAW_TESTOWY.md` – zestaw testowy i miary
- `Materiały do zadania dla Uczestników/1.` i `5.` – wzorce COI (źródło prawdy)

## 7. Pytania do mentora (otwarte)

1. Wzorce mają puste `validation` – czy dodawanie walidatorów (REQUIRED, PESEL, NIP…) jest OK?
2. Plik `.JPE` w formularzu 7 – obsługiwać jako JPEG?
3. Do oddania: 1 JSON na formularz (7) czy na każdy plik (56)?
