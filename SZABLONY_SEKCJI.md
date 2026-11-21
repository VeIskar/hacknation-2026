# Biblioteka szablonów sekcji standardowych (COI)

Źródła: „Standardy i dobre praktyki projektowania formularzy” (S), „Reguły techniczne konfiguracji” (R), „Dane inicjalne” (DI), „Słowniki” (SŁ), screeny eUsług „Nadpłata podatku” i „Numer porządkowy” (EK).
Wersja robocza 1 · sobota 11:40. Konflikty oznaczone **⚠ K1…K12** – lista na końcu, do potwierdzenia u mentora COI.

**Zasada:** sekcje z tego pliku generuje kod (szablony). AI ustala tylko **parametry szablonu** (rozdział 1) i **przedmiot wniosku** (strony 2…n). Pola z papieru, które pokrywają te sekcje, są usuwane (rozdział 5).

---

## 0. Konwencje JSON (dla każdego pola)

| Element | Reguła |
|---|---|
| Sekcja | element `tabs[].questions[]` z `field.type = "SECTION"` lub `"REPEATING_SECTION"`; pola sekcji leżą w `field.repeatingSectionGrid[]` (struktura jak question) ⚠ K1 |
| Zagnieżdżenie | pole zawsze w sekcji; sekcja nie może być w sekcji (R4–R6) |
| `id` | UUID v4 (sekcja, pole, strona, link) |
| `techName` | snake_case, unikalny w formularzu, stały – z tej tabeli; jsonata się do niego odwołuje |
| Obligatoryjność | każde pole musi ją mieć (R8): `validation` zawiera `"REQUIRED"` albo jest jawnie bez niego |
| Siatka | jedna kolumna (S): `x=0`, `y` = kolejność w sekcji, `rows=1`, `cols` = pełna szerokość ⚠ K5 |
| `questionOrder` | kolejność pola w sekcji (od 1) |
| Dane inicjalne | `readOnly: true`, `defaultValue: "ŹRÓDŁO.atrybut"`, `defaultValueType: "EXTERNAL_SYSTEM"` (DI) ⚠ K3 |
| Opcje | `options: [{id, name, techName}]`; przy słowniku `options: []` + `dictionaryName` |
| Widoczność | `states: [{ "type": "SHOW", "query": "<jsonata>" }]` – szablony zapytań w rozdziale 4 |
| Etykieta opcjonalnych pól | renderer dopisuje „(opcjonalnie)” – nie wpisywać tego do `title` (EK) |

---

## 1. Parametry szablonu – co ustala AI z papierowego formularza

| Parametr | Wartości | Skąd | Na co wpływa |
|---|---|---|---|
| `TYTUL` | „Wniosek/Zgłoszenie/Deklaracja/Oświadczenie o …”, max 255 znaków, bez przepisów prawa (S, R1) | nagłówek formularza | `title` formularza |
| `CZASOWNIK` | wnioskujesz / zgłaszasz / deklarujesz | pierwsze słowo tytułu | etykiety w Podmiocie wniosku |
| `ADRESAT_TYP` | URZAD / ORGAN | „Do Wójta…” → ORGAN; „Urząd Gminy…” → URZAD | tytuł i etykieta sekcji 1 |
| `ADRESAT_NAZWA` | np. „Urząd Gminy Ulan-Majorat, Wydział Podatków” | nagłówek / adresat | `defaultValue` w sekcji 1 |
| `WNIOSKODAWCY` | FIZYCZNA / PODMIOT / OBA | jakie dane wnioskodawcy są na papierze (S, „Podmiot wniosku”) | opcje radia + które sekcje warunkowe powstają |
| `TYLKO_WE_WLASNYM` | true/false | czy można działać w imieniu innego | true → brak sekcji Podmiot wniosku i sekcji warunkowych |
| `ZALACZNIKI` | lista | „Załączniki:” na papierze | FILE_UPLOADER-y w przedmiocie wniosku |
| `OSWIADCZENIA` | lista tekstów | „Oświadczam, że…” | zgody w sekcji Zgody i oświadczenia |
| `PODPIS` | true (domyślnie) / false | S: domyślnie każdy formularz kończy się podpisem | tekst bloku Podgląd |

**Tabela decyzji `WNIOSKODAWCY` → opcje radia „Wybierz, w czyim imieniu …”** (S)

| Papier zawiera | Opcje radia | Sekcje warunkowe |
|---|---|---|
| tylko dane osoby fizycznej | Swoim · Innej osoby | Dane innej osoby, Adres zamieszkania innej osoby, Pełnomocnictwo, Opłata skarbowa v1 |
| tylko dane firmy/instytucji | Osoby prawnej lub jednostki organizacyjnej ⚠ K10 | Dane podmiotu, Adres siedziby, Pełnomocnictwo, Opłata v2, Potwierdzenie reprezentanta |
| jedno i drugie | Swoim · Innej osoby · Osoby prawnej lub jednostki organizacyjnej | wszystkie powyższe |

---

## 2. Układ stron

| Strona | `type` | Tytuł strony (propozycja, stały – używa go jsonata) ⚠ K6 | Sekcje |
|---|---|---|---|
| 1 | MAIN | `Wnioskodawca` | S1 Urząd · S2 Podmiot wniosku · S3 Twoje dane · S4 Adres zamieszkania · warunkowo S5–S11 |
| 2…n | MAIN | temat strony, np. `Informacje o nadpłacie`, `Lokalizacja budynku` | **przedmiot wniosku (AI)** – sekcje tematyczne |
| n+1 | MAIN | `Kontakt i zgody` | S12 Dane do kontaktu · S13 Zgody i oświadczenia |
| ostatnia | FINISH | `Podsumowanie` | S14 Podsumowanie (opcjonalnie) · S15 Podgląd – tylko TEXT_BLOCK / INFO_SECTION (R7) |

`flow.links`: liniowo strona *k* → *k+1* (R9). Strony alternatywne tylko gdy od odpowiedzi zależy cały etap (S8) – poza MVP.

---

## 3. Sekcje i pola

### S1 · Urząd / organ — zawsze

| techName sekcji | Tytuł sekcji |
|---|---|
| `urzad` | URZAD: „Urząd, do którego jest składany wniosek” · ORGAN: „Organ, do którego jest składany wniosek” |

| # | techName | Etykieta | Typ | Walidacja | readOnly | defaultValue / Type | Widoczność | Uwagi |
|---|---|---|---|---|---|---|---|---|
| 1 | `nazwa_urzedu` | URZAD: „Nazwa urzędu” · ORGAN: „Nazwa organu” | TEXT_FIELD | REQUIRED | true | `ADRESAT_NAZWA` / (puste – to nie rejestr) | zawsze | nazwa urzędu + komórka organizacyjna (S) |

### S2 · Podmiot wniosku — gdy `TYLKO_WE_WLASNYM = false`

| techName sekcji | Tytuł |
|---|---|
| `podmiot_wniosku` | „Podmiot wniosku” |

| # | techName | Etykieta | Typ | Walidacja | Opcje (`name` / `techName`) | Widoczność |
|---|---|---|---|---|---|---|
| 1 | `w_czyim_imieniu` | „Wybierz, w czyim imieniu `CZASOWNIK`” | RADIO | REQUIRED | Swoim / `swoim` · Innej osoby / `innej_osoby` · Osoby prawnej lub jednostki organizacyjnej / `osoby_prawnej` (podzbiór wg tabeli decyzji) | zawsze |
| 2 | `jako_kto` | „Wybierz, jako kto `CZASOWNIK`” | RADIO | REQUIRED | Pełnomocnik / `pelnomocnik` · Reprezentant / `reprezentant` | SHOW: Q(`w_czyim_imieniu`) = „Osoby prawnej lub jednostki organizacyjnej” |

Pole 2 istnieje tylko gdy opcja `osoby_prawnej` jest w polu 1.

### S3 · Twoje dane — zawsze (obowiązkowa, S)

| techName sekcji | Tytuł |
|---|---|
| `twoje_dane` | „Twoje dane” |

| # | techName | Etykieta | Typ | Walidacja | readOnly | defaultValue | defaultValueType |
|---|---|---|---|---|---|---|---|
| 1 | `imie` | „Imię” | TEXT_FIELD | REQUIRED | true | `MLPZ.name` | EXTERNAL_SYSTEM |
| 2 | `nazwisko` | „Nazwisko” | TEXT_FIELD | REQUIRED | true | `MLPZ.surname` | EXTERNAL_SYSTEM |
| 3 | `pesel` | „Numer PESEL” | TEXT_FIELD | REQUIRED, PESEL | true | `MLPZ.pesel` | EXTERNAL_SYSTEM |

### SZABLON ADRESU (A) — używany przez S4, S6, S8

Parametr `P` = prefiks techName, `T` = tytuł sekcji. Kolejność pól stała (S).

| # | techName | Etykieta | Typ | Walidacja | Słownik / opcje | Inne | Widoczność |
|---|---|---|---|---|---|---|---|
| 1 | `P_kraj` | „Kraj” | SELECT | REQUIRED | `dictionaryName`: Kraje ⚠ K4 | `searchEnabled: true` ⚠ K7, `defaultValue: "Polska"` | zawsze |
| 2 | `P_wojewodztwo` | „Województwo” | SELECT | REQUIRED | Województwo ⚠ K8 | `searchEnabled: true` | SHOW: kraj = Polska |
| 3 | `P_powiat` | „Powiat” | SELECT | REQUIRED | Powiat ⚠ K8 | `searchEnabled: true` | SHOW: kraj = Polska |
| 4 | `P_gmina` | „Gmina” | SELECT | REQUIRED | Gmina ⚠ K8 | `searchEnabled: true` | SHOW: kraj = Polska |
| 5 | `P_miejscowosc` | „Miejscowość” | SELECT | REQUIRED | Miejscowość ⚠ K8 | `searchEnabled: true` | SHOW: kraj = Polska |
| 6 | `P_miejscowosc_zagr` | „Miejscowość” | TEXT_FIELD | REQUIRED | – | – | SHOW: kraj ≠ Polska |
| 7 | `P_kod_pocztowy` | „Kod pocztowy” | TEXT_FIELD | REQUIRED, ZIP_CODE | – | placeholder `__-___` ⚠ K7 | SHOW: kraj = Polska |
| 8 | `P_kod_pocztowy_zagr` | „Kod pocztowy” | TEXT_FIELD | REQUIRED (bez ZIP_CODE) | – | + checkbox „Brak kodu pocztowego” ⚠ K9 | SHOW: kraj ≠ Polska |
| 9 | `P_ulica` | „Ulica” | TEXT_FIELD | REQUIRED ⚠ K11 | – | placeholder „Np. Polna, aleja Leśna, plac Lipowy, skwer Słoneczny”; + checkbox „Brak nazwy ulicy” ⚠ K9 | zawsze (PL i zagranica) |
| 10 | `P_numer_budynku` | „Numer budynku” | TEXT_FIELD | REQUIRED | – | – | zawsze ⚠ K12 |
| 11 | `P_numer_lokalu` | „Numer lokalu” | TEXT_FIELD | REQUIRED ⚠ K11 | – | + checkbox „Brak numeru lokalu” ⚠ K9 | zawsze ⚠ K12 |

Dane inicjalne MLPZ w adresie (`MLPZ.postCode`, `MLPZ.street`, `MLPZ.building`, `MLPZ.apartment`): na screenach pola są **puste i edytowalne** → **nie ustawiamy** ⚠ K3.

### S4 · Adres zamieszkania — zawsze

`P = adres`, `T = "Adres zamieszkania"` (wariant: zameldowania / korespondencyjny – jeśli papier tak mówi).

### S5 · Dane innej osoby — SHOW: Q(`w_czyim_imieniu`) = „Innej osoby”

| techName sekcji | Tytuł |
|---|---|
| `dane_innej_osoby` | „Dane innej osoby” |

| # | techName | Etykieta | Typ | Walidacja |
|---|---|---|---|---|
| 1 | `inna_imie` | „Imię” | TEXT_FIELD | REQUIRED |
| 2 | `inna_nazwisko` | „Nazwisko” | TEXT_FIELD | REQUIRED |
| 3 | `inna_pesel` | „Numer PESEL” | TEXT_FIELD | REQUIRED, PESEL ⚠ K2 |

### S6 · Adres zamieszkania innej osoby — SHOW jak S5 (EK)

`P = adres_innej`, `T = "Adres zamieszkania innej osoby"`, szablon A.

### S7 · Dane podmiotu — SHOW: Q(`w_czyim_imieniu`) = „Osoby prawnej lub jednostki organizacyjnej”

| techName sekcji | Tytuł |
|---|---|
| `dane_podmiotu` | „Dane podmiotu” |

| # | techName | Etykieta | Typ | Walidacja | Uwagi |
|---|---|---|---|---|---|
| 1 | `podmiot_nazwa` | „Nazwa” | TEXT_FIELD | REQUIRED | |
| 2 | `podmiot_nip` | „NIP” | TEXT_FIELD | REQUIRED, NIP | |
| 3 | `podmiot_regon` | „REGON” | TEXT_FIELD | REQUIRED, REGON | ⚠ K2 (brak na screenie) |
| 4 | `podmiot_krs` | „Numer KRS” | TEXT_FIELD | opcjonalne | S: Pattern `^\d{10}$`, komunikat „Wpisz 10 cyfr.” – brak walidatora Pattern na liście R ⚠ K7 |

### S8 · Adres siedziby — SHOW jak S7 (EK)

`P = adres_siedziby`, `T = "Adres siedziby"`, szablon A.

### S9 · Pełnomocnictwo — SHOW: „Innej osoby” **lub** („Osoby prawnej…” **i** `jako_kto` = „Pełnomocnik”)

| techName sekcji | Tytuł | Opis sekcji |
|---|---|---|
| `pelnomocnictwo` | „Pełnomocnictwo” | „Dodaj dokument potwierdzający, że jesteś pełnomocnikiem.” |

| # | techName | Etykieta | Typ | Walidacja | Limity (⚠ K7 – brak w schemacie) |
|---|---|---|---|---|---|
| 1 | `plik_pelnomocnictwa` | „Plik dokumentu z pełnomocnictwem” | FILE_UPLOADER | REQUIRED | 1 plik, 10 MB, jpg, pdf, xml, PAdES, png, jpeg, CAdES, XAdES |

### S10a · Opłata skarbowa (wersja 1) — SHOW: Q(`w_czyim_imieniu`) = „Innej osoby”

| techName sekcji | Tytuł | Opis sekcji |
|---|---|---|
| `oplata_skarbowa` | „Opłata skarbowa” | „Nie musisz płacić za złożenie pełnomocnictwa wystawionego przez najbliższą rodzinę: małżonka, dzieci, rodziców, dziadków, wnuków, rodzeństwo. Więcej informacji na stronie biznes.gov.pl” |

| # | techName | Etykieta | Typ | Walidacja | Opcje | Widoczność |
|---|---|---|---|---|---|---|
| 1 | `czy_oplata` | „Czy złożenie pełnomocnictwa wymaga opłaty skarbowej?” | RADIO | REQUIRED | Tak / `tak` · Nie / `nie` | zawsze |
| 2 | `oplata_info` | – (`description` = TEKST_OPŁATY) | TEXT_BLOCK | – | – | SHOW: `czy_oplata` = „Tak” |
| 3 | `plik_potwierdzenia_przelewu` | „Plik z potwierdzeniem przelewu” | FILE_UPLOADER | REQUIRED | 1 plik, 10 MB, PDF | SHOW: `czy_oplata` = „Tak” |

### S10b · Opłata skarbowa (wersja 2) — SHOW: „Osoby prawnej…” **i** `jako_kto` = „Pełnomocnik”

| techName sekcji | Tytuł |
|---|---|
| `oplata_skarbowa_pelnomocnik` | „Opłata skarbowa” (EK: „Opłata skarbowa za pełnomocnictwo”) |

| # | techName | Etykieta | Typ | Walidacja | Limity |
|---|---|---|---|---|---|
| 1 | `oplata_info_v2` | – (`description` = TEKST_OPŁATY) | TEXT_BLOCK | – | – |
| 2 | `plik_potwierdzenia_przelewu_v2` | „Plik z potwierdzeniem przelewu” | FILE_UPLOADER | REQUIRED | 1 plik, 10 MB, PDF |

**TEKST_OPŁATY** (S, dosłownie; `(...)` = przedmiot z `TYTUL`):
> Opłata skarbowa wynosi 17 zł. Przelej ją na konto urzędu miasta lub gminy właściwego dla adresu zamieszkania osoby, która udzieliła pełnomocnictwa. Jeśli adres nie jest w Polsce, opłatę przelej na konto Urzędu Miasta Stołecznego Warszawy – Centrum Obsługi Podatnika. W tytule przelewu wpisz „Wniosek o (...) – opłata skarbowa za pełnomocnictwo”. Dodaj plik z potwierdzeniem przelewu. Znajdziesz go na stronie lub w aplikacji swojego banku.

### S11 · Potwierdzenie, że jesteś reprezentantem — SHOW: „Osoby prawnej…” **i** `jako_kto` = „Reprezentant” (tylko EK, brak w S)

| techName sekcji | Tytuł | Opis sekcji |
|---|---|---|
| `potwierdzenie_reprezentanta` | „Potwierdzenie, że jesteś reprezentantem” | „Dołącz aktualny odpis danych z Krajowego Rejestru Sądowego lub innego rejestru. Odpis powinien potwierdzać, że jesteś reprezentantem podmiotu lub instytucji.” |

| # | techName | Etykieta | Typ | Walidacja | Limity |
|---|---|---|---|---|---|
| 1 | `plik_odpisu` | „Plik z odpisem danych” | FILE_UPLOADER | REQUIRED | do 3 plików, 10 MB, jpg, pdf, png, jpeg |

### Strony 2…n · Przedmiot wniosku — generuje AI

Zasady dla AI (S, R): sekcje tematyczne; typ pola wg danych (krótki tekst → TEXT_FIELD, opis/uzasadnienie → TEXTAREA, liczba/kwota → NUMBER, data → DATEPICKER, 1 z ≤5 → RADIO, ≥1 z wielu → CHECKBOX, >5 opcji → SELECT, >15 → `searchEnabled`), załącznik → FILE_UPLOADER, objaśnienie pola → `description`, ogólna instrukcja → TEXT_BLOCK (bez ściany tekstu), prosty język (bez „dokonać”, „posiadać”, form bezosobowych), pola zależne → `states` SHOW. Dane powtarzalne (wiele działek, osób, pojazdów) → REPEATING_SECTION.

### S12 · Dane do kontaktu — zawsze, przedostatnia strona

| techName sekcji | Tytuł | Opis sekcji |
|---|---|---|
| `dane_do_kontaktu` | „Dane do kontaktu” | „Wpisanie danych do kontaktu może przyspieszyć załatwienie sprawy. Urzędnik będzie mógł skontaktować się z Tobą w przypadku pytań lub wątpliwości. Jeśli widzisz uzupełnione dane, sprawdź, czy są poprawne. Możesz je zmienić lub usunąć.” |

| # | techName | Etykieta | Typ | Walidacja | readOnly | defaultValue / Type |
|---|---|---|---|---|---|---|
| 1 | `telefon` | „Numer telefonu” | TEXT_FIELD | opcjonalne | false ⚠ K3 | `MLPZ.phoneNumber` / EXTERNAL_SYSTEM ⚠ K3 |
| 2 | `email` | „Adres e-mail” | TEXT_FIELD | EMAIL (opcjonalne) | false ⚠ K3 | `MLPZ.email` / EXTERNAL_SYSTEM ⚠ K3 |

(EK: pola są wstępnie wypełnione **i edytowalne** – niezgodne z DI.)

### S13 · Zgody i oświadczenia — zawsze, przedostatnia strona

| techName sekcji | Tytuł |
|---|---|
| `zgody` | tylko zgoda RODO: „Zgoda” · tylko oświadczenie: „Oświadczenie” · oba: „Zgody i oświadczenia” |

| # | techName | Typ | Konfiguracja |
|---|---|---|---|
| 1 | `zgody_lista` | CONSENT_SECTION | `consentSectionConfig.consents`: (a) zawsze „Wyrażam zgodę na przetwarzanie moich danych osobowych zgodnie z klauzulą informacyjną.” (link do BIP urzędu, nie pełna treść klauzuli – S), required: true; (b) każde `OSWIADCZENIA` z papieru, przepisane prostym językiem, czas teraźniejszy, neutralnie płciowo. `selectAllEnabled` ⚠ K7. Nigdy CHECKBOX/RADIO dla zgód (S). |

### S14 · Podsumowanie — strona FINISH, opcjonalnie

| techName | Typ | Treść |
|---|---|---|
| sekcja `podsumowanie`, tytuł „Podsumowanie” → pole `podsumowanie_tekst` | TEXT_BLOCK | co dalej ze sprawą (np. kontakt urzędu, termin) – tylko jeśli papier o tym mówi |

### S15 · Podgląd — strona FINISH, zawsze

| techName | Typ | Treść |
|---|---|---|
| sekcja `podglad`, tytuł „Podgląd” → pole `podglad_tekst` | TEXT_BLOCK | `PODPIS=true`: „Zanim przejdziesz do wyboru sposobu podpisu, sprawdź dane na podglądzie. Jeśli zobaczysz błędy, wróć do edycji.” · `PODPIS=false`: „Zanim wyślesz formularz, sprawdź dane na podglądzie. Jeśli zobaczysz błędy, wróć do edycji.” |

R7: na FINISH wolno tylko INFO_SECTION ⚠ K6 – jeśli mentor potwierdzi, zamienić TEXT_BLOCK na INFO_SECTION (`techName` + `description`).

---

## 4. Szablony zapytań jsonata (SHOW)

Wzór z R (pole w sekcji):
```
"<OPCJA>" in tabs['<TYTUŁ_STRONY>' in title].questions['<techName_sekcji>' in field.techName].field.repeatingSectionGrid['<techName_pola>' in field.techName].field.__userAnswer
```
Oznaczenie Q(pole) = „X” w tabelach = powyższe wyrażenie.

| Warunek | query |
|---|---|
| Innej osoby | `"Innej osoby" in tabs['Wnioskodawca' in title].questions['podmiot_wniosku' in field.techName].field.repeatingSectionGrid['w_czyim_imieniu' in field.techName].field.__userAnswer` |
| Osoby prawnej | `"Osoby prawnej lub jednostki organizacyjnej" in tabs['Wnioskodawca' in title].questions['podmiot_wniosku' in field.techName].field.repeatingSectionGrid['w_czyim_imieniu' in field.techName].field.__userAnswer` |
| Osoby prawnej **i** Pełnomocnik | `(<Osoby prawnej>) and ("Pełnomocnik" in tabs['Wnioskodawca' in title].questions['podmiot_wniosku' in field.techName].field.repeatingSectionGrid['jako_kto' in field.techName].field.__userAnswer)` |
| Pełnomocnictwo (S9) | `(<Innej osoby>) or ((<Osoby prawnej>) and (<Pełnomocnik>))` |
| Osoby prawnej **i** Reprezentant | jak wyżej z `"Reprezentant"` |
| Kraj = Polska (sekcja `S`, pole `P_kraj`) | `"Polska" in tabs['Wnioskodawca' in title].questions['S' in field.techName].field.repeatingSectionGrid['P_kraj' in field.techName].field.__userAnswer` |
| Kraj ≠ Polska | `$not(<Kraj = Polska>)` |
| Opłata = Tak | `"Tak" in tabs['Wnioskodawca' in title].questions['oplata_skarbowa' in field.techName].field.repeatingSectionGrid['czy_oplata' in field.techName].field.__userAnswer` |

---

## 5. Pola z papieru, które usuwamy (pokrywają je szablony)

| Na papierze | Zastępuje |
|---|---|
| Imię, nazwisko, PESEL wnioskodawcy | S3 Twoje dane (MLPZ) |
| Adres zamieszkania / zameldowania / do korespondencji wnioskodawcy | S4 |
| Telefon, e-mail, „dane kontaktowe” | S12 |
| Dane pełnomocnika / „działający w imieniu” | S2 + S5/S7 + S9 |
| Nazwa firmy, NIP, REGON, KRS, adres siedziby wnioskodawcy | S7 + S8 |
| „Oświadczam, że…”, klauzula RODO | S13 |
| Podpis, data, miejscowość i data, „czytelny podpis” | podpis elektroniczny – pole usuwamy |
| Adresat w nagłówku („Do Wójta Gminy…”) | S1 |
| Pola „wypełnia urząd” (nr sprawy, pieczęć, data wpływu) | usuwamy |
| Pouczenia, podstawy prawne | usuwamy z pól; ewentualnie krótki TEXT_BLOCK / link |

---

## 6. Konflikty do potwierdzenia (pytania do mentora)

| # | Konflikt | Nasza propozycja do czasu odpowiedzi |
|---|---|---|
| K1 | Schemat ma `repetingSectionGrid`, przykłady jsonaty `repeatingSectionGrid`; dla sekcji powtarzającej raz `field.techName`, raz `fieldTechName` | klucz jak w schemacie (`repetingSectionGrid`), w jsonacie jak w przykładzie R; poprawić po wzorcowym JSON-ie |
| K2 | S: Dane innej osoby z PESEL, Dane podmiotu z REGON i KRS; screeny EK: bez nich | trzymamy S (pełniejsze) |
| K3 | DI: pole z danymi inicjalnymi musi być readOnly i nieedytowalne; S zasila z MLPZ adres i kontakt, a EK pokazuje je jako edytowalne | Twoje dane: readOnly + MLPZ. Adres: bez danych inicjalnych. Kontakt: MLPZ + `readOnly: false` (zgodnie z EK) |
| K4 | Dokładne wartości `dictionaryName` („Kraje”? „KRAJE”?); S wspomina `TERYT_4G_DOWODOWY` spoza listy SŁ | nazwy jak w SŁ: Kraje, Województwo, Powiat, Gmina, Miejscowość, Numery kierunkowe |
| K5 | Szerokość siatki (`cols` dla pełnej szerokości) | `cols: 1` do czasu wzorca |
| K6 | Tytuły stron nieokreślone, a jsonata się do nich odwołuje; FINISH: R7 mówi tylko INFO_SECTION, S – TEXT_BLOCK | tytuły z rozdziału 2; na FINISH INFO_SECTION |
| K7 | `searchEnabled`, `selectAllEnabled`, placeholder, limity plików, walidator Pattern (KRS) są w S/R, brak ich w schemacie JSON | dodajemy klucze `searchEnabled`/`selectAllEnabled` (są w R); placeholder i limity w `tooltipMessage`/`description`; KRS bez Pattern |
| K8 | S: adres PL to 4 kaskadowe listy, w konfiguracji jedna lista TERYT (z błędnym defaultValue „Polska”); EK pokazuje tylko „Województwo” | 4 osobne SELECT-y z 4 słownikami |
| K9 | „Checkbox wyłączający pole” (Brak ulicy / kodu / lokalu) – brak sposobu zapisu w schemacie | osobny CHECKBOX z jedną opcją + na polu tekstowym `states: READ_ONLY` gdy zaznaczony |
| K10 | Wariant „tylko podmiot”: radio z jedną opcją? | radio z jedną opcją (spójność jsonaty); zapytać |
| K11 | S: „Ulica” z walidacją kodu pocztowego (błąd kopiuj-wklej); „Numer lokalu” wymagany mimo „Brak numeru lokalu” | ulica bez ZIP_CODE; numer lokalu REQUIRED + checkbox „Brak” (K9) |
| K12 | Proza S: adres zagraniczny ma też numer budynku i lokalu; konfiguracja pokazuje je tylko dla Polski | widoczne zawsze |
