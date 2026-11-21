# Zestaw testowy – jak mierzymy jakość

Cel: po każdej zmianie w pipeline jedną komendą zobaczyć, czy jest lepiej czy gorzej. W finale COI odpala rozwiązanie na **nowych** plikach, więc liczy się odporność, a nie dopasowanie do jednego formularza.

## 1. Co mamy

| Grupa | Formularze | Pliki | Wzorzec JSON | Do czego |
|---|---|---|---|---|
| **A. Złote pary** | 1 Numer porządkowy, 5 Nadpłata | 2 × 8 formatów = 16 | **tak (od COI)** | pomiar dokładności |
| **B. Do oceny** | 2, 3, 4, 6, 7, 8, 9 | 7 × 8 formatów = 56 | nie | poprawność, spójność, czas + **pliki do oddania** |

Podział ról w grupie A: **5 (nadpłata) = zbiór roboczy** – wolno go używać w promptach jako przykład. **1 (numer porządkowy) = zbiór kontrolny** – nie wklejamy go do promptów i nie stroimy pod niego. Jego wynik mówi, jak poradzimy sobie z nowym plikiem w finale.

## 2. Struktura katalogu

Uwaga (D5 w `DECISIONS.md`): plików COI nie commitujemy. Dane wejściowe i wzorce czytamy z `materialy/` (poza gitem), a `tests/data/` poniżej to układ logiczny, nie katalog w repo.

```
tests/data/
  golden/
    01_numer_porzadkowy/
      input/   ← 8 plików z folderu „1. …” (bez wizualizacji .docx)
      expected.json   ← wzorzec COI
    05_nadplata/
      input/   ← 8 plików z folderu „5. …”
      expected.json
  eval/
    02_zwrot_oplaty_skarbowej/input/   ← 8 plików
    03_zaswiadczenie/input/
    04_swietlica/input/
    06_pas_drogowy/input/
    07_psy_agresywne/input/            ← uwaga: .PDF .DOC .JPE (wielkie litery, .JPE)
    08_deklaracja_odpady/input/        ← DOCX zawiera tylko obraz → OCR
    09_stypendium_sportowe/input/      ← 3 wnioski w 1
    (opcjonalnie) <id>/checklist.md   ← ręczna lista pól przedmiotu wniosku
results/<data_godzina>/
  <form>/<plik>.json                   ← wynik API
  report.md                            ← tabela z miarami
```

## 3. Miary (od najważniejszej)

| # | Miara | Grupa | Jak liczona | Cel |
|---|---|---|---|---|
| M0 | **Działa** | A+B | API zwróciło 200 i JSON dla każdego z 72 plików | 72/72 |
| M1 | **Poprawny format** | A+B | JSON Schema + nasz linter 12 reguł technicznych (min. 2 strony, FINISH, pola w sekcjach, flow, jsonata wskazuje istniejące strony i pola) | 100% |
| M2 | **Szablon zgodny** | A | sekcje strony „Dane”, „Kontakt…”, „Strona końcowa” – porównanie techName sekcji i pól ze wzorcem | 100% (to kod, nie AI) |
| M3 | **Przedmiot wniosku – pola** | A | dopasowanie pól wynik ↔ wzorzec po etykiecie (podobieństwo tekstu ≥ 0,7) i typie; precision, recall, F1 | F1 ≥ 0,8 |
| M4 | **Typy i opcje** | A | wśród dopasowanych: % zgodnych typów; F1 opcji RADIO/CHECKBOX/SELECT | ≥ 90% |
| M5 | **Warunki** | A | czy pola zależne mają SHOW na tę samą opcję co we wzorcu (porównanie zachowania, nie tekstu jsonaty) | wszystkie |
| M6 | **Spójność formatów** | A+B | ten sam formularz w 8 formatach → czy wychodzi ten sam zestaw pól (F1 każdego formatu względem wersji z DOCX/PDF) | ≥ 0,9; wskazuje, który ekstraktor kuleje |
| M7 | **Czas** | A+B | sekundy na plik, osobno ekstrakcja i AI | < 60 s na plik na laptopie |
| M8 | **Checklista** | B (3, 4, 6) | ręczna lista pól przedmiotu – ile znaleziono | ≥ 80% |

M6 to nasza najmocniejsza miara: nie potrzebuje wzorca, a od razu pokazuje problemy z OCR i konwersją DOC/ODS/XLSX. W prezentacji to dobry slajd: „ten sam wniosek w 8 formatach daje ten sam formularz”.

## 4. Raport (`results/…/report.md`) – wygląd

```
Formularz              | Format | M0 | M1 | M3 F1 | M4 typy | M5 warunki | M6 spójność | Czas
05_nadplata (roboczy)  | pdf    | ✅ | ✅ | 0.92  | 100%    | 2/2        | –           | 18 s
05_nadplata            | jpg    | ✅ | ✅ | 0.85  | 92%     | 1/2        | 0.88        | 41 s
01_numer (kontrolny)   | docx   | ✅ | ✅ | 1.00  | 100%    | –          | –           | 12 s
...
SUMA                   |        | 72/72 | 72/72 | śr. 0.89 | ... 
```

## 5. Pliki do oddania (wynikowe JSON-y)

Z grupy B: **jeden JSON na formularz** (7 plików) z najlepszego źródła (zwykle DOCX lub PDF), nazwy np. `02_wniosek_o_zwrot_oplaty_skarbowej.json`. Pozostałe formaty jako dowód spójności (opcjonalnie). Zapytać mentora, czy chcą 7 czy 56 plików.

## 6. Kto co robi

| Kto | Zadanie | Kiedy |
|---|---|---|
| Ty | rozłożyć pliki do `tests/data/` (kopie, oryginały zostają w „Materiałach”); checklisty dla 3, 4, 6 (po ~10 min) | teraz |
| B | skrypt `eval`: puszcza wszystkie pliki przez API, liczy M0–M7, pisze `report.md` | do 15:00 (najpierw M0, M1, M7; potem M3–M6) |
| A | linter (M1) jako moduł aplikacji – ten sam kod naprawia wynik w pipeline i liczy miarę | do 15:00 |
| wszyscy | przed każdym mergem: `make eval` i porównanie z poprzednim raportem | cały czas |
