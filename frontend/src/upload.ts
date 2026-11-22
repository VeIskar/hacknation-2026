// Kontrola pliku w przeglądarce, zanim trafi do API. Te same reguły i te same słowa co
// w backend/app/files.py (SPEC "API contract"), więc urzędnik widzi jeden komunikat niezależnie
// od tego, kto błąd wykrył. Zawartości pliku nie sprawdzamy: to robi API (krok 8 w demo).

export const MAX_NAME_LENGTH = 250
const FORBIDDEN_NAME_CHARS = new Set([...";:></\\|'*%$"])
/** Limit z SPEC "API contract" i env.example (`MAX_FILE_SIZE_MB=10`). Serwer i tak sprawdza swój. */
export const MAX_FILE_MB = 10

export const ACCEPTED_EXTENSIONS = ['pdf', 'doc', 'docx', 'ods', 'xlsx', 'jpg', 'jpeg', 'jpe', 'png'] as const
export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(',')

export const MSG_NAME = 'Nazwa pliku jest za długa albo ma niedozwolone znaki.'
export const MSG_TYPE = 'Ten typ pliku nie jest obsługiwany. Wybierz PDF, DOC, DOCX, ODS, XLSX, JPG albo PNG.'
export const MSG_EMPTY = 'Plik jest pusty. Wybierz inny plik.'
export const MSG_TOO_LARGE = `Plik jest za duży. Limit to ${MAX_FILE_MB} MB.`

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase()
}

function nameIsValid(name: string): boolean {
  if (name === '' || name.length > MAX_NAME_LENGTH) return false
  return ![...name].some((char) => FORBIDDEN_NAME_CHARS.has(char) || char.charCodeAt(0) < 32)
}

/** Komunikat błędu albo `null`, gdy plik można wysłać. Kolejność jak w API: nazwa, rozmiar, typ. */
export function fileProblem(file: Pick<File, 'name' | 'size'>): string | null {
  if (!nameIsValid(file.name)) return MSG_NAME
  if (file.size > MAX_FILE_MB * 1024 * 1024) return MSG_TOO_LARGE
  if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(extensionOf(file.name))) return MSG_TYPE
  if (file.size === 0) return MSG_EMPTY
  return null
}
