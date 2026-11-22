// Atrapy do podglądu eUsługi (SPEC.md "Real and mocked"). Wszystkie wartości są zmyślone.
// PESEL, NIP i REGON mają poprawne sumy kontrolne: pilnuje tego src/preview/validators.test.ts.

/**
 * Dane inicjalne. Klucz to `defaultValue` pola z `defaultValueType: EXTERNAL_SYSTEM`, czyli
 * źródło i atrybut z materiału COI „Dane inicjalne” (komplet atrybutów PESEL, PESEL_ADDRESS, MLPZ).
 * Jedna zmyślona osoba: PESEL 85071201244 to kobieta urodzona 12 lipca 1985 (pilnuje test).
 * Pusty tekst to atrybut bez danych w źródle. Wtedy pole zostaje puste, jak każe COI.
 */
export const INITIAL_DATA: Readonly<Record<string, string>> = {
  'PESEL.pesel': '85071201244',
  'PESEL.name': 'Anna',
  'PESEL.surname': 'Przykładowa',
  'PESEL.birthDate': '1985-07-12',
  'PESEL.citizenship': 'polskie',
  'PESEL.motherName': 'Maria',
  'PESEL.birthPlace': 'Warszawa',
  'PESEL.motherSurname': 'Przykładowa',
  'PESEL.sex': 'kobieta',
  'PESEL.fatherName': 'Jan',
  'PESEL.secondName': 'Zofia',
  'PESEL.birthCountry': 'Polska',
  'PESEL.foreignBirthUSC': '',
  'PESEL.familyName': 'Przykładowa',
  'PESEL.fatherSurname': 'Przykładowy',
  'PESEL.maritalStatus': 'panna',
  // Brak zameldowania tymczasowego: przykład źródła bez danych.
  'PESEL_ADDRESS.temporaryAddressVoivodeship': '',
  'PESEL_ADDRESS.temporaryAddressDistrict': '',
  'PESEL_ADDRESS.temporaryAddressCommunity': '',
  'PESEL_ADDRESS.temporaryAddressPlace': '',
  'PESEL_ADDRESS.temporaryAddressStreetType': '',
  'PESEL_ADDRESS.temporaryAddressStreet': '',
  'PESEL_ADDRESS.temporaryAddressHouseNumber': '',
  'PESEL_ADDRESS.temporaryAddressApartmentNumber': '',
  'PESEL_ADDRESS.temporaryAddressPostalCode': '',
  'PESEL_ADDRESS.permanentAddressVoivodeship': 'mazowieckie',
  'PESEL_ADDRESS.permanentAddressDistrict': 'Warszawa',
  'PESEL_ADDRESS.permanentAddressCommunity': 'Warszawa',
  'PESEL_ADDRESS.permanentAddressPlace': 'Warszawa',
  'PESEL_ADDRESS.permanentAddressStreetType': 'ulica',
  'PESEL_ADDRESS.permanentAddressStreet': 'Przykładowa',
  'PESEL_ADDRESS.permanentAddressPostalCode': '00-950',
  'PESEL_ADDRESS.permanentAddressHouseNumber': '12',
  'PESEL_ADDRESS.permanentAddressApartmentNumber': '3',
  'MLPZ.name': 'Anna',
  'MLPZ.secondName': 'Zofia',
  'MLPZ.surname': 'Przykładowa',
  'MLPZ.pesel': '85071201244',
  'MLPZ.phoneNumber': '500 600 700',
  'MLPZ.email': 'anna.przykladowa@example.com',
  'MLPZ.country': 'Polska',
  'MLPZ.voivodeship': 'mazowieckie',
  'MLPZ.district': 'Śródmieście',
  'MLPZ.community': 'Warszawa',
  'MLPZ.place': 'Warszawa',
  'MLPZ.postCode': '00-950',
  'MLPZ.street': 'Przykładowa',
  'MLPZ.building': '12',
  'MLPZ.apartment': '3',
  // Osoba fizyczna bez organizacji.
  'MLPZ.institutionName': '',
  'MLPZ.descriptiveOrganizationName': '',
}

/** Przykładowy podmiot do zrzutów i testów walidatorów. */
export const DEMO_ENTITY = {
  name: 'Przykładowa Spółka z o.o.',
  nip: '1234563218',
  regon: '123456785',
} as const

/** Przykładowa seria i numer dowodu osobistego z poprawną cyfrą kontrolną. */
export const DEMO_ID_CARD = 'ABA300000'

const VOIVODESHIPS = [
  'dolnośląskie',
  'kujawsko-pomorskie',
  'lubelskie',
  'lubuskie',
  'łódzkie',
  'małopolskie',
  'mazowieckie',
  'opolskie',
  'podkarpackie',
  'podlaskie',
  'pomorskie',
  'śląskie',
  'świętokrzyskie',
  'warmińsko-mazurskie',
  'wielkopolskie',
  'zachodniopomorskie',
]

/** Słowniki COI po `dictionaryName`. Podgląd pokazuje pierwszy poziom słownika TERYT. */
export const DICTIONARIES: Readonly<Record<string, readonly string[]>> = {
  Kraje: ['Polska', 'Austria', 'Czechy', 'Francja', 'Hiszpania', 'Litwa', 'Niemcy', 'Słowacja', 'Ukraina', 'Włochy'],
  TERYT_4G_DOWODOWY: VOIVODESHIPS,
  TERYT_DOWODOWY: VOIVODESHIPS,
  Województwo: VOIVODESHIPS,
}
