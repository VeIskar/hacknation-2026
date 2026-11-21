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

## Requests

(one line per change you need from another area: who asks, what, why)

- web → lider (kontrakt, F1): front nie wysyła nagłówka `Authorization`. Przy `JWT_ENABLED=true` każde wczytanie pliku skończy się 401 (SPEC „API contract”). SPEC nie mówi, skąd przeglądarka ma wziąć token. Potrzebna decyzja: demo z `JWT_ENABLED=false` albo sposób przekazania tokenu do frontu.

## Log

(one line per step: done / next / blocker)

- F0 (etap 0, kierunek warsztatu): done trzy makiety ekranu wyniku w `frontend/design/` (`k1-zakreslacz.html`, `k2-kalka.html`, `k3-sukno.html`, poza gitem) i zrzuty 1440 i 390 px w `frontend/shots/etap0/`; kroje OFL-1.1 sprawdzone przez `fc-query` (Atkinson Hyperlegible Next 2.001, Barlow Semi Condensed 1.408, Brygada 1918 3.006: komplet polskich znaków), kontrast palet zmierzony, nic w `src/`; `bash scripts/gate.sh` → `GATE: PASS (web)`; e2e stan wyjściowy: 3 passed, 1 failed (`acceptance.spec.ts:32`, brak h1 „Wczytaj formularz”, aplikacja to jeszcze szablon) / next człowiek wybiera kierunek, potem F1 / blocker brak; do F1: `origin/main` jest 7 commitów dalej (`1c3ebd2`), `playwright.config.ts` nie ustawia `LLM_FIXTURE` (prośba api w `PROGRESS.api.md`), `frontend/design/` nie jest ignorowany przez git.
- F1 (Must 3, kierunek „Zakreślacz”): done ekran „Wczytaj formularz” (prawdziwy input w strefie upuszczania), oczekiwanie (pierwsza strona pliku przez pdfjs-dist, czas, jedno zdanie, „Przerwij analizę”), błąd API w `role="alert"` z `detail` bez zmian, wynik z „Pokaż JSON” i „Pobierz JSON”; kroje Atkinson Hyperlegible Next i Brygada 1918 (tylko tytuły) w `frontend/src/fonts/`; `LLM_FIXTURE` w `playwright.config.ts` (z pustą zmienną test pada na linii 41, z atrapą na 43); `frontend/scripts/look.mjs` → `LOOK: PASS` (6 stanów × 1440 i 390 px, axe bez naruszeń, krok 8, pobranie `.json`); vitest 14 testów, 19/19 mutacji wykrytych; `gate.sh` → `GATE: PASS (web)`; e2e 3 passed, 1 failed: `acceptance.spec.ts:43` (region „Twoje dane”, to F2); recenzje `reviewer` i `a11y`: naniesione (worker pdfjs jako `.js`, sygnał przerwania w teście, fokus na komunikacie błędu, `aria-invalid`, tytuł wniosku jako h2, zapas dla `:has()`) / next F2 podgląd eUsługi / blocker brak; odłożone: `wasmUrl` dla pdfjs (skany JBIG2, JPX, CCITT w PDF-ie dadzą pustą stronę; w 13 PDF-ach COI takich nie ma), `standardFontDataUrl`, decyzja o JWT (Requests).
