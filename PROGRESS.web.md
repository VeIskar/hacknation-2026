# PROGRESS (area: web, directory frontend/)

## State

(rewritten by /hn-stan before sleep, at a usage limit, before switching agents)

## Plan

F1 (Must 3: ekran „Wczytaj formularz”, oczekiwanie, błędy, pokaż i pobierz JSON), kierunek K1 Zakreślacz:

1. `DECISIONS.md`: pdfjs-dist, kroje. Kroje do `frontend/src/fonts/` z `OFL.txt`.
2. `playwright.config.ts`: `LLM_FIXTURE` dla serwera API (prośba api).
3. `src/api.ts` (`POST /api/forms`, `detail` bez zmian) i `src/format.ts` (czas, rozmiar, nazwa pliku, liczby z JSON-a) z testami vitest.
4. `src/App.tsx` + `src/screens/`: wczytanie (prawdziwy input w strefie), oczekiwanie (pierwsza strona pliku, czas, jedno zdanie), wynik (pokaż i pobierz JSON), błąd `role="alert"`.
5. `src/index.css`, `src/warsztat.css`: tokeny i wygląd warsztatu.
6. `frontend/scripts/look.mjs`: zrzuty 1440 i 390 px każdego stanu, krok 8 i pobranie JSON-a.
7. Dowód: vitest, `acceptance.spec.ts` przechodzi kroki 1–3 i pada na kroku 4, a11y i klawiatura zielone na „/”.

F2 (Must 4: „Podgląd eUsługi” z JSON-a, SHOW, walidatory przy „Dalej”):

1. `DECISIONS.md`: jsonata (MIT), potem `npm install`.
2. `src/data/demo.ts`: dane inicjalne `MLPZ.*`, słowniki `Kraje` i `TERYT_4G_DOWODOWY`, przykładowy NIP i REGON.
3. `src/preview/`: `answers.ts` (odpowiedzi od `defaultValue`), `conditions.ts` (SHOW przez jsonata na kopii z `__userAnswer`), `validators.ts` (REQUIRED, PESEL, NIP, REGON, ZIP_CODE, EMAIL), `richText.ts` (opisy HTML przez białą listę znaczników). Testy vitest obok.
4. `src/preview/Preview.tsx` i `Field.tsx`: kroki „Krok 2 z 4”, sekcje jako regiony, pola według DESIGN „Forms”, podsumowanie błędów, „Dalej” i „Wstecz”, strona FINISH.
5. `src/eusluga.css`: strefa eUsługi na tokenach `ink/muted/paper/line/action/error`, bez stylu warsztatu.
6. `scripts/look.mjs`: stany Dane, „Innej osoby”, błąd walidacji, strona końcowa w 1440 i 390 px z axe.
7. Dowód: `acceptance.spec.ts` cały zielony, a11y i klawiatura zielone, `LOOK: PASS`, każda nowa asercja widziana na czerwono.

F2.5B (kierunek „Jasny urząd” z DESIGN.md, wzorce w `frontend/design/jasny-urzad/`; układ z F2.5A zostaje):

1. `src/index.css`: tokeny (granat, akcja, szare pole, linie, błąd), jeden krój Atkinson, obrys fokusu granatowy; bez żółtego i bez Brygady.
2. `src/components/AppBar.tsx` i `icons.tsx`: granatowy pasek, linia „Wersja testowa”, etapy z tekstem „Gotowe / Teraz / Później”, na telefonie „Etap 1 z 3”.
3. `src/warsztat.css`: przyciski (główny z dolnym cieniem, drugi z ramką, odsyłacz), strefa pliku i panel oczekiwania na szarym polu, kartka z jedynym cieniem, panel boczny z ramką.
4. `src/eusluga.css` i `src/preview/Field.tsx`: pola 48 px, pole z rejestru z kłódką, lista z własną strzałką, błąd z ikoną, bez paska z boku.
5. `scripts/look.mjs`: przepływ dla folderu 9 na JSON-ie z `analysis_form9.json`, kontrola zgodności liczb, tytułu i nazwy pliku.
6. Dowód: `gate.sh web`, `test:e2e`, `LOOK: PASS`, zrzuty 1440 i 390 px.

## Requests

(one line per change you need from another area: who asks, what, why)

- web → lider (kontrakt, F1): front nie wysyła nagłówka `Authorization`. Przy `JWT_ENABLED=true` każde wczytanie pliku skończy się 401 (SPEC „API contract”). SPEC nie mówi, skąd przeglądarka ma wziąć token. Potrzebna decyzja: demo z `JWT_ENABLED=false` albo sposób przekazania tokenu do frontu.

## Log

(one line per step: done / next / blocker)

- F0 (etap 0, kierunek warsztatu): done trzy makiety ekranu wyniku w `frontend/design/` (`k1-zakreslacz.html`, `k2-kalka.html`, `k3-sukno.html`, poza gitem) i zrzuty 1440 i 390 px w `frontend/shots/etap0/`; kroje OFL-1.1 sprawdzone przez `fc-query` (Atkinson Hyperlegible Next 2.001, Barlow Semi Condensed 1.408, Brygada 1918 3.006: komplet polskich znaków), kontrast palet zmierzony, nic w `src/`; `bash scripts/gate.sh` → `GATE: PASS (web)`; e2e stan wyjściowy: 3 passed, 1 failed (`acceptance.spec.ts:32`, brak h1 „Wczytaj formularz”, aplikacja to jeszcze szablon) / next człowiek wybiera kierunek, potem F1 / blocker brak; do F1: `origin/main` jest 7 commitów dalej (`1c3ebd2`), `playwright.config.ts` nie ustawia `LLM_FIXTURE` (prośba api w `PROGRESS.api.md`), `frontend/design/` nie jest ignorowany przez git.
- F1 (Must 3, kierunek „Zakreślacz”): done ekran „Wczytaj formularz” (prawdziwy input w strefie upuszczania), oczekiwanie (pierwsza strona pliku przez pdfjs-dist, czas, jedno zdanie, „Przerwij analizę”), błąd API w `role="alert"` z `detail` bez zmian, wynik z „Pokaż JSON” i „Pobierz JSON”; kroje Atkinson Hyperlegible Next i Brygada 1918 (tylko tytuły) w `frontend/src/fonts/`; `LLM_FIXTURE` w `playwright.config.ts` (z pustą zmienną test pada na linii 41, z atrapą na 43); `frontend/scripts/look.mjs` → `LOOK: PASS` (6 stanów × 1440 i 390 px, axe bez naruszeń, krok 8, pobranie `.json`); vitest 14 testów, 19/19 mutacji wykrytych; `gate.sh` → `GATE: PASS (web)`; e2e 3 passed, 1 failed: `acceptance.spec.ts:43` (region „Twoje dane”, to F2); recenzje `reviewer` i `a11y`: naniesione (worker pdfjs jako `.js`, sygnał przerwania w teście, fokus na komunikacie błędu, `aria-invalid`, tytuł wniosku jako h2, zapas dla `:has()`) / next F2 podgląd eUsługi / blocker brak; odłożone: `wasmUrl` dla pdfjs (skany JBIG2, JPX, CCITT w PDF-ie dadzą pustą stronę; w 13 PDF-ach COI takich nie ma), `standardFontDataUrl`, decyzja o JWT (Requests).
- F2 (Must 4, „Podgląd eUsługi”): done podgląd z JSON-a COI w `frontend/src/preview/`: strony jako „Krok N z 4”, sekcje jako regiony z tytułem, pola według DESIGN „Forms” w strefie `eusluga.css` (bez stylu warsztatu); warunki SHOW przez jsonata 2.2.2 na kopii z `__userAnswer` (pole i sekcja bez spełnionego warunku nie istnieją w DOM, odpowiedź ukrytego pola nie steruje innymi warunkami); odpowiedzi od `defaultValue`, dane `MLPZ.*` i słowniki z `src/data/demo.ts`; walidatory REQUIRED, PESEL, NIP, REGON, ZIP_CODE, EMAIL przy „Dalej” z podsumowaniem błędów, fokusem i `aria-invalid`; „Dalej” i „Wstecz”, strona końcowa z przeglądem odpowiedzi i „Zmień”; opisy HTML przez białą listę znaczników, bez `dangerouslySetInnerHTML`; vitest 44 testy, 33/33 mutacji wykrytych; `gate.sh` → `GATE: PASS (web)`; e2e 4 passed (cały `acceptance.spec.ts`); `look.mjs` → `LOOK: PASS` (10 stanów × 1440 i 390 px, axe bez naruszeń; 11 nowych kontroli widzianych na czerwono); recenzje `reviewer` i `a11y`: naniesione (pola ukrytej sekcji w zbiorze ukrytych, łańcuch SHOW, błąd i fokus przy kilku zgodach, `role="alert"` wewnątrz ramki z fokusem, cele 44 px w podsumowaniu i linkach, obrys ikony kalendarza, łamanie długich słów, pole pliku po polsku) / next F3 po zgodzie człowieka / blocker brak; odłożone: słowniki inne niż Kraje i TERYT dają pustą listę, pole RADIO tylko do odczytu jest `disabled`, sam tekst 200% przy 1440 px rozpycha kolumnę papieru (`warsztat.css`), `origin/main` jest 3 commity dalej (`fa76e6d`), scalenie po commicie F2.
- F2.5A i F2.5B (układ warsztatu i kierunek „Jasny urząd”): done A: pasek etapów, strefa pliku z „Wybierz plik”, papier dopiero po wyborze pliku (proporcje strony, render w `devicePixelRatio`, miniatury, poniżej 1200 px zwinięty do „Pokaż oryginał”), wynik w trzech kolumnach z panelem „Karta” i „JSON”; B: tokeny „Jasnego urzędu” w `src/index.css`, jeden krój Atkinson, granatowy pasek usługi z linią „Wersja testowa”, etapy z tekstem „Gotowe / Teraz / Później” (na telefonie „Etap 1 z 3”), przyciski (główny z dolnym cieniem, drugi z ramką, odsyłacz), pola 48 px, pole z rejestru z kłódką i podpowiedzią „Przykładowe dane z rejestru”, lista z własną strzałką, błąd z ikoną, bez żółtego i bez paska z boku; `look.mjs` na PDF-ach z folderów 5 i 9, folder 9 na JSON-ie z `analysis_form9.json` (6 stron, 38 sekcji, 113 pól), kontrola zgodności karty, JSON-a, tytułu i nazwy pliku; `gate.sh web` → `GATE: PASS (web)`, 44 testy; e2e 4 passed; `LOOK: PASS`; nowe kontrole widziane na czerwono / next F3a ekrany Wczytaj i Analiza według wzorców / blocker brak; odłożone: układ ekranów z wzorców (F3a, F3b), podświetlanie JSON-a (F3b), źródła na papierze (F4), `reviewer` i `a11y` nie były uruchamiane w tym kroku.
