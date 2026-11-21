# PROGRESS (lead: whole repository, integration)

## State

(rewritten by /hn-stan before sleep, at a usage limit, before switching agents)

## Plan

(at most 10 lines for the current step)

Krok L1 (lider, gałąź `lead/mentor-2111`): dokumenty po rozmowie z mentorem COI (2026-11-21), bez zmian w kodzie.

- `DECISIONS.md`: D8 (trzy zasady sensownej cyfryzacji potwierdzone przez mentora) i D9 (Eden AI; treść D9 zmieniła się w kroku L2).
- `SPEC.md`: „Model” (`reasoning_effort: "none"`, skany przez OCR, D9), Must 1 (wyjątki `.doc` z treścią DOCX i `.jpe`), fixture (`applicants`, `proxy`).
- `DELEGACJA.md`: stan, rozdz. 2.1–2.3 (`ApplicantData`, format z `validate_upload`), K1–K3, rozdz. 4, rozdz. 6 pkt 5 (LibreOffice), rozdz. 7.
- `SZABLONY_SEKCJI.md`: rozdz. 1 z tabelą „decyzja → sekcja” według P1.2b, poprawki w rozdz. 2–6, walidatory P1.3a w rozdz. 0 i 5.
- Baza: `origin/main` `4e9603e` (P1.3a weszło w trakcie kroku).
- Dowód: `git diff --check`, kontrola tabel, odwołań i braku emoji, diff tylko w plikach `.md`, `bash scripts/gate.sh api -rs`.

Krok L2 (lider, ta sama gałąź): decyzje lidera po konsultacji z COI (2026-11-21), bez zmian w kodzie.

- Baza: `origin/main` `6945cc1` (doszły M1.3, M1.5 i pypdf); L1 i L2 idą jednym PR.
- `DECISIONS.md`: D9 od nowa (Eden AI jako wyjątek COI, Ollama zostaje, klucz poza repo i agentami), D10 (jeden dokument → jeden JSON, warianty i zależności, bez pól nieuzasadnionych), D11 (cel 180 s, granica 200 s).
- `SPEC.md`: wyjątek w „Task and criteria” i „Out”, Must 1 i 2 (D10, D11), „Real and mocked”, „Model” z dwoma dostawcami. „API contract” i „Field contract” bez zmian.
- `DELEGACJA.md`: stan, właściciele plików (rozdz. 1), zadania M1.7 i K3.1 z kolejnością, E1, Q1, D1, M1.4, M1.5, rozdz. 4–7, prompty w rozdz. 8.
- Wpływ na kod sprawdzony na `main` i w PR #11, #12: lista w „Requests”. Implementacji nie zmieniam.
- Dowód: `git diff --check`, diff tylko w plikach `.md`, kontrola odwołań i tabel, `bash scripts/gate.sh all -rs` na bazie `6945cc1` → `408 passed, 143 skipped`, `GATE: PASS (all)`; pominięte wymagają `materialy/`, których ten worktree nie ma.

Krok L3 (lider, ta sama gałąź): odpowiedzi mentorów COI z Discorda (2026-11-21 wieczór), bez zmian w kodzie.

- Już zapisane: jeden dokument → jeden JSON (D10), cel 180–200 s (D11), Eden AI z zachowaniem Ollamy (D9). Dopisane tylko braki.
- `DECISIONS.md`: D9 pkt 7 (tylko modele otwarte) i pkt 8 (model docelowy Qwen3.5-9B, sprawdzony w katalogu Eden AI), D12 (obrona: x86 bez GPU), D13 (walidatory potwierdzone), D14 (słowniki z pliku COI).
- `SPEC.md`: warunek modelu otwartego, Must 2 (słowniki, walidatory), „Model” (Qwen3.5-9B, środowisko obrony).
- `DELEGACJA.md`: stan, M1.4, M1.7, K3.1, E1, rozdz. 4–7, prompty. `SZABLONY_SEKCJI.md`: rozdz. 0 i 5.
- Otwarte i tak opisane: RAM i internet na obronie, słownik adresu zamieszkania.
- Dowód: `git diff --check`, diff tylko w plikach `.md`, kontrola tabel, `bash scripts/gate.sh all -rs`.

Krok L4 (lider): integracja L1–L3 z `main` `65c0259` po akceptacji lidera (D8–D14 zatwierdzone).

- Na `main` nie było D8–D14; doszły M1.4, K2, K3, K3-fix, P1.4 i P3 (część E1). Konfliktów brak.
- Poprawione po P1.4 i M1.4: D10 (stan kontraktu warunków), `DELEGACJA.md` (stan, rozdz. 7).
- Dowód: `git diff --cached --check`, w stage'u tylko pięć plików `.md`, `bash scripts/gate.sh all -rs`.

## Requests

(one line per change you need from another area: who asks, what, why)

- lider → Marcin (M1.7, `config.py`, `env.example`, `docker-compose.yml`): `LLM_PROVIDER` (`ollama` domyślnie, `edenai`), przy `edenai` tylko host Eden AI i wymagany klucz; pole `Settings.llm_provider`. Dlaczego: D9, adapter K3.1 potrzebuje jawnego wyboru dostawcy.
- lider → Marcin (`env.example`, wiersz 2): komentarz „The model runs locally only (Ollama). No hosted model APIs” jest nieaktualny po D9.
- lider → Marcin (`docker-compose.yml`): `api` ma zachować wyjście do internetu. Uwaga LATER z recenzji M1.5 „sieć tylko api–ollama” nie może odciąć Eden AI. `OLLAMA_NO_CLOUD=1` zostaje.
- lider → Marcin (M1.4, `main.py`, `config.py`): cały proces ma mieścić się w budżecie D11. Dziś `LLM_TIMEOUT_S=120` i dwie próby K3 to do 240 s samej analizy.
- lider → Mikołaj (K3.1, `llm.py`): adapter Eden AI obok Ollamy. Do rozstrzygnięcia w kodzie: `reasoning_effort: "none"` i `response_format: json_schema` są dobrane pod Ollamę, a `trust_env=False` ma komentarz „model działa lokalnie”.
- lider → Mikołaj (K3.1, `analysis.py` w PR #11): `CONTEXT_TOKENS = 16384`, `MAX_ATTEMPTS = 2` i komunikat „sprawdź OLLAMA_CONTEXT_LENGTH” zakładają Ollamę; przy Eden AI budżet i liczba prób zależą od dostawcy i od D11.
- lider → Mikołaj (`scripts/bench_model.py`): sonda `ollama_version` i domyślny adres `localhost:11434` są tylko dla Ollamy; pomiar Eden AI uruchamia człowiek z kluczem.
- lider → Paweł (E1, `eval.py`): jeden plik → jeden JSON, także folder 9; raport z czasem całego procesu wobec D11 i z polami bez odpowiednika we wzorcu (D10 pkt 3).
- lider → web (`frontend/playwright.config.ts`): `LLM_FIXTURE` dla API nadal nie jest ustawione (prośba Mikołaja z K1). Po K3.1 e2e bez niego mogłoby wołać Eden AI i zużywać klucz.
- lider → Mikołaj (K3.1, `llm.py`): model docelowy to Qwen3.5-9B przez Eden AI (D9 pkt 8). Kandydaci: `ovhcloud/Qwen3.5-9B`, `ionos/Qwen/Qwen3.5-9B`. W Qwen3.5 myślenie jest domyślnie włączone, a `reasoning_effort` katalog deklaruje tylko dla jednej trasy, więc wyłączenie myślenia musi być do ustawienia per dostawca.
- lider → Mikołaj (K3.1, `analysis.py`): kontekst Qwen3.5-9B w Eden AI to 262 144 tokeny, więc foldery 8 i 9 nie potrzebują dzielenia na fragmenty. Budżet 16384 zostaje tylko dla Ollamy.
- lider → Mikołaj (K3.1, `llm.py`): osobny krótki limit na połączenie. Internet na obronie jest niepotwierdzony (D12), a brak sieci nie może zjadać całego `LLM_TIMEOUT_S`.
- lider → Marcin (M1.7, `config.py`): przy `edenai` przyjmuj tylko modele otwarte z listy (D9 pkt 7). Eden AI udostępnia też modele zamknięte, a ich użycie łamie zasady COI.
- lider → Marcin (M1.4, `main.py`): brak internetu przy `edenai` ma dać szybkie 503 z tym samym `detail`. Przełączenie na Ollamę robi człowiek w `.env`, bez automatycznego ponowienia na drugim dostawcy (budżet D11).
- lider → Marcin (Docker, `docker-compose.yml`, `ollama/Dockerfile`): obrona to x86 bez GPU (D12). Potwierdź, że oba obrazy budują się i startują na `linux/amd64`, i podaj zmierzone zużycie pamięci `api` i `ollama` z `qwen3.5:4b`. RAM na obronie jest niepotwierdzony.
- lider → Marcin (Docker, `docker-compose.yml`): przy `edenai` serwis `ollama` nie jest potrzebny, a trzyma model w pamięci. Rozważ uruchamianie go tylko dla dostawcy `ollama`.
- lider → Marcin (`scripts/pull_model.sh`, README): obrazy i model lokalny pobieramy przed obroną (D12). Opisz kroki przygotowania maszyny bez internetu.
- lider → Paweł (P1, `generator/template.py`): `TERYT_4G_DOWODOWY` podają Standardy COI i wzorce, ale plik słowników COI go nie wymienia (D14). Nie zmieniaj go do odpowiedzi mentora. Po odpowiedzi: jedna poprawka w szablonie adresu i w testach.
- lider → Paweł (P2, `lint.py`): linter przyjmuje dowolną niepustą nazwę słownika. Po rozstrzygnięciu D14: reguła „nazwa słownika z listy COI”.
- lider → Paweł (P1.2c/P1.3, `models.py`): `SubjectField` nie pozwala wskazać słownika, więc pole kraju lub gminy z papieru nie dostanie słownika COI. To zmiana kontraktu, czyli decyzja ludzi.
- lider → Paweł (P1, P1.3a): walidatory są potwierdzone przez mentora (D13). Kod bez zmian, `ADD_VALIDATORS` zostaje `true`.
- lider → Paweł (E1, `eval.py`): raport podaje użyty model i dostawcę oraz nazwy słowników spoza pliku COI. Zapytania do Eden AI uruchamia człowiek z kluczem.
- lider → mentor COI: (1) ile RAM-u ma maszyna obrony, (2) czy będzie stabilny internet, (3) który słownik stosować do adresu zamieszkania: `TERYT_4G_DOWODOWY` ze Standardów i wzorców czy Województwo, Powiat, Gmina, Miejscowość z pliku słowników.

## Log

(one line per step: done / next / blocker)

- L1 (dokumenty po mentorze): done D8, D9 i synchronizacja SPEC, DELEGACJA, SZABLONY z P1.2a, P1.2b, P1.3a i K1 na bazie `4e9603e`; zamknięte prośby z `PROGRESS.api.md`: Paweł (SZABLONY rozdz. 1, DELEGACJA rozdz. 2.1), Mikołaj (SPEC „Model”), Marcin (SPEC Must 1) / next: commit człowieka i PR do `main` / blocker brak; otwarte bez zmian: `LLM_TIMEOUT_S=120` i „JSON w < 2 min” w M1.5 wobec 238–344 s z K1, licencja LibreOffice przed pierwszą zależnością, pytania do mentora z `docs/BRIEF_ZESPOL.md` rozdz. 7 i SPEC (numeracja rozszerzeń).
- L2 (decyzje po konsultacji z COI): done D9 (Eden AI jako wyjątek, Ollama zostaje), D10, D11 w `DECISIONS.md`; `SPEC.md` i `DELEGACJA.md` z zadaniami M1.7 i K3.1; baza `6945cc1` (L4: `65c0259`); wpływ na kod i właścicieli plików w „Requests” / next: akceptacja lidera, commit człowieka, PR do `main`, potem K3 (#11) → M1.7 → K3.1 → M1.4 / blocker brak; otwarte: model po stronie Eden AI i pomiar czasu (człowiek z kluczem), wartości limitów pod D11, wariant na całe sekcje lub strony w formularzu 9 (zmiana kontraktu `FormAnalysis`), prośby z PR #11 do lidera (sygnatura `analyze` w rozdz. 2.2, osobny komunikat dla za długiego dokumentu).
- L3 (odpowiedzi mentorów z Discorda): done D9 pkt 7 i 8 (tylko modele otwarte; Qwen3.5-9B: Apache-2.0, w publicznym katalogu Eden AI pod ośmioma identyfikatorami, wymuszony schemat zadeklarowany), D12, D13, D14; `SPEC.md`, `DELEGACJA.md`, `SZABLONY_SEKCJI.md`; prośby do Mikołaja, Marcina, Pawła i mentora w „Requests” / next: akceptacja lidera, commit człowieka, PR do `main`; pomiar Qwen3.5-9B przez Eden AI przez człowieka z kluczem / blocker brak; otwarte: RAM i internet na obronie, słownik adresu zamieszkania, sposób wyłączenia myślenia i czas odpowiedzi w Eden AI.
- L4 (integracja z `main` `65c0259`): done L1–L3 na aktualnym `main`, D10 i `DELEGACJA.md` zgodne z P1.4 i M1.4 / next: commit człowieka, push, PR / blocker brak.
