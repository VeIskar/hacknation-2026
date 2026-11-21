# Szablony sekcji standardowych – wersja 2 (zgodna z wzorcami COI)

**Źródło prawdy:** dwa wzorcowe JSON-y od COI
- `1. …numer porządkowy…/konfiguracja_form_wniosekOUstalenieNumeruPorządkowegoNieruchomości (1).json`
- `5. …nadpłata podatku…/konfiguracja_form_wniosekOStwierdzenieNadpłatyPodatkuHacknation (2).json`

oraz Standardy i Reguły techniczne. Tam, gdzie wzorce się różnią, wybór jest zaznaczony **[decyzja]**. Wersja 1 (z rana, zgadywana) jest nieaktualna.

---

## 0. Format JSON – jak dokładnie wygląda COI

### Plik
```json
{ "title": "...", "tabs": [ ... ], "flow": { "links": [ {"id": "...", "source": "<id strony>", "target": "<id strony>"} ] } }
```

### Strona (`tabs[]`)
```json
{ "id": "<uuid>", "title": "Dane", "type": "MAIN", "questions": [ <sekcja>, ... ] }
```
Ostatnia strona `"type": "FINISH"`, reszta `"MAIN"`. `flow.links` łączy strony po kolei (1→2→3→4).

### Element siatki (sekcja na stronie albo pole w sekcji)
```json
{ "x": 0, "y": 0, "rows": 1, "cols": 3, "field": { ... } }
```

### Obiekt `field` – ZAWSZE wszystkie klucze (puste, gdy nieużywane)
```json
{
  "id": "<uuid>",
  "type": "TEXT_FIELD",
  "techName": "nazwa_urzedu",
  "title": "Nazwa urzędu",
  "description": "",
  "options": [],
  "validation": [],
  "readOnly": false,
  "repeatingSectionGrid": [],
  "states": [],
  "questionOrder": 0,
  "tooltipMessage": ""
}
```
Klucze dodatkowe – **tylko gdy potrzebne**: `defaultValue`, `defaultValueType`, `dictionaryName`, `multiLevelTree`, `searchEnabled`, `consentSectionConfig`.

### Reguły formatu (sprawdzone na wzorcach)

| Reguła | Wartość |
|---|---|
| Klucz pól w sekcji | **`repeatingSectionGrid`** (schemat ma literówkę `repeting…` – ignorujemy) |
| Siatka | `x: 0`, `cols: 3` zawsze |
| Pole w sekcji | `y` = indeks od 0, `rows: 1`, `questionOrder` = ten sam indeks |
| Sekcja na stronie | `rows` = liczba pól + 1; `y` = suma `rows` poprzednich sekcji; `questionOrder` = `y` |
| Sekcja (`type: SECTION`) | `description` = `"<html><head></head><body></body></html>"` gdy pusta, inaczej HTML z treścią |
| Opis pola | `""` gdy pusty, inaczej `"<html><head></head><body><p>…</p></body></html>"` |
| Opcje RADIO/CHECKBOX/SELECT | `{"id": "<nazwa>", "name": "<nazwa>", "techName": "<slug>"}` – **id = nazwa**, nie UUID |
| `techName` | slug z etykiety: małe litery, bez polskich znaków, `_` zamiast spacji (`Wybierz, jako kto wnioskujesz` → `wybierz_jako_kto_wnioskujesz`) |
| `validation` | we wzorcach zawsze `[]` – **[decyzja]** dodajemy walidatory jako rozszerzenie (REQUIRED, PESEL, NIP, REGON, EMAIL, ZIP_CODE, a w polach z analizy także SERIAL_NUMBER_ID_CARD, EPUAP, ADE) – patrz rozdz. 5; mentor COI potwierdził, że to dozwolone (D13) |
| Dane inicjalne | `"defaultValue": "MLPZ.name"`, `"defaultValueType": "EXTERNAL_SYSTEM"` |
| Słownik krajów | `"dictionaryName": "Kraje"`, `"defaultValue": ["Polska"]` (lista!), `"searchEnabled": true` |
| Adres w Polsce | **jedno** pole SELECT: `"dictionaryName": "TERYT_4G_DOWODOWY"`, `"multiLevelTree": true`, `"searchEnabled": true`, `"defaultValue": []`. Nazwę podają Standardy COI (rozdz. „Adres”) i wzorce; plik słowników COI jej nie wymienia – otwarte pytanie do mentora (D14) |
| Zgoda | `CONSENT_SECTION` z `"consentSectionConfig": {"consents": [{"description": "<html…>", "required": true}], "files": []}` |
| Strona końcowa | sekcja z polem **TEXT_BLOCK** (nie INFO_SECTION) |

### Jsonata (warunek SHOW) – format 1:1 z COI
```
("<OPCJA>" in tabs['<TYTUŁ STRONY>' in title].questions['<techName sekcji>' in field.techName].field.repeatingSectionGrid['<techName pola>' in field.techName].field.__userAnswer)
```
Zaprzeczenie: `$not("<OPCJA>" in …)`. Łączenie: `(…) and (…)`, `(…) or ((…) and (…))`.

Skróty w tabelach niżej:
- **[INNA]** = `wybierz_w_czyim_imieniu_wnioskujesz` = „Innej osoby”
- **[PRAWNA]** = `wybierz_w_czyim_imieniu_wnioskujesz` = „Osoby prawnej lub jednostki organizacyjnej”
- **[PEŁN]** = `wybierz_jako_kto_wnioskujesz` = „Pełnomocnik”
- **[REPR]** = `wybierz_jako_kto_wnioskujesz` = „Reprezentant”

Wszystkie z sekcji `podmiot_wniosku` na stronie `Dane`.

---

## 1. Parametry – co AI ustala dla części szablonowej

| Parametr | Przykład (nadpłata) | Przykład (numer porządkowy) | Skąd na papierze |
|---|---|---|---|
| `TYTUL` | Wniosek o stwierdzenie nadpłaty podatku | Wniosek o ustalenie numeru porządkowego nieruchomości | nagłówek „WNIOSEK o …” |
| `ADRESAT_TYP` | URZAD | ORGAN | „Urząd Gminy…” → URZAD; „Wójt / Burmistrz / Prezydent / Starosta…” → ORGAN |
| `ADRESAT_NAZWA` | Urząd Gminy Ulan-Majorat | Wójt Gminy Elbląg | blok adresata (bez ulicy i kodu) |
| `WNIOSKODAWCY` (`applicants`) | OBA (bo „Nazwisko i imię/Nazwa firmy”, PESEL/NIP) | OBA („imię i nazwisko/nazwa wnioskodawcy”) | jakie dane wnioskodawcy są na papierze |
| `WNIOSKODAWCA` (`applicant`) | decyzje z tabeli niżej | decyzje z tabeli niżej | o jakie dane wnioskodawcy, pełnomocnika i kontaktu pyta papier |
| `TEMAT_STRONY` | Informacje o nadpłacie | Informacje o budynku | czego dotyczy treść wniosku |
| `PODPIS` | tak | nie (inny tekst podglądu) | domyślnie tak |

Nazwy w kodzie (`FormAnalysis.applicants`): FIZYCZNA = `PERSON`, PODMIOT = `ENTITY`, OBA = `BOTH`.

Od P1.2b sekcje strony „Dane” wynikają z `applicants` i decyzji `applicant` (kontrakt P1.2a, zasada D8). S2 pokazuje tylko faktyczne wybory; nie ma już radia z jedną opcją dla PODMIOT.

| `applicants` | „Wybierz, w czyim imieniu …” | „Wybierz, jako kto …” (Pełnomocnik · Reprezentant) |
|---|---|---|
| PERSON | Swoim · Innej osoby, gdy `proxy`; bez `proxy` nie ma radia | nie ma |
| ENTITY | nie ma radia (jedna ścieżka) | gdy `proxy` |
| BOTH (oba wzorce) | Swoim · Innej osoby (gdy `proxy`) · Osoby prawnej lub jednostki organizacyjnej | gdy `proxy`, SHOW [PRAWNA] |

S2 bez żadnego radia nie powstaje. Przy jednej ścieżce warunki SHOW pomijają radio z S2, np. przy ENTITY S4 nie ma SHOW, a S11 ma tylko [PEŁN].

| Decyzja (`applicant`) | Sekcja (rozdz. 3–4) |
|---|---|
| zawsze | S1 i S3 z polami Imię, Nazwisko |
| `applicant_pesel` | pole `numer_pesel` w S3 |
| `person_address` | S4a przy PERSON i BOTH; S7, gdy jest ścieżka „Innej osoby” |
| `applicants` = ENTITY lub BOTH | S4: Nazwa i identyfikatory z `entity_ids` w kolejności NIP, REGON, KRS |
| `entity_ids_one_of` | NIP i REGON w S4 bez REQUIRED, opis sekcji „Podaj jeden z: …” |
| `entity_address` | S5 (ENTITY, BOTH) |
| `representative_proof` | S8 (ENTITY, BOTH) |
| `proxy` | S9; S6 i S10 przy ścieżce „Innej osoby”; S11 przy ENTITY i BOTH |
| `correspondence_address` | „Adres do korespondencji” (`adres_do_korespondencji`): RADIO „Czy adres do korespondencji jest inny?” (Tak · Nie) i szablon adresu z `SUF` = `_korespondencyjny`, bez danych inicjalnych, SHOW: radio = Tak |
| `contact` | S12 tylko z wybranymi polami: PHONE → `numer_telefonu`, EMAIL → `adres_e_mail`; pusta lista: bez S12 |
| `applicant_extra_fields` | sekcja „Dodatkowe dane wnioskodawcy” przed S9 (bez S9: na końcu strony), pola jak na stronach przedmiotu |

Ścieżka „Innej osoby” istnieje przy PERSON lub BOTH z `proxy`.

`CZASOWNIK` w etykietach: „wnioskujesz” (Wniosek), „zgłaszasz” (Zgłoszenie), „deklarujesz” (Deklaracja).

---

## 2. Układ stron

| # | `title` | `type` | Zawartość |
|---|---|---|---|
| 1 | `Dane` | MAIN | S1–S11 (szablon, dobór wg rozdz. 1) |
| 2…n | `TEMAT_STRONY` (np. „Informacje o nadpłacie”) | MAIN | **przedmiot wniosku – generuje AI** |
| n+1 | `Kontakt i zgody` **[decyzja; wzorzec 1 ma „Kontakt z urzędem”]** | MAIN | S12 (wg `contact`), S13 |
| ostatnia | `Strona końcowa` | FINISH | S14 |

---

## 3. Sekcje strony „Dane” (kolejność jak we wzorcach)

### S1 · Urząd / Organ – zawsze
| URZAD | ORGAN |
|---|---|
| sekcja `urzad_do_ktorego_jest_skladany_wniosek` · „Urząd, do którego jest składany wniosek” | sekcja `organ_do_ktorego_jest_skladany_wniosek` · „Organ, do którego jest składany wniosek” |
| pole TEXT_FIELD `nazwa_urzedu` · „Nazwa urzędu” | pole TEXT_FIELD `nazwa_organu` · „Nazwa organu” |

Pole: `readOnly: true`, `defaultValue: "<ADRESAT_NAZWA>"` (bez `defaultValueType`).

### S2 · Podmiot wniosku – `podmiot_wniosku` · „Podmiot wniosku”
| y | Typ | techName | Etykieta | Opcje (name / techName) | SHOW |
|---|---|---|---|---|---|
| 0 | RADIO | `wybierz_w_czyim_imieniu_wnioskujesz` | Wybierz, w czyim imieniu wnioskujesz | Swoim / `swoim` · Innej osoby / `innej_osoby` · Osoby prawnej lub jednostki organizacyjnej / `osoby_prawnej_lub_jednostki_organizacyjnej` | – |
| 1 | RADIO | `wybierz_jako_kto_wnioskujesz` | Wybierz, jako kto wnioskujesz | Pełnomocnik / `pelnomocnik` · Reprezentant / `reprezentant` | [PRAWNA] |

### S3 · Twoje dane – `twoje_dane` · „Twoje dane”
| y | Typ | techName | Etykieta | readOnly | defaultValue | defaultValueType |
|---|---|---|---|---|---|---|
| 0 | TEXT_FIELD | `imie` | Imię | true | `MLPZ.name` | EXTERNAL_SYSTEM |
| 1 | TEXT_FIELD | `nazwisko` | Nazwisko | true | `MLPZ.surname` | EXTERNAL_SYSTEM |
| 2 | TEXT_FIELD | `numer_pesel` | Numer PESEL | true | `MLPZ.pesel` | EXTERNAL_SYSTEM |

[decyzja] MLPZ jak w Standardach (wzorzec 5 ma `PESEL.*`, wzorzec 1 nie ma pola PESEL). Pole `numer_pesel` jest tylko przy `applicant_pesel` (rozdz. 1).

### SZABLON ADRESU – 9 pól, `SUF` = sufiks techName

| y | Typ | techName | Etykieta | Inne | SHOW |
|---|---|---|---|---|---|
| 0 | SELECT | `kraj{SUF}` | Kraj | `dictionaryName: "Kraje"`, `defaultValue: ["Polska"]`, `searchEnabled: true` | – |
| 1 | TEXT_FIELD | `miejscowosc{SUF}_zagranica` | Miejscowość | | `$not(kraj = Polska)` |
| 2 | TEXT_FIELD | `kod_pocztowy{SUF}_zagranica` | Kod pocztowy | | `$not(kraj = Polska)` |
| 3 | TEXT_FIELD | `ulica{SUF}_zagranica` | Ulica | | `$not(kraj = Polska)` |
| 4 | SELECT | `wojewodztwo{SUF}` | Województwo **[decyzja: wzorce mają tu nazwę słownika]** | `dictionaryName: "TERYT_4G_DOWODOWY"`, `multiLevelTree: true`, `searchEnabled: true`, `defaultValue: []` | kraj = Polska |
| 5 | TEXT_FIELD | `kod_pocztowy{SUF}` | Kod pocztowy | MLPZ.postCode* | kraj = Polska |
| 6 | TEXT_FIELD | `ulica{SUF}` | Ulica | MLPZ.street* | kraj = Polska |
| 7 | TEXT_FIELD | `numer_budynku{SUF}` | Numer budynku | MLPZ.building* | – |
| 8 | TEXT_FIELD | `numer_lokalu{SUF}` | Numer lokalu | MLPZ.apartment* | – |

\* Dane inicjalne (`defaultValueType: EXTERNAL_SYSTEM`, `readOnly: false`) **tylko w adresie wnioskodawcy (S4a)**.

| Sekcja | techName sekcji | Tytuł | `SUF` | SHOW sekcji |
|---|---|---|---|---|
| S4a | `adres_zamieszkania` | Adres zamieszkania | (pusty) | – |
| S5 | `adres_siedziby` | Adres siedziby | `_siedziba` | [PRAWNA] |
| S7 | `adres_zamieszkania_osoby_ktorej_jestes_pelnomocnikiem` | Adres zamieszkania innej osoby | `_inna_osoba` | [INNA] |

### S4 · Dane podmiotu – `dane_podmiotu` · „Dane podmiotu” · SHOW [PRAWNA]
| y | techName | Etykieta |
|---|---|---|
| 0 | `nazwa` | Nazwa |
| 1 | `nip` | NIP |
| 2 | `regon` | REGON |
| 3 | `numer_krs` | Numer KRS |

Wszystkie TEXT_FIELD. Nazwa jest zawsze, a NIP, REGON i Numer KRS według `entity_ids` (rozdz. 1). Wzorzec 1 i Standardy mają pełną wersję, wzorzec 5 tylko Nazwa i NIP.

### S8 · Potwierdzenie, że jesteś reprezentantem – `potwierdzenie_ze_jestes_reprezentantem` · SHOW `([PRAWNA]) and ([REPR])`
Opis sekcji: „Dołącz aktualny odpis danych z Krajowego Rejestru Sądowego lub innego rejestru. Odpis powinien potwierdzać, że jesteś reprezentantem podmiotu lub instytucji.”

| y | Typ | techName | Etykieta |
|---|---|---|---|
| 0 | FILE_UPLOADER | `plik_z_odpisem_danych` | Plik z odpisem danych |

### S6 · Dane innej osoby – `dane_innej_osoby` · „Dane innej osoby” · SHOW [INNA]
| y | techName | Etykieta |
|---|---|---|
| 0 | `imie_inna_osoba` | Imię |
| 1 | `nazwisko_inna_osoba` | Nazwisko |

(Oba wzorce: bez PESEL.)

### S9 · Pełnomocnictwo – `pelnomocnictwo` · SHOW `([INNA]) or (([PRAWNA]) and ([PEŁN]))`
Opis sekcji: „Dodaj dokument potwierdzający, że jesteś pełnomocnikiem.”

| y | Typ | techName | Etykieta |
|---|---|---|---|
| 0 | FILE_UPLOADER | `plik_dokumentu_z_pelnomocnictwem` | Plik dokumentu z pełnomocnictwem |

### S10 · Opłata skarbowa – `oplata_skarbowa_pelnomocnictwo_1` · „Opłata skarbowa” · SHOW [INNA]
Opis sekcji (HTML z linkiem): „Nie musisz płacić za złożenie pełnomocnictwa wystawionego przez najbliższą rodzinę: małżonka, dzieci, rodziców, dziadków, wnuków, rodzeństwo. Więcej informacji na stronie [biznes.gov.pl](https://www.biznes.gov.pl/pl/portal/0089#8)”

| y | Typ | techName | Etykieta | Opcje | SHOW |
|---|---|---|---|---|---|
| 0 | RADIO | `czy_zlozenie_pelnomocnictwa_wymaga_oplaty_skarbowej` | Czy złożenie pełnomocnictwa wymaga opłaty skarbowej? | Tak / `tak` · Nie / `nie` | – |
| 1 | TEXT_BLOCK | `oplata_info_1` | (pusty) | – | radio = Tak |
| 2 | FILE_UPLOADER | `plik_z_potwierdzeniem_przelewu` | Plik z potwierdzeniem przelewu | – | radio = Tak |

Opis `oplata_info_1` (HTML):
> Opłata skarbowa za pełnomocnictwo wynosi **17 zł**. ¶ Przelej ją na konto urzędu miasta lub gminy właściwego dla adresu zamieszkania osoby, która udzieliła pełnomocnictwa. Jeśli adres nie jest w Polsce, opłatę przelej na konto [Urzędu Miasta Stołecznego Warszawy – Centrum Obsługi Podatnika](https://warszawa19115.pl/-/oplata-skarbowa). ¶ W tytule przelewu wpisz „`<TYTUL>` – opłata skarbowa za pełnomocnictwo”.

### S11 · Opłata skarbowa za pełnomocnictwo – `oplata_skarbowa_pelnomocnictwo_2` · SHOW `([PRAWNA]) and ([PEŁN])`
| y | Typ | techName | Etykieta |
|---|---|---|---|
| 0 | TEXT_BLOCK | `oplata_info` | (pusty) |
| 1 | FILE_UPLOADER | `plik_z_potwierdzeniem_przelewu_2` | Plik z potwierdzeniem przelewu |

Opis `oplata_info`: jak w S10, ale „…dla adresu **siedziby podmiotu, który udzielił** pełnomocnictwa…” + akapit „Więcej informacji o opłacie skarbowej za pełnomocnictwo znajdziesz na stronie [biznes.gov.pl](https://www.biznes.gov.pl/pl/portal/0089#9)”.
Tytuł sekcji: „Opłata skarbowa za pełnomocnictwo” (wzorce mają literówkę „pełnomonictwo” – poprawiamy).

**Kolejność sekcji na stronie „Dane”:** S1, S2, S3, S4a, S4, S5, S8, S6, S7, Adres do korespondencji, Dodatkowe dane wnioskodawcy, S9, S10, S11. Kolejność S1–S11 jest jak we wzorcach. Sekcji bez decyzji z rozdz. 1 nie ma.

---

## 4. Strony końcowe

### S12 · Dane do kontaktu – `dane_do_kontaktu` · „Dane do kontaktu”
Opis sekcji: „Wpisanie danych do kontaktu może przyspieszyć załatwienie sprawy. Urzędnik będzie mógł skontaktować się z Tobą w przypadku pytań lub wątpliwości. Jeśli widzisz uzupełnione dane, sprawdź, czy są poprawne. Możesz je zmienić lub usunąć.”

| y | Typ | techName | Etykieta | defaultValue | readOnly |
|---|---|---|---|---|---|
| 0 | TEXT_FIELD | `numer_telefonu` | Numer telefonu | `MLPZ.phoneNumber` (EXTERNAL_SYSTEM) | false |
| 1 | TEXT_FIELD | `adres_e_mail` | Adres e-mail | `MLPZ.email` (EXTERNAL_SYSTEM) | false |

Pola według `contact` (rozdz. 1). Gdy papier nie zbiera danych do kontaktu, S12 nie ma.

### S13 · Zgoda – `zgoda_wyrazenie` · „Zgoda”
| y | Typ | techName | consentSectionConfig |
|---|---|---|---|
| 0 | CONSENT_SECTION | `zgoda` | consents: [„Wyrażam zgodę na przetwarzanie moich danych osobowych zgodnie z klauzulą informacyjną” (link), `required: true`] + oświadczenia z papieru (rozdz. 6), `files: []` |

Gdy papier ma oświadczenia → tytuł sekcji „Zgody i oświadczenia”.

### S14 · Podgląd – strona FINISH – `podglad_uzupelnionego_wniosku` · „Podgląd uzupełnionego wniosku”
| y | Typ | techName | Opis |
|---|---|---|---|
| 0 | TEXT_BLOCK | `podglad_1` | PODPIS=tak: „Zanim przejdziesz do wyboru sposobu podpisu, sprawdź dane na podglądzie. Jeśli zobaczysz błędy, wróć do edycji.” · PODPIS=nie: „Zanim wyślesz wniosek, sprawdź uzupełnione dane na podglądzie. Jeśli zobaczysz błędy, wróć do edycji.” |

---

## 5. Walidatory – nasze rozszerzenie (wzorce mają `[]`)

Mentor COI potwierdził 2026-11-21: puste `validation` we wzorcach nie zabrania walidatorów. Dodajemy reguły, które wynikają z pola (D13).

| Pole | validation |
|---|---|
| radia w S2, pola obowiązkowe przedmiotu wniosku, uploady obowiązkowe | `["REQUIRED"]` |
| `numer_pesel` (S3) | `[]` – pole do odczytu z rejestru (DECISIONS, P1) |
| `nip` / `regon` | `["REQUIRED", "NIP"]` / `["REQUIRED", "REGON"]`; przy `entity_ids_one_of` bez `REQUIRED` |
| `adres_e_mail` | `["EMAIL"]` |
| `kod_pocztowy*` (PL) | `["REQUIRED", "ZIP_CODE"]` |
| pola readOnly z rejestru | `[]` |
| pola TEXT_FIELD z analizy (strony przedmiotu, „Dodatkowe dane wnioskodawcy”) | walidator typu z etykiety (po `REQUIRED`, gdy pole jest wymagane): PESEL, NIP, REGON, ZIP_CODE, EMAIL, SERIAL_NUMBER_ID_CARD, EPUAP, ADE. Dwie kategorie albo etykieta złożona → bez walidatora typu (DECISIONS, P1.3a) |

Przełącznik w konfiguracji: `ADD_VALIDATORS=true/false`, żeby jednym ruchem wrócić do formatu 1:1 z wzorcem.

---

## 6. Przedmiot wniosku – co robi AI (na przykładzie nadpłaty)

| Na papierze | W JSON-ie (strona „Informacje o nadpłacie”) |
|---|---|
| „wnoszę o stwierdzenie nadpłaty z tytułu …… (rodzaj podatku)” | TEXT_FIELD `podatek_ktorego_dotyczy_nadplata` „Podatek, którego dotyczy nadpłata” |
| „w kwocie ……” | NUMBER `kwota` „Kwota” |
| „Uzasadnienie: ………” | TEXTAREA `uzasadnienie` + opis „Uzasadnij dlaczego Twoim zdaniem powstała nadpłata i z czego wynika jej wysokość.” |
| „Kwotę nadpłaty proszę: 1) zaliczyć na poczet… z tytułu …… 2) zwrócić przelewem na wskazany rachunek ……” | RADIO `wybierz_co_mamy_zrobic_z_nadplata` „Wybierz, co mamy zrobić z nadpłatą” + TEXT_FIELD `nazwa_podatku` (SHOW opcja 1) + TEXT_FIELD `numer_rachunku` (SHOW opcja 2) |
| „w załączeniu: 1) korekta deklaracji” | sekcja „Korekta deklaracji” z opisem + FILE_UPLOADER `plik_deklaracji_podatkowej` |

**Zasady przekształcenia (dla promptu).** Mentor COI potwierdził trzy z nich (D8): zachowanie treści sprawy, prosty język z warunkami SHOW oraz sekcje wnioskodawcy według papieru (rozdz. 1).
- zachowaj każdą informację potrzebną do załatwienia sprawy: dane innych osób, daty zdarzeń, załączniki, instrukcje, wybory i ich warunki (D8);
- etykiety prostym językiem, 2. osoba („Wybierz…”, „Uzasadnij…”), bez „Na podstawie art. …” (D8);
- „……” po tekście → pole; typ wg treści: kwota/liczba → NUMBER, data → DATEPICKER, uzasadnienie/opis → TEXTAREA, reszta → TEXT_FIELD;
- „proszę: 1) … 2) …” / kwadraciki □ → RADIO (jeden wybór) lub CHECKBOX (wiele); dane dopisywane przy opcji → pole z SHOW tej opcji (D8);
- „w załączeniu / załączniki:” → sekcja z opisem + FILE_UPLOADER na każdy wymieniony załącznik;
- „Oświadczam, że…” wymagane od tej samej osoby w każdej ścieżce → consent w S13; zgody opcjonalne i warunkowe zostają przy danych, których dotyczą (P1.2a);
- grupuj pola w sekcje tematyczne (tytuł sekcji = temat).

**Dane wnioskodawcy** (imię i nazwisko lub nazwa, adres, PESEL, NIP/REGON/KRS, pełnomocnik, telefon, e-mail) nie trafiają na strony przedmiotu. AI zapisuje je jako decyzje `applicant` (rozdz. 1), a dane spoza szablonu w `applicant_extra_fields` (P1.2a, D8).

**Usuwamy z papieru** (pokrywa to szablon): miejscowość i data, podpis (→ `signature`), adresat (→ `addressee`), „Na podstawie art. …”, klauzula RODO (zastępuje ją zgoda z linkiem), pola „wypełnia urząd”, przypisy.
