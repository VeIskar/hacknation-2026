# Testy zapisanych wyników F2–F9

Stan na `origin/main` 69e3f11 (22.11.2026). Testy nie wołają modelu. Nie używają dokumentów źródłowych.

## Jak uruchomić

```
bash scripts/gate.sh api tests/test_wyniki.py           # pytest: linter, struktura, SHA-256, raport
cd frontend && npx playwright test wyniki.spec.ts       # Playwright: podgląd i pobranie (REPLAY)
```

## Wyniki

| Plik | Jest | SHA-256 | Pochodzenie | Linter | Renderer (krok 1) | SHOW / walidatory (linter) | Tryb testu | Dla jury |
|---|---|---|---|---|---|---|---|---|
| F2 | tak | `14df810c…d3b876b1` | Eden AI, zgodny z report.md | PASS | PASS | PASS / PASS | REPLAY | tak |
| F3 | tak | `3e4e06fe…0094fe8c` | Eden AI, zgodny z report.md | PASS | PASS | PASS / PASS | REPLAY | tak |
| F4 | tak | `cb34787b…cf4d026e` | Eden AI, zgodny z report.md | PASS | PASS | PASS / PASS | REPLAY | tak |
| F5 | tak | `5f0ee452…93607220` | **nieznane**, niezgodny z report.md | PASS | PASS | PASS / PASS | REPLAY | nie (formularz referencyjny) |
| F6 | tak | `22dfcdb1…ba65c82e` | Eden AI, zgodny z report.md | PASS | PASS | PASS / PASS | REPLAY | tak |
| F7 | tak | `f4ee0d2d…7e4f274c` | Eden AI, zgodny z report.md | PASS | PASS | PASS / PASS | REPLAY | tak |
| F8 | tak | `02dad626…7e5a7ab5` | Eden AI, zgodny z report.md | PASS | PASS | PASS / PASS | REPLAY | tak |
| F9 | tak | `eab0cad5…88ef7ceb` | Eden AI, zgodny z report.md | PASS | PASS | PASS / PASS | REPLAY | tak |

Pełne skróty SHA-256 są w `backend/tests/test_wyniki.py` (słownik `SHA256`).

**Wynik automatyczny: 8/8 plików przechodzi linter i podgląd. Pochodzenie z Eden AI potwierdzone dla 7/8.**

## Co sprawdzają testy

- pytest (`backend/tests/test_wyniki.py`), produkcyjny `app.lint.check`:
  - odczyt JSON, SHA-256 i zapis kanoniczny (brak regresji pliku);
  - linter: 0 błędów, w tym odwołania i składnia warunków SHOW;
  - strony MAIN i FINISH, sekcje, pola, unikalne `id`;
  - walidatory z listy lintera, słowniki z `app.quality.COI_DICTIONARIES`;
  - liczby SHOW, walidatorów i słowników równe wierszom w `report.md` (7 plików, bez F5);
  - testy negatywne z konkretnym komunikatem lintera: złe odwołanie SHOW, zła składnia warunku,
    nieznany walidator, brak strony FINISH.
- Playwright (`frontend/tests/e2e/wyniki.spec.ts`), odpowiedź API podmieniona na zapisany plik:
  - podgląd się otwiera, „Krok 1 z N” zgadza się z liczbą stron w JSON;
  - „Dalej” przechodzi dalej albo pokazuje błędy walidacji pierwszej strony;
  - brak wyjątków strony przy liczeniu SHOW i walidatorów na pierwszej stronie;
  - pobrany JSON jest identyczny bajt w bajt z plikiem.

## Trzy różne twierdzenia

1. **Historyczny przebieg Eden AI.** `report.md` opisuje przebieg `flexai/Qwen3.5-9B@eu`, wszystkie
   wiersze OK, lint 0. Pliki F2–F4 i F6–F9 zgadzają się z nim co do SHOW, walidatorów i słowników.
2. **Powtarzalność na zapisanych plikach.** To mierzą nowe testy: 8/8 PASS, bez modelu.
3. **Skuteczność nowych wywołań modelu.** Tego testy NIE mierzą. Model nie jest deterministyczny.
   W innej serii wystąpił błąd 503.

## Czego NIE potwierdzono

- Pochodzenia `wyniki/F5.coi.json`. Plik nie zgadza się z wierszem F5 w `report.md`:
  SHOW 1 zamiast 14, REQUIRED 6 zamiast 10, brak ZIP_CODE i słowników.
  Prawdziwy wynik F5 z tego przebiegu nie jest w repozytorium.
- Przejścia przez wszystkie strony w podglądzie. Test sprawdza pierwszy krok nawigacji.
  SHOW i walidatory na dalszych stronach sprawdza tylko linter, nie przeglądarka.
- Że „Dalej” przechodzi dalej. Przy polach wymaganych na stronie 1 test widzi tylko blokadę.
- Plików `F*.analysis.json` (odpowiedzi modelu). Nie są zapisane w repozytorium.
- Nowego przebiegu Eden AI. Nie uruchamiano płatnych wywołań.
