// Atrapy do podglądu eUsługi (SPEC.md "Real and mocked"). Wszystkie wartości są zmyślone.
// PESEL, NIP i REGON mają poprawne sumy kontrolne: pilnuje tego src/preview/validators.test.ts.

/** Dane inicjalne z rejestru. Klucz to `defaultValue` pola z `defaultValueType: EXTERNAL_SYSTEM`. */
export const INITIAL_DATA: Readonly<Record<string, string>> = {
  'MLPZ.name': 'Anna',
  'MLPZ.surname': 'Przykładowa',
  'MLPZ.pesel': '85071201244',
  'MLPZ.postCode': '00-950',
  'MLPZ.city': 'Warszawa',
  'MLPZ.street': 'Przykładowa',
  'MLPZ.building': '12',
  'MLPZ.apartment': '3',
  'MLPZ.phoneNumber': '500 600 700',
  'MLPZ.email': 'anna.przykladowa@example.com',
}

/** Przykładowy podmiot do zrzutów i testów walidatorów. */
export const DEMO_ENTITY = {
  name: 'Przykładowa Spółka z o.o.',
  nip: '1234563218',
  regon: '123456785',
} as const

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
