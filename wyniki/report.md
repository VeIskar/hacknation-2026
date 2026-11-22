# Raport generowania COI

Pliki do oceny obejmują formularze F2–F4 i F6–F9. F5 to dodatkowy pomiar na formularzu referencyjnym.

Oparcie w tekście i decyzje wnioskodawcy bez wykrytej przesłanki są przybliżeniami.

| Formularz | Wynik | E2E (s) | Próby | Lint | Oparcie (%) | Bez przesłanki | SHOW or | SHOW and | SHOW sekcje |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| F2 | OK | 8.056 | 1 | 0 | 90.9 | 0 | 1 | 3 | 7 |
| F3 | OK | 6.769 | 2 | 0 | 100.0 | 0 | 0 | 0 | 0 |
| F4 | OK | 4.918 | 1 | 0 | 100.0 | 0 | 0 | 0 | 0 |
| F5 | OK | 4.738 | 1 | 0 | 100.0 | 0 | 0 | 0 | 2 |
| F6 | OK | 34.698 | 2 | 0 | 100.0 | 0 | 0 | 0 | 1 |
| F7 | OK | 15.699 | 2 | 0 | 100.0 | 0 | 0 | 0 | 0 |
| F8 | OK | 38.863 | 1 | 0 | 88.4 | 0 | 0 | 6 | 2 |
| F9 | OK | 98.272 | 2 | 0 | 100.0 | 0 | 4 | 38 | 9 |

## F2

- **Plik i format** Wniosek o zwrot opłaty skarbowej.docx / docx
- **Czasy (s)** extract 0.024 / analyze 8.021 / build+lint 0.004 / e2e 8.056
- **Próby** 1
  - 1. HTTP 200, 8.013 s, finish_reason stop, tokeny 3721/1286
- **Korekty strażnika** 3 / uwagi 0
- **Lint** 0
- **Przedmiot** strony 1 / sekcje 6 / pola 20
- **SHOW** razem 23 / or 1 / and 3 / sekcje 7
- **Walidatory** REQUIRED × 23, ZIP_CODE × 4
- **Słowniki** Kraje × 2, TERYT_4G_DOWODOWY × 2
- **Uwagi o walidatorach** 0
- **Uwagi o słownikach** 0

## F3

- **Plik i format** Wniosek o wydanie zaświadczenia.docx / docx
- **Czasy (s)** extract 0.003 / analyze 6.758 / build+lint 0.002 / e2e 6.769
- **Próby** 2
  - 1. HTTP 200, 3.580 s, finish_reason stop, tokeny 3169/526
  - 2. HTTP 200, 3.167 s, finish_reason stop, tokeny 3788/495
- **Korekty strażnika** 0 / uwagi 0
- **Lint** 0
- **Przedmiot** strony 1 / sekcje 2 / pola 2
- **SHOW** razem 6 / or 0 / and 0 / sekcje 0
- **Walidatory** REQUIRED × 3, ZIP_CODE × 1
- **Słowniki** Kraje × 1, TERYT_4G_DOWODOWY × 1
- **Uwagi o walidatorach** 0
- **Uwagi o słownikach** 0

## F4

- **Plik i format** Wniosek o wynajęcie świetlicy.docx / docx
- **Czasy (s)** extract 0.002 / analyze 4.908 / build+lint 0.002 / e2e 4.918
- **Próby** 1
  - 1. HTTP 200, 4.905 s, finish_reason stop, tokeny 3161/816
- **Korekty strażnika** 3 / uwagi 0
- **Lint** 0
- **Przedmiot** strony 1 / sekcje 4 / pola 6
- **SHOW** razem 6 / or 0 / and 0 / sekcje 0
- **Walidatory** REQUIRED × 6, ZIP_CODE × 1
- **Słowniki** Kraje × 1, TERYT_4G_DOWODOWY × 1
- **Uwagi o walidatorach** 0
- **Uwagi o słownikach** 0

## F5

- **Plik i format** Wniosek o stwierdzenie nadpłaty podatku.docx / docx
- **Czasy (s)** extract 0.003 / analyze 4.726 / build+lint 0.003 / e2e 4.738
- **Próby** 1
  - 1. HTTP 200, 4.722 s, finish_reason stop, tokeny 3029/768
- **Korekty strażnika** 3 / uwagi 0
- **Lint** 0
- **Przedmiot** strony 1 / sekcje 4 / pola 8
- **SHOW** razem 14 / or 0 / and 0 / sekcje 2
- **Walidatory** REQUIRED × 10, ZIP_CODE × 2
- **Słowniki** Kraje × 2, TERYT_4G_DOWODOWY × 2
- **Uwagi o walidatorach** 0
- **Uwagi o słownikach** 0

## F6

- **Plik i format** Wniosek o wydanie zezwolenia na zajęcie pasa drogowego.docx / docx
- **Czasy (s)** extract 0.002 / analyze 34.685 / build+lint 0.003 / e2e 34.698
- **Próby** 2
  - 1. HTTP 200, 20.124 s, finish_reason stop, tokeny 3852/3452
  - 2. HTTP 200, 14.551 s, finish_reason stop, tokeny 7427/2320
- **Korekty strażnika** 2 / uwagi 0
- **Lint** 0
- **Przedmiot** strony 1 / sekcje 5 / pola 25
- **SHOW** razem 11 / or 0 / and 0 / sekcje 1
- **Walidatory** REQUIRED × 27, ZIP_CODE × 1
- **Słowniki** Kraje × 1, TERYT_4G_DOWODOWY × 1
- **Uwagi o walidatorach** 0
- **Uwagi o słownikach** 0

## F7

- **Plik i format** Wniosek o wydanie zezwolenia na hodowanie lub utrzymywanie psów ras uznawanychza agresywne.PDF / pdf
- **Czasy (s)** extract 0.065 / analyze 15.623 / build+lint 0.002 / e2e 15.699
- **Próby** 2
  - 1. HTTP 200, 8.481 s, finish_reason stop, tokeny 4349/1406
  - 2. HTTP 200, 7.133 s, finish_reason stop, tokeny 5871/1159
- **Korekty strażnika** 2 / uwagi 0
- **Lint** 0
- **Przedmiot** strony 1 / sekcje 3 / pola 17
- **SHOW** razem 6 / or 0 / and 0 / sekcje 0
- **Walidatory** REQUIRED × 5, ZIP_CODE × 2
- **Słowniki** Kraje × 1, TERYT_4G_DOWODOWY × 1
- **Uwagi o walidatorach** 0
- **Uwagi o słownikach** 0

## F8

- **Plik i format** Deklaracja o wysokości opłaty.docx / docx
- **Czasy (s)** extract 0.119 / analyze 38.713 / build+lint 0.006 / e2e 38.863
- **Próby** 1
  - 1. HTTP 200, 38.708 s, finish_reason stop, tokeny 13211/5305
- **Korekty strażnika** 5 / uwagi 1
- **Lint** 0
- **Przedmiot** strony 1 / sekcje 13 / pola 77
- **SHOW** razem 23 / or 0 / and 6 / sekcje 2
- **Walidatory** EMAIL × 1, NIP × 1, REGON × 1, REQUIRED × 35, ZIP_CODE × 6
- **Słowniki** Kraje × 5, TERYT_4G_DOWODOWY × 3
- **Uwagi o walidatorach** 0
- **Uwagi o słownikach** 0

## F9

- **Plik i format** Wniosek o przyznanie stypendium.docx / docx
- **Czasy (s)** extract 0.011 / analyze 98.233 / build+lint 0.009 / e2e 98.272
- **Próby** 2
  - 1. HTTP 200, 46.031 s, finish_reason stop, tokeny 6991/7079
  - 2. HTTP 200, 52.184 s, finish_reason stop, tokeny 14193/6979
- **Korekty strażnika** 1 / uwagi 0
- **Lint** 0
- **Przedmiot** strony 1 / sekcje 9 / pola 54
- **SHOW** razem 61 / or 4 / and 38 / sekcje 9
- **Walidatory** EPUAP × 1, REQUIRED × 45, SERIAL_NUMBER_ID_CARD × 1, ZIP_CODE × 2
- **Słowniki** Kraje × 2, TERYT_4G_DOWODOWY × 2
- **Uwagi o walidatorach** 0
- **Uwagi o słownikach** 0
