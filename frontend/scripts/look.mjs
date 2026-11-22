// Oczy: przechodzi przepływ na atrapie modelu i zapisuje zrzuty każdego stanu w 1440 i 390 px
// do frontend/shots/. Sprawdza też krok 8 (zły typ pliku), pobranie pliku JSON i podgląd eUsługi:
// dane z rejestru, warunek SHOW, błąd walidacji, przejście do strony końcowej.
//
// Papier na zrzutach ma być prawdziwy. Skrypt szuka materiałów COI (poza gitem) w LOOK_MATERIALY,
// w materialy/ obok repozytorium i w głównym katalogu roboczym gita. Pełny przepływ idzie na
// PDF-ie z folderu 5 (zrzuty f1-* i f2-*), a krótki, do wyniku, na PDF-ie z folderu 9 (p9-*).
// Bez materiałów zostaje plik generowany tutaj i skrypt mówi o tym na końcu.
//
// Modelu skrypt nie woła. JSON formularza buduje prawdziwy generator API z analizy zapisanej
// w backend/tests/fixtures/: fields.json dla folderu 5 i analysis_form9.json dla folderu 9.
// Drugie API stoi na osobnym porcie, a przeglądarka kieruje do niego żądanie krótkiego przepływu.
//
// Użycie (z katalogu frontend/):
//   node scripts/look.mjs                      PDF-y z materialy/ albo plik generowany tutaj
//   node scripts/look.mjs /sciezka/wniosek.pdf wskazany plik w pełnym przepływie
//
// Skrypt startuje własne API z LLM_FIXTURE i własny serwer Vite na osobnych portach, więc nie
// trafi w API bez atrapy ani w serwery innej sesji. Na końcu oba zatrzymuje.
import { AxeBuilder } from '@axe-core/playwright'
import { chromium } from '@playwright/test'
import { execFileSync, spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdir, readFile, readdir } from 'node:fs/promises'
import { basename, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = dirname(dirname(fileURLToPath(import.meta.url)))
const root = dirname(frontend)
const shots = join(frontend, 'shots')
const apiPort = Number(process.env.LOOK_API_PORT ?? 8017)
const webPort = Number(process.env.LOOK_WEB_PORT ?? 5183)
const api = `http://localhost:${apiPort}`
const web = `http://localhost:${webPort}`
const fixture = join(root, 'backend', 'tests', 'fixtures', 'fields.json')
const secondApi = `http://localhost:${apiPort + 1}`
const secondFixture = join(root, 'backend', 'tests', 'fixtures', 'analysis_form9.json')
// Trzecie API wymaga tokenu (JWT_ENABLED=true). Sekret żyje tylko w tym procesie.
const jwtApi = `http://localhost:${apiPort + 2}`
const jwtSecret = 'look-' + 'x'.repeat(40)
const axeTags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
const viewports = [
  [1440, 900],
  [390, 844],
]

function samplePdf() {
  const lines = ['WNIOSEK O WYDANIE ZASWIADCZENIA', 'Imie i nazwisko', 'PESEL', 'Adres zamieszkania', 'Kod pocztowy']
  const text = lines.map((line, i) => `${i === 0 ? '72 760 Td' : '0 -32 Td'} (${line}) Tj`).join(' ')
  const stream = `BT /F1 14 Tf ${text} ET`
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ]
  let pdf = '%PDF-1.4\n'
  const offsets = []
  objects.forEach((body, i) => {
    offsets.push(pdf.length)
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`
  })
  const xref = pdf.length
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  pdf += offsets.map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(pdf, 'latin1')
}

// Materiały COI leżą poza gitem, zwykle tylko w głównym katalogu roboczym, nie w worktree.
function materialsDir() {
  const candidates = [process.env.LOOK_MATERIALY, join(root, 'materialy')]
  try {
    const common = execFileSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], { cwd: root, encoding: 'utf-8' })
    candidates.push(join(dirname(common.trim()), 'materialy'))
  } catch {
    // Poza repozytorium gita zostają dwa pierwsze miejsca.
  }
  return candidates.find((path) => path && existsSync(path)) ?? null
}

async function firstPdf(directory, folderPrefix) {
  const folder = (await readdir(directory)).find((name) => name.startsWith(folderPrefix))
  if (!folder) return null
  const pdf = (await readdir(join(directory, folder))).find((name) => name.toLowerCase().endsWith('.pdf'))
  return pdf ? join(directory, folder, pdf) : null
}

async function realPdfs() {
  const directory = materialsDir()
  if (!directory) return { main: null, second: null }
  return { main: await firstPdf(directory, '5. '), second: await firstPdf(directory, '9. ') }
}

// Wzorce COI (folder 1 i 5) i zapisane wyniki API z LOOK_JSON_DIR albo z generated-forms-final/
// obok repozytorium. Wszystko poza gitem; bez tych plików kontrola jest pusta i mówi o tym.
async function anyJsonFiles() {
  const files = []
  const directory = materialsDir()
  if (directory) {
    for (const folder of (await readdir(directory)).filter((name) => /^[15]\. /.test(name))) {
      for (const name of await readdir(join(directory, folder))) if (name.endsWith('.json')) files.push(join(directory, folder, name))
    }
  }
  const saved = process.env.LOOK_JSON_DIR ?? join(dirname(root), 'generated-forms-final')
  if (existsSync(saved)) {
    for (const name of (await readdir(saved)).sort()) if (name.endsWith('.coi.json')) files.push(join(saved, name))
  }
  return files
}

async function responds(url) {
  try {
    await fetch(url, { signal: AbortSignal.timeout(1000) })
    return true
  } catch {
    return false
  }
}

async function waitFor(url, label) {
  for (let i = 0; i < 120; i++) {
    if (await responds(url)) return
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`${label} nie wystartował pod ${url}`)
}

const children = []
function start(command, args, options) {
  const child = spawn(command, args, { stdio: ['ignore', 'ignore', 'inherit'], ...options })
  children.push(child)
  return child
}
function stopAll() {
  for (const child of children) child.kill('SIGTERM')
}

const failures = []
let jwtToken = ''
function check(name, ok, detail = '') {
  console.log(`${ok ? 'OK  ' : 'BŁĄD'} ${name}${detail ? `: ${detail}` : ''}`)
  if (!ok) failures.push(name)
}

// Podgląd eUsługi na atrapie modelu: etykiety niżej pochodzą z backend/tests/fixtures/fields.json.
async function preview(page, width, shot) {
  const region = (name) => page.getByRole('region', { name })
  const pageTitle = (name) => page.getByRole('heading', { level: 3, name })
  const next = page.getByRole('button', { name: 'Dalej' })
  const focused = (selector) => page.evaluate((query) => document.activeElement?.matches(query) ?? false, selector)

  const pesel = region('Twoje dane').getByLabel('Numer PESEL')
  check(
    `${width}: PESEL z rejestru ma 11 cyfr i jest tylko do odczytu`,
    /^\d{11}$/.test(await pesel.inputValue()) && !(await pesel.isEditable()),
  )
  check(`${width}: krok jest podany tekstem`, await page.getByText('Krok 1 z 4', { exact: true }).isVisible())
  check(`${width}: sekcja z niespełnionym SHOW nie istnieje w DOM`, (await region('Dane innej osoby').count()) === 0)
  const ownZip = await region('Adres zamieszkania').getByLabel('Kod pocztowy').count()
  check(`${width}: przy kraju „Polska” jest jedno pole „Kod pocztowy”`, ownZip === 1, String(ownZip))
  await shot('01-dane')

  await page.getByRole('radio', { name: 'Innej osoby' }).check()
  const otherAddress = region('Adres zamieszkania innej osoby')
  await otherAddress.waitFor()
  check(`${width}: „Innej osoby” pokazuje „Dane innej osoby”`, await region('Dane innej osoby').isVisible())
  await shot('02-innej-osoby')

  const zip = otherAddress.getByLabel('Kod pocztowy')
  await zip.fill('12345')
  await next.click()
  const zipError = otherAddress.getByText('Wpisz kod pocztowy w formacie 00-000')
  await zipError.waitFor()
  check(`${width}: po błędach fokus stoi na podsumowaniu`, await focused('.eu-summary'))
  check(`${width}: błędne pole ma aria-invalid`, (await zip.getAttribute('aria-invalid')) === 'true')
  const summaryLinks = await page.locator('.eu-summary a').evaluateAll((links) => links.map((link) => link.getBoundingClientRect().height))
  check(`${width}: linki podsumowania mają co najmniej 44 px`, summaryLinks.every((height) => height >= 44), summaryLinks.join(', '))
  check(`${width}: błąd zatrzymuje na stronie „Dane”`, await pageTitle('Dane').isVisible())
  await shot('03-blad-walidacji')
  await page.locator('.eu-summary').getByRole('link', { name: 'Wpisz kod pocztowy w formacie 00-000' }).click()
  check(`${width}: link z podsumowania przenosi fokus do pola`, await zip.evaluate((el) => el === document.activeElement))

  await page.getByRole('radio', { name: 'Swoim' }).check()
  await region('Dane innej osoby').waitFor({ state: 'detached' })
  check(`${width}: błędy pól z ukrytych sekcji znikają z podsumowania`, (await page.locator('.eu-summary').count()) === 0)
  await next.click()
  await pageTitle('Informacje o nadpłacie').waitFor()
  check(`${width}: po zmianie strony fokus stoi na jej tytule`, await focused('.eu-page'))
  await page.getByLabel('Podatek, którego dotyczy nadpłata').fill('Podatek od nieruchomości')
  await page.getByLabel('Kwota').fill('120,50')
  await page.getByLabel('Uzasadnienie').fill('Podatek został zapłacony dwa razy.')
  await page.getByRole('radio', { name: 'Zwrócić przelewem na rachunek bankowy' }).check()
  await page.getByLabel('Numer rachunku').fill('61 1090 1014 0000 0712 1981 2874')
  await page
    .getByLabel('Plik deklaracji podatkowej')
    .setInputFiles({ name: 'korekta-deklaracji.pdf', mimeType: 'application/pdf', buffer: samplePdf() })
  await next.click()
  await pageTitle('Kontakt i zgody').waitFor()

  await page.getByRole('button', { name: 'Wstecz' }).click()
  await pageTitle('Informacje o nadpłacie').waitFor()
  const amount = await page.getByLabel('Kwota').inputValue()
  check(`${width}: odpowiedzi zostają po „Wstecz”`, amount === '120,50', amount)
  await next.click()
  await pageTitle('Kontakt i zgody').waitFor()

  await next.click()
  await page.locator('.eu-summary').waitFor()
  check(`${width}: wymagana zgoda zatrzymuje „Dalej”`, await pageTitle('Kontakt i zgody').isVisible())
  await page.getByRole('checkbox', { name: /Wyrażam zgodę/ }).check()
  await next.click()
  await pageTitle('Strona końcowa').waitFor()
  check(`${width}: strona końcowa to „Krok 4 z 4”`, await page.getByText('Krok 4 z 4', { exact: true }).isVisible())
  check(`${width}: strona końcowa nie ma „Dalej”`, (await next.count()) === 0)
  check(`${width}: strona końcowa pokazuje wpisaną kwotę`, await page.locator('.eu-review').getByText('120,50').isVisible())
  await shot('04-strona-koncowa')
}

// Papier stoi obok od 1200 px. Węziej jest zwinięty do przycisku „Pokaż oryginał”.
const PAPER_BESIDE_FROM = 1200

// Podgląd, liczby, JSON i nazwa pliku mają dotyczyć jednego dokumentu. Liczymy z JSON-a pokazanego
// w panelu i porównujemy z resztą ekranu. Działa dla każdego formularza, nie tylko dla atrapy.
async function sameDocument(page, source, label) {
  const showJson = page.getByRole('button', { name: 'Pokaż JSON' })
  await showJson.click()
  const form = JSON.parse(await page.locator('.json').textContent())
  const sections = form.tabs.flatMap((tab) => tab.questions.map((cell) => cell.field))
  const fields = sections.flatMap((section) => section.repeatingSectionGrid.map((cell) => cell.field))
  const numbers = (await page.locator('.liczby').textContent()) ?? ''
  const [, pages, sectionCount, fieldCount] = numbers.match(/^(\d+) \S+, (\d+) \S+ i (\d+) \S+\./) ?? []
  const shown = `${pages} stron, ${sectionCount} sekcji, ${fieldCount} pól`
  const counted = `${form.tabs.length} stron, ${sections.length} sekcji, ${fields.length} pól`
  check(`${label}: liczby w nagłówku to liczby z JSON-a`, shown === counted, `nagłówek ${shown}, JSON ${counted}`)
  const bar = await page.locator('.eu-bar span').count()
  check(`${label}: pasek kroków ma tyle odcinków, ile stron`, bar === form.tabs.length, String(bar))
  await showJson.click()
  check(`${label}: krok podglądu liczy strony z JSON-a`, await page.getByText(`Krok 1 z ${form.tabs.length}`, { exact: true }).isVisible())
  check(`${label}: tytuł wniosku pochodzi z JSON-a`, await page.getByRole('heading', { level: 2, name: form.title, exact: true }).isVisible(), form.title)
  check(`${label}: pierwsza strona podglądu to pierwsza strona JSON-a`, await page.getByRole('heading', { level: 3, name: form.tabs[0].title, exact: true }).isVisible())
  check(`${label}: nazwa pliku na ekranie to wczytany plik`, await page.getByText(source.name).first().isVisible(), source.name)
  const always = form.tabs[0].questions.map((cell) => cell.field).filter((section) => section.states.length === 0)
  const missing = []
  for (const section of always) {
    if ((await page.getByRole('region', { name: section.title, exact: true }).count()) === 0) missing.push(section.title)
  }
  check(`${label}: każda sekcja bez warunku jest w podglądzie (${always.length})`, missing.length === 0, missing.join(', '))
  return form
}

// Stany wspólne dla każdego pliku: pusty start, wybrany plik, oczekiwanie i wynik.
// `apiUrl` kieruje żądanie analizy do innego API niż to, które stoi za serwerem Vite.
async function toResult(page, source, width, shot, label, apiUrl = null) {
  await page.goto(web)
  await page.getByRole('heading', { level: 1, name: 'Wczytaj formularz' }).waitFor()
  await page.evaluate(() => document.fonts.ready)
  check(`${label}: start nie pokazuje papieru przed wyborem pliku`, (await page.getByRole('region', { name: 'Oryginał' }).count()) === 0)
  await shot(page, '01-pusty')

  await page.getByLabel('Plik formularza').setInputFiles(source)
  const sheet = page.locator('[data-ready="true"]')
  if (width >= PAPER_BESIDE_FROM) {
    await sheet.waitFor({ timeout: 20_000 })
    await shot(page, '02-plik-wybrany')
  } else {
    const toggle = page.getByRole('button', { name: 'Pokaż pierwszą stronę' })
    await toggle.waitFor()
    // Pytamy o całą treść papieru, nie o płótno: płótno jest niewidoczne także wtedy, gdy PDF jeszcze się rysuje.
    check(`${label}: wąski ekran zwija papier do przycisku`, !(await page.locator('#papier-tresc').isVisible()))
    await shot(page, '02-plik-wybrany')
    await toggle.click()
    await sheet.waitFor({ timeout: 20_000 })
    await shot(page, '02b-oryginal')
    await page.getByRole('button', { name: 'Ukryj pierwszą stronę' }).click()
  }

  // Oczekiwanie: atrapa odpowiada od razu, więc odpowiedź wstrzymujemy tutaj, nie w aplikacji.
  let release
  const held = new Promise((resolve) => {
    release = resolve
  })
  await page.route('**/api/forms', async (route) => {
    await held
    await route.continue(apiUrl ? { url: `${apiUrl}/api/forms` } : {})
  })
  await page.getByRole('button', { name: 'Analizuj formularz' }).click()
  await page.getByRole('heading', { level: 1, name: 'Analiza formularza' }).waitFor()
  await page.clock.fastForward(72_000)
  await shot(page, '03-oczekiwanie')
  release()

  await page.getByRole('heading', { level: 1, name: 'Podgląd eUsługi' }).waitFor({ timeout: 20_000 })
  await page.unroute('**/api/forms')
  check(`${label}: po wyniku fokus stoi na nagłówku h1`, await page.evaluate(() => document.activeElement?.tagName === 'H1'))
  if (width < PAPER_BESIDE_FROM) check(`${label}: na telefonie JSON jest zwinięty pod podglądem`, !(await page.locator('#json-tresc').isVisible()))
  await shot(page, '04-wynik')
}

function watch(page) {
  const errors = []
  page.on('pageerror', (error) => errors.push(String(error)))
  return errors
}

// Każdy stan dostaje zrzut i kontrolę axe z tymi samymi tagami co tests/e2e/a11y.spec.ts.
function shooter(prefix, width, label) {
  return async (target, name, group = prefix) => {
    await target.screenshot({ path: join(shots, `${group}-${name}-${width}.png`), fullPage: true })
    const result = await new AxeBuilder({ page: target }).withTags(axeTags).analyze()
    const found = result.violations.map((violation) => `${violation.id} (${violation.nodes[0].target.join(' ')})`)
    check(`${label}: axe ${name}`, found.length === 0, found.join(', '))
  }
}

// F3a: wczytanie i analiza bez szczęśliwej ścieżki. Kontrola pliku w przeglądarce, przerwanie,
// błędy API i serwera pośredniego, token przy JWT_ENABLED=true, fokus i cele 44 px.
async function uploadChecks(browser, source, [width, height]) {
  const label = `wczytaj ${width}`
  const context = await browser.newContext({ viewport: { width, height }, locale: 'pl-PL' })
  const page = await context.newPage()
  const errors = watch(page)
  const shot = shooter('f3', width, label)
  const analyze = page.getByRole('button', { name: 'Analizuj formularz' })
  const alert = page.locator('#plik-blad')
  const focused = (selector) => page.evaluate((query) => document.activeElement?.matches(query) ?? false, selector)
  let requests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/forms')) requests++
  })

  await page.goto(web)
  await page.getByRole('heading', { level: 1, name: 'Wczytaj formularz' }).waitFor()
  check(`${label}: pusta strefa nie ma jeszcze przycisku „Analizuj formularz”`, (await analyze.count()) === 0)
  check(`${label}: „Jak to działa” jest na ekranie`, await page.getByRole('heading', { level: 2, name: 'Jak to działa' }).isVisible())
  check(`${label}: opis mówi o limicie 10 MB`, await page.getByText('Najwyżej 10 MB.').isVisible())

  // Klawiatura: pierwszy Tab w treści trafia do pola pliku, a obrys rysuje strefa.
  await page.locator('#plik').focus()
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  const ring = await page.locator('.strefa').evaluate((element) => getComputedStyle(element).outlineStyle)
  check(`${label}: pole pliku z klawiatury ma obrys na strefie`, (await focused('#plik')) && ring === 'solid', ring)

  // Kontrola w przeglądarce: zły typ, pusty plik i za duży plik nie idą do API.
  const cases = [
    [{ name: 'wniosek.txt', mimeType: 'text/plain', buffer: Buffer.from('tekst') }, 'Ten typ pliku nie jest obsługiwany'],
    [{ name: 'pusty.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(0) }, 'Plik jest pusty'],
    [{ name: 'duzy.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(10 * 1024 * 1024 + 1, 32) }, 'Limit to 10 MB'],
  ]
  for (const [file, expected] of cases) {
    await page.getByLabel('Plik formularza').setInputFiles(file)
    await analyze.click()
    await alert.waitFor()
    const text = (await alert.textContent()) ?? ''
    check(`${label}: ${file.name} zatrzymany przed wysłaniem`, text.includes(expected) && requests === 0, `${text} (żądań: ${requests})`)
    check(`${label}: po błędzie pliku fokus stoi na komunikacie`, await focused('#plik-blad'))
    check(`${label}: pole pliku ma aria-invalid przy błędzie`, (await page.locator('#plik').getAttribute('aria-invalid')) === 'true')
  }
  await shot(page, '01-zly-typ')

  // Karta pliku: nazwa, rozmiar, liczba stron i odsyłacz „Zmień plik” z celem 44 px.
  await page.getByLabel('Plik formularza').setInputFiles(source)
  check(`${label}: wybór nowego pliku czyści błąd`, (await alert.count()) === 0)
  const card = page.locator('#plik-stan')
  await page.getByText(/\d+ (strona|strony|stron)$/).first().waitFor({ timeout: 20_000 })
  check(`${label}: karta pliku podaje nazwę i liczbę stron`, ((await card.textContent()) ?? '').includes(source.name))
  const change = await page.locator('.strefa-akcja').boundingBox()
  check(`${label}: odsyłacz „Zmień plik” ma co najmniej 44 px`, change.height >= 44 && change.width >= 44, `${change.width}×${change.height}`)
  check(`${label}: nazwa pola pliku zawiera „Zmień plik”`, (await page.getByRole('button', { name: /Plik formularza Zmień plik/ }).count()) + (await page.getByLabel('Plik formularza Zmień plik').count()) > 0)

  // Przerwanie: żądanie wisi, „Przerwij analizę” wraca do pliku z uczciwym komunikatem.
  let release
  const held = new Promise((resolve) => {
    release = resolve
  })
  await page.route('**/api/forms', async (route) => {
    await held
    await route.continue().catch(() => {})
  })
  await analyze.click()
  await page.getByRole('heading', { level: 1, name: 'Analiza formularza' }).waitFor()
  check(`${label}: na ekranie analizy fokus stoi na nagłówku`, await focused('h1'))
  await page.getByRole('button', { name: 'Przerwij analizę' }).click()
  const notice = page.locator('#plik-uwaga')
  await notice.waitFor()
  const noticeText = (await notice.textContent()) ?? ''
  check(`${label}: po przerwaniu komunikat nie obiecuje zatrzymania serwera`, noticeText.includes('Serwer mógł jeszcze dokończyć pracę'), noticeText)
  check(`${label}: po przerwaniu fokus stoi na komunikacie`, await focused('#plik-uwaga'))
  check(`${label}: po przerwaniu plik zostaje wybrany`, ((await card.textContent()) ?? '').includes(source.name))
  await shot(page, '02-przerwano')
  release()
  await page.unroute('**/api/forms')

  // Błędy API: detail bez zmian. Serwer pośredni bez detail i brak sieci: własne zdanie.
  const responses = [
    [{ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Model AI nie odpowiada. Spróbuj ponownie za chwilę.' }) }, 'Model AI nie odpowiada. Spróbuj ponownie za chwilę.'],
    [{ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Coś poszło nie tak. Spróbuj ponownie.' }) }, 'Coś poszło nie tak. Spróbuj ponownie.'],
    [{ status: 504, contentType: 'text/html', body: '<html>504 Gateway Time-out</html>' }, 'Serwer nie odpowiedział na czas. Spróbuj ponownie za chwilę.'],
    [{ status: 413, contentType: 'text/html', body: '<html>413</html>' }, 'Plik jest za duży dla serwera. Wybierz mniejszy plik.'],
    ['abort', 'Nie udało się połączyć z serwerem. Spróbuj ponownie.'],
  ]
  for (const [response, expected] of responses) {
    await page.route('**/api/forms', (route) => (response === 'abort' ? route.abort('failed') : route.fulfill(response)))
    await analyze.click()
    await alert.waitFor()
    const text = (await alert.textContent()) ?? ''
    check(`${label}: ${response === 'abort' ? 'brak sieci' : response.status} daje „${expected}”`, text === expected, text)
    check(`${label}: po błędzie API zostaje karta pliku`, ((await card.textContent()) ?? '').includes(source.name))
    await page.unroute('**/api/forms')
  }
  await shot(page, '03-blad-serwera')

  // Token: prawdziwe API z JWT_ENABLED=true. 401 odsłania pole tokenu, zły token daje znów 401.
  await page.route('**/api/forms', (route) => route.continue({ url: `${jwtApi}/api/forms` }))
  await analyze.click()
  const tokenField = page.getByLabel('Token dostępu')
  await tokenField.waitFor()
  const unauthorized = (await alert.textContent()) ?? ''
  check(`${label}: 401 pokazuje detail z API`, unauthorized === 'Brak tokenu dostępu albo token jest nieważny.', unauthorized)
  check(`${label}: po 401 fokus stoi na komunikacie`, await focused('#plik-blad'))
  await shot(page, '04-token')
  await analyze.click()
  check(`${label}: pusty token zatrzymuje wysłanie`, ((await alert.textContent()) ?? '').includes('Wklej token'))
  await tokenField.fill('zly.token.jwt')
  await analyze.click()
  await page.waitForFunction(() => document.querySelector('#plik-blad')?.textContent?.startsWith('Brak tokenu'))
  check(`${label}: zły token daje 401`, ((await alert.textContent()) ?? '').startsWith('Brak tokenu'))
  let header = ''
  page.on('request', (request) => {
    if (request.url().endsWith('/api/forms')) header = request.headers().authorization ?? ''
  })
  await tokenField.fill(jwtToken)
  await analyze.click()
  await page.getByRole('heading', { level: 1, name: 'Podgląd eUsługi' }).waitFor({ timeout: 20_000 })
  check(`${label}: dobry token daje wynik`, header === `Bearer ${jwtToken}`)
  await page.unroute('**/api/forms')

  check(`${label}: brak błędów JavaScript na stronie`, errors.length === 0, errors.join(' | '))
  await context.close()
}

// F3b: panel JSON wybranego elementu, kontrola techniczna i oznaczenie danych przykładowych.
async function jsonPanelChecks(page, width) {
  const label = `json ${width}`
  const narrow = width < PAPER_BESIDE_FROM
  const content = page.locator('#json-tresc')
  if (narrow && !(await content.isVisible())) await page.getByRole('button', { name: 'JSON wybranego elementu' }).click()
  check(`${label}: kontrola techniczna bez błędów`, await page.getByText('Kontrola techniczna: 0 błędów').isVisible())
  check(`${label}: podgląd mówi, że dane są przykładowe`, await page.getByText('Dane z rejestru i słowniki w podglądzie są przykładowe.').isVisible())
  const element = async () => JSON.parse((await page.locator('#panel-json').textContent()) ?? 'null')
  const first = await element()
  check(`${label}: na starcie panel pokazuje pierwszą sekcję`, first?.field?.type === 'SECTION' && (await page.locator('[data-wybrany="true"]').count()) === 1, first?.field?.techName)
  check(`${label}: JSON jest podświetlony`, (await page.locator('#panel-json .json-klucz').count()) > 0)
  const showJson = page.getByRole('button', { name: 'Pokaż JSON' })
  await showJson.click()
  await page.getByRole('region', { name: 'Adres zamieszkania', exact: true }).getByRole('combobox').first().focus()
  check(`${label}: fokus w sekcji nie wyłącza „Pokaż JSON”`, (await showJson.getAttribute('aria-pressed')) === 'true')
  await page.getByRole('region', { name: 'Adres zamieszkania', exact: true }).getByRole('heading').click()
  check(`${label}: klik w sekcję wraca do JSON-u elementu`, (await showJson.getAttribute('aria-pressed')) === 'false')
  await page.getByRole('region', { name: 'Twoje dane' }).click()
  check(`${label}: klik w sekcję pokazuje jej JSON`, (await element())?.field?.techName === 'twoje_dane')
  check(`${label}: opis mówi, który to element`, ((await page.locator('.inspektor-co').textContent()) ?? '').includes('„Twoje dane”'))
  await page.getByRole('region', { name: 'Adres zamieszkania', exact: true }).getByRole('combobox').first().focus()
  check(`${label}: fokus z klawiatury też wybiera sekcję`, (await element())?.field?.techName === 'adres_zamieszkania')
  await page.screenshot({ path: join(shots, `f3-05-json-elementu-${width}.png`), fullPage: true })
  // Fokus z klawiatury: Tab z ostatniego przycisku podglądu prowadzi do kodu JSON.
  await page.getByRole('button', { name: 'Dalej' }).focus()
  await page.keyboard.press('Tab')
  // Na telefonie między nimi stoi przełącznik zwiniętego panelu.
  if (narrow) await page.keyboard.press('Tab')
  const panelRing = await page.evaluate(() => {
    const active = document.activeElement
    return active?.id === 'panel-json' ? getComputedStyle(active).outlineStyle : `fokus na ${active?.tagName}`
  })
  check(`${label}: kod JSON jest osiągalny z klawiatury i ma obrys`, panelRing === 'solid', panelRing)
}

// Odpowiedź dla pól oznaczonych jako błędne, według typu pola i podpowiedzi formatu.
async function fillInvalid(page) {
  const ids = await page.locator('.eu [aria-invalid="true"]').evaluateAll((elements) => elements.map((element) => element.id))
  const groups = new Set()
  for (const id of ids) {
    const field = page.locator(`[id="${id}"]`)
    const info = await field.evaluate((element) => ({
      tag: element.tagName,
      type: element.getAttribute('type') ?? '',
      name: element.getAttribute('name') ?? '',
      inputMode: element.inputMode,
      hint: element.closest('.eu-field')?.querySelector('[id$="-format"]')?.textContent ?? '',
    }))
    if (info.type === 'radio') {
      if (groups.has(info.name)) continue
      groups.add(info.name)
      await field.check()
    } else if (info.type === 'checkbox') await field.check()
    else if (info.tag === 'SELECT') await field.selectOption({ index: 1 })
    else if (info.type === 'file') await field.setInputFiles({ name: 'zalacznik.pdf', mimeType: 'application/pdf', buffer: samplePdf() })
    else if (info.type === 'date') await field.fill('2026-01-15')
    else if (info.type === 'email') await field.fill('anna@example.com')
    else if (info.tag === 'TEXTAREA') await field.fill('Przykładowy opis.')
    else {
      const value = info.hint.includes('11 cyfr')
        ? '85071201244'
        : info.hint.includes('10 cyfr')
          ? '1234563218'
          : info.hint.includes('9 albo 14')
            ? '123456785'
            : info.hint.includes('00-000')
              ? '00-950'
              : info.hint.includes('3 litery')
                ? 'ABA300000'
                : info.inputMode === 'decimal'
                  ? '12'
                  : 'Przykład'
      await field.fill(value)
    }
  }
  return ids.length
}

// „Dalej” aż do następnej strony. Błędy walidacji poprawia fillInvalid, najwyżej trzy razy.
async function nextPage(page) {
  const title = page.locator('.eu-page')
  const before = await title.textContent()
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.getByRole('button', { name: 'Dalej' }).click()
    await page.waitForFunction(
      (old) => document.querySelector('.eu-summary') || document.querySelector('.eu-page')?.textContent !== old,
      before,
    )
    if ((await title.textContent()) !== before) return true
    if ((await fillInvalid(page)) === 0) return false
  }
  return false
}

// Wynik z dowolnego JSON-a: każda strona do końca, z poprawnymi odpowiedziami na wymagane pola.
async function walkToFinish(page, form, label, from = 1) {
  for (let step = from; step < form.tabs.length; step++) {
    if (!(await nextPage(page))) {
      check(`${label}: przejście do kroku ${step + 1}`, false, (await page.locator('.eu-summary').textContent()) ?? '')
      return false
    }
  }
  const last = `Krok ${form.tabs.length} z ${form.tabs.length}`
  check(`${label}: wszystkie ${form.tabs.length} strony do strony końcowej`, await page.getByText(last, { exact: true }).isVisible())
  check(`${label}: strona końcowa nie ma „Dalej”`, (await page.getByRole('button', { name: 'Dalej' }).count()) === 0)
  return true
}

// Formularz 9: jeden plik, jeden JSON, wiele stron i zależności między stronami.
async function form9Checks(page, width) {
  const label = `p9 ${width}`
  const region = (name) => page.getByRole('region', { name, exact: true })
  const visible = async (name) => (await region(name).count()) > 0
  const form = JSON.parse(bodiesFor(page).at(-1) ?? 'null')
  check(`${label}: jedna odpowiedź API dla jednego pliku`, bodiesFor(page).length === 1, String(bodiesFor(page).length))

  check(`${label}: bez wyboru nie ma sekcji pełnomocnictwa`, !(await visible('Pełnomocnictwo')))
  await page.getByRole('radio', { name: 'Pełnomocnik' }).check()
  await region('Pełnomocnictwo').waitFor()
  check(`${label}: „Pełnomocnik” pokazuje pełnomocnictwo i opłatę`, (await visible('Pełnomocnictwo')) && (await visible('Opłata skarbowa za pełnomocnictwo')))
  check(`${label}: „Reprezentant” zostaje ukryty`, !(await visible('Potwierdzenie, że jesteś reprezentantem')))
  if (!(await nextPage(page))) return check(`${label}: przejście na stronę „Kandydat”`, false)

  check(`${label}: dyscypliny ukryte przed wyborem wniosku`, !(await visible('Dyscypliny sportowe kandydata')))
  await page.getByRole('radio', { name: 'Stypendium' }).check()
  await region('Dyscypliny sportowe kandydata').waitFor()
  check(`${label}: „Stypendium” pokazuje dyscypliny`, await visible('Dyscypliny sportowe kandydata'))
  await page.getByRole('radio', { name: 'Wyróżnienie' }).check()
  await region('Dyscypliny sportowe kandydata').waitFor({ state: 'detached' })
  check(`${label}: „Wyróżnienie” chowa dyscypliny`, !(await visible('Dyscypliny sportowe kandydata')))
  await shot9(page, width, '06-kandydat')
  if (!(await nextPage(page))) return check(`${label}: przejście na stronę „Osiągnięcia”`, false)

  check(`${label}: wybór ze strony 2 steruje stroną 3`, (await visible('Podopieczni trenera')) && !(await visible('Osiągnięcia sportowca')))
  check(`${label}: przed wyborem liczby jest tylko podopieczny 1`, (await visible('Dane podopiecznego 1')) && !(await visible('Dane podopiecznego 2')))
  await page.getByRole('radio', { name: '2', exact: true }).check()
  await region('Dane podopiecznego 2').waitFor()
  check(`${label}: „2” pokazuje drugiego podopiecznego, ale nie trzeciego`, (await visible('Dane podopiecznego 2')) && !(await visible('Dane podopiecznego 3')))
  await page.getByRole('group', { name: /^Czy podopieczny 2 jest pełnoletni/ }).getByRole('radio', { name: 'Nie' }).check()
  await shot9(page, width, '07-osiagniecia')
  if (!(await nextPage(page))) return check(`${label}: przejście na stronę „Zgody”`, false)

  check(`${label}: zgody idą za wyborem „Wyróżnienie”`, (await visible('Zgoda trenera')) && !(await visible('Zgoda pełnoletniego kandydata do stypendium')))
  check(
    `${label}: niepełnoletni podopieczny 2 daje zgodę opiekuna, a nie własną`,
    (await visible('Zgoda opiekuna podopiecznego 2')) && !(await visible('Zgoda pełnoletniego podopiecznego 2')),
  )
  check(
    `${label}: przy liczbie 2 nie ma zgód podopiecznego 3`,
    !(await visible('Zgoda opiekuna podopiecznego 3')) && !(await visible('Zgoda pełnoletniego podopiecznego 3')),
  )
  await page.getByRole('button', { name: 'Wstecz' }).click()
  await page.getByRole('heading', { level: 3, name: 'Osiągnięcia' }).waitFor()
  check(`${label}: „Wstecz” zachowuje wybór liczby podopiecznych`, await page.getByRole('radio', { name: '2', exact: true }).isChecked())
  if (!(await walkToFinish(page, form, label, 3))) return
  const review = (await page.locator('.eu-review').textContent()) ?? ''
  check(`${label}: przegląd pokazuje wybory z wielu stron`, review.includes('Pełnomocnik') && review.includes('Wyróżnienie'))
  await shot9(page, width, '08-strona-koncowa')
}

const responseBodies = new WeakMap()
function bodiesFor(page) {
  return responseBodies.get(page) ?? []
}
function recordBodies(page) {
  const bodies = []
  responseBodies.set(page, bodies)
  page.on('response', async (response) => {
    if (response.url().endsWith('/api/forms') && response.ok()) bodies.push(await response.text())
  })
}

async function shot9(page, width, name) {
  await page.screenshot({ path: join(shots, `p9-${name}-${width}.png`), fullPage: true })
  const result = await new AxeBuilder({ page }).withTags(axeTags).analyze()
  const found = result.violations.map((violation) => `${violation.id} (${violation.nodes[0].target.join(' ')})`)
  check(`p9 ${width}: axe ${name}`, found.length === 0, found.join(', '))
}

// Dowolny poprawny JSON COI: wzorce z folderów 1 i 5 oraz zapisane wyniki API (np. Eden AI).
// Przeglądarka dostaje plik jako odpowiedź API, więc podgląd nie wie, skąd przyszedł.
async function anyJsonChecks(browser, files) {
  for (const path of files) {
    const name = basename(path)
    const label = `JSON ${name}`
    const raw = await readFile(path, 'utf-8')
    const form = JSON.parse(raw)
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'pl-PL' })
    const page = await context.newPage()
    const errors = watch(page)
    await page.route('**/api/forms', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: raw }))
    await page.goto(web)
    await page.getByLabel('Plik formularza').setInputFiles({ name: 'wniosek.pdf', mimeType: 'application/pdf', buffer: samplePdf() })
    await page.getByRole('button', { name: 'Analizuj formularz' }).click()
    await page.getByRole('heading', { level: 1, name: 'Podgląd eUsługi' }).waitFor({ timeout: 20_000 })
    check(`${label}: tytuł z pliku`, await page.getByRole('heading', { level: 2, name: form.title, exact: true }).isVisible(), form.title)
    const problems = await page.locator('.kontrola').textContent()
    check(`${label}: kontrola techniczna bez błędów`, problems?.includes('0 błędów') ?? false, problems ?? '')
    await walkToFinish(page, form, label)
    check(`${label}: brak błędów JavaScript`, errors.length === 0, errors.join(' | '))
    await context.close()
  }
  if (files.length > 0) await brokenJsonCheck(browser, files.at(-1))
  const f9 = files.find((path) => basename(path) === 'F9.coi.json')
  if (f9) for (const [width, height] of viewports) await realValidatorChecks(browser, f9, { width, height })
  const nadplata = files.find((path) => path.includes('NadpłatyPodatku'))
  if (nadplata) await registryHintCheck(browser, nadplata)
}

async function openJson(browser, path, viewport) {
  const raw = await readFile(path, 'utf-8')
  const context = await browser.newContext({ viewport, locale: 'pl-PL' })
  const page = await context.newPage()
  const errors = watch(page)
  await page.route('**/api/forms', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: raw }))
  await page.goto(web)
  await page.getByLabel('Plik formularza').setInputFiles({ name: 'wniosek.pdf', mimeType: 'application/pdf', buffer: samplePdf() })
  await page.getByRole('button', { name: 'Analizuj formularz' }).click()
  await page.getByRole('heading', { level: 1, name: 'Podgląd eUsługi' }).waitFor({ timeout: 20_000 })
  return { context, page, errors, form: JSON.parse(raw) }
}

// Wynik API dla formularza 9: walidatory dowodu i ePUAP w przeglądarce, za dwoma warunkami SHOW.
async function realValidatorChecks(browser, path, viewport) {
  const label = `F9 z API ${viewport.width}`
  const { context, page, errors } = await openJson(browser, path, viewport)
  const hint = page.locator('.eu-field', { hasText: 'Imię' }).first().locator('.eu-hint')
  check(`${label}: imię z konta oznaczone jako przykładowe i zablokowane`, ((await hint.textContent()) ?? '').includes('Przykładowe dane z Twojego konta. Nie możesz ich zmienić.'))
  if (!(await nextPage(page))) {
    check(`${label}: przejście na stronę wniosku`, false)
    return context.close()
  }
  const club = page.getByRole('region', { name: 'Dane wnioskodawcy (Klub sportowy)' })
  check(`${label}: sekcja klubu ukryta przed wyborem`, (await club.count()) === 0)
  await page.getByRole('radio', { name: 'Wnioskodawca – Klub sportowy' }).check()
  await club.waitFor()
  await page.getByRole('checkbox', { name: 'Wypełnij dane pełnomocnika' }).check()
  await page.getByRole('checkbox', { name: 'Wypełnij dane klubu' }).check()
  await page.getByRole('radio', { name: 'Skrzynka ePUAP' }).check()
  const card = page.getByLabel('Seria i numer dowodu osobistego pełnomocnika')
  const epuap = page.getByLabel('Adres skrzynki ePUAP')
  await card.fill('ABA300001')
  await epuap.fill('skrytka')
  await page.getByRole('button', { name: 'Dalej' }).click()
  await page.locator('.eu-summary').waitFor()
  const summary = (await page.locator('.eu-summary').textContent()) ?? ''
  check(`${label}: podsumowanie zgłasza błędny numer dowodu`, summary.includes('Sprawdź numer dowodu osobistego, bo jeden znak jest błędny'))
  check(`${label}: podsumowanie zgłasza zły adres ePUAP`, summary.includes('Wpisz adres skrzynki ePUAP w formacie /identyfikator/skrytka'))
  check(`${label}: oba pola mają aria-invalid`, (await card.getAttribute('aria-invalid')) === 'true' && (await epuap.getAttribute('aria-invalid')) === 'true')
  await page.screenshot({ path: join(shots, `f3-06-walidatory-api-${viewport.width}.png`), fullPage: true })
  const axe = await new AxeBuilder({ page }).withTags(axeTags).analyze()
  check(`${label}: axe z błędami walidacji`, axe.violations.length === 0, axe.violations.map((violation) => violation.id).join(', '))
  await card.fill('ABA300000')
  await epuap.fill('/rdos-wroclaw/skrytka')
  await page.getByRole('radio', { name: 'eDoręczenia' }).check()
  check(`${label}: „eDoręczenia” chowa pole ePUAP`, (await epuap.count()) === 0)
  await page.getByRole('button', { name: 'Dalej' }).click()
  await page.locator('.eu-summary').waitFor()
  const after = (await page.locator('.eu-summary').textContent()) ?? ''
  check(`${label}: poprawione pola znikają z podsumowania`, !after.includes('dowodu osobistego') && !after.includes('ePUAP'))
  check(`${label}: brak błędów JavaScript`, errors.length === 0, errors.join(' | '))
  await context.close()
}

// Wzorzec COI z folderu 5 ma PESEL.name, PESEL.surname i PESEL.pesel tylko do odczytu.
async function registryHintCheck(browser, path) {
  const label = 'wzorzec 5'
  const { context, page } = await openJson(browser, path, { width: 1440, height: 900 })
  const pesel = page.getByLabel('Numer PESEL')
  const hint = page.locator('.eu-field', { has: pesel }).locator('.eu-hint')
  check(`${label}: PESEL z rejestru ma przykładową wartość`, (await pesel.inputValue()) === '85071201244', await pesel.inputValue())
  check(`${label}: podpowiedź podaje rejestr PESEL i blokadę`, ((await hint.textContent()) ?? '').includes('Przykładowe dane z rejestru PESEL. Nie możesz ich zmienić.'))
  const street = page.locator('.eu-field', { has: page.getByLabel(/^Ulica/) }).first().locator('.eu-hint')
  check(`${label}: ulica z konta jest do zmiany`, ((await street.textContent()) ?? '').includes('Przykładowe dane z Twojego konta. Możesz je zmienić.'))
  await context.close()
}

// Plik bez `id` w jednym polu: podgląd działa na kopii, ale znak kontroli mówi o pliku z API,
// a panel JSON pokazuje element z pliku, nie z kopii.
async function brokenJsonCheck(browser, path) {
  const label = `JSON bez id (${basename(path)})`
  const form = JSON.parse(await readFile(path, 'utf-8'))
  const section = form.tabs[0].questions[0].field
  delete section.repeatingSectionGrid[0].field.id
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'pl-PL' })
  const page = await context.newPage()
  const errors = watch(page)
  await page.route('**/api/forms', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(form) }))
  await page.goto(web)
  await page.getByLabel('Plik formularza').setInputFiles({ name: 'wniosek.pdf', mimeType: 'application/pdf', buffer: samplePdf() })
  await page.getByRole('button', { name: 'Analizuj formularz' }).click()
  await page.getByRole('heading', { level: 1, name: 'Podgląd eUsługi' }).waitFor({ timeout: 20_000 })
  const badge = (await page.locator('.kontrola').textContent()) ?? ''
  check(`${label}: kontrola mówi o braku w pliku`, badge.includes('1 błąd') && badge.includes('1 pole nie ma identyfikatora albo typu.'), badge)
  const shown = JSON.parse((await page.locator('#panel-json').textContent()) ?? 'null')
  check(`${label}: panel pokazuje sekcję z pliku, bez dopisanego id`, shown?.field?.techName === section.techName && !('id' in (shown?.field?.repeatingSectionGrid?.[0]?.field ?? {})))
  check(`${label}: brak błędów JavaScript`, errors.length === 0, errors.join(' | '))
  await context.close()
}

// Krótki przepływ na drugim pliku: wielostronicowy PDF pokazuje miniatury i przyklejony papier.
async function walkShort(browser, source, [width, height], prefix) {
  const label = `${prefix} ${width}`
  const context = await browser.newContext({ viewport: { width, height }, locale: 'pl-PL' })
  const page = await context.newPage()
  const errors = watch(page)
  const shot = shooter(prefix, width, label)
  recordBodies(page)
  await page.clock.install()
  await toResult(page, source, width, shot, label, secondApi)
  const form = await sameDocument(page, source, label)
  check(`${label}: formularz z folderu 9 ma inny tytuł niż atrapa folderu 5`, !form.title.includes('nadpłaty'), form.title)
  if (width >= PAPER_BESIDE_FROM) {
    const thumbnails = page.getByRole('group', { name: 'Strony oryginału' }).getByRole('button')
    if ((await thumbnails.count()) > 1) {
      await thumbnails.nth(1).click()
      await page.getByText(/^Strona 2 z \d+\.$/).waitFor()
      check(`${label}: miniatura przełącza stronę papieru`, (await thumbnails.nth(1).getAttribute('aria-pressed')) === 'true')
      await page.getByRole('button', { name: 'Dalej' }).scrollIntoViewIfNeeded()
      const top = await page.getByRole('region', { name: 'Oryginał' }).evaluate((element) => element.getBoundingClientRect().top)
      check(`${label}: papier zostaje w oknie przy przewijaniu`, top >= 0 && top < 40, String(Math.round(top)))
      await page.screenshot({ path: join(shots, `${prefix}-05-przewiniete-${width}.png`) })
    }
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await form9Checks(page, width)
  check(`${label}: brak błędów JavaScript na stronie`, errors.length === 0, errors.join(' | '))
  await context.close()
}

async function walk(browser, source, [width, height]) {
  const context = await browser.newContext({ viewport: { width, height }, acceptDownloads: true, locale: 'pl-PL' })
  const page = await context.newPage()
  const errors = watch(page)
  const shot = shooter('f1', width, String(width))

  const bodies = []
  page.on('response', async (response) => {
    if (response.url().endsWith('/api/forms') && response.ok()) bodies.push(await response.text())
  })
  // Zegar Playwrighta pozwala pokazać licznik po ponad minucie bez czekania minuty.
  await page.clock.install()
  await toResult(page, source, width, shot, String(width))
  await sameDocument(page, source, String(width))

  const showJson = page.getByRole('button', { name: 'Pokaż JSON' })
  await showJson.click()
  const jsonVisible = await page.getByText(/"techName":\s*"twoje_dane"/).first().isVisible()
  check(`${width}: „Pokaż JSON” pokazuje tekst JSON-a`, jsonVisible)
  check(`${width}: fokus idzie do panelu z JSON-em`, await page.evaluate(() => document.activeElement?.id === 'panel-json'))
  if (width >= PAPER_BESIDE_FROM) {
    const form = await page.locator('.rama').boundingBox()
    const panel = await page.locator('.inspektor').boundingBox()
    check(`${width}: JSON stoi obok formularza, nie nad nim`, panel.x >= form.x + form.width, `${Math.round(panel.x)} i ${Math.round(form.x + form.width)}`)
  }
  await shot(page, '05-json')

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Pobierz JSON' }).click(),
  ])
  const name = download.suggestedFilename()
  const downloaded = await readFile(await download.path(), 'utf-8')
  check(`${width}: pobrany plik to odpowiedź API bajt w bajt`, bodies.length > 0 && downloaded === bodies.at(-1), `${downloaded.length} i ${bodies.at(-1)?.length}`)
  const form = JSON.parse(downloaded)
  check(`${width}: „Pobierz JSON” daje plik .json`, name.endsWith('.json'), name)
  check(`${width}: pierwsza strona to „Dane”, ostatnia to FINISH`, form.tabs[0].title === 'Dane' && form.tabs.at(-1).type === 'FINISH')

  await showJson.click()
  check(`${width}: drugi klik wraca do JSON-u wybranego elementu`, (await showJson.getAttribute('aria-pressed')) === 'false')
  await jsonPanelChecks(page, width)
  await preview(page, width, (name) => shot(page, name, 'f2'))

  // Krok 8 z "Demo flow": nazwa .pdf, treść nie jest PDF-em.
  const fresh = await context.newPage()
  await fresh.goto(web)
  await fresh.getByLabel('Plik formularza').setInputFiles({
    name: 'wniosek.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('To nie jest PDF.'),
  })
  await fresh.getByRole('button', { name: 'Analizuj formularz' }).click()
  const alert = fresh.getByRole('alert')
  await alert.waitFor({ timeout: 20_000 })
  const message = (await alert.textContent()) ?? ''
  check(`${width}: zły typ pliku daje komunikat z API`, message.includes('nie pasuje do rozszerzenia'), message)
  const previewSettled = await fresh
    .getByText('Wczytuję pierwszą stronę pliku.')
    .waitFor({ state: 'hidden', timeout: 15_000 })
    .then(() => true, () => false)
  check(`${width}: podgląd pliku, który nie jest PDF-em, kończy się zdaniem`, previewSettled)
  await fresh.evaluate(() => document.fonts.ready)
  await shot(fresh, '06-blad')

  check(`${width}: brak błędów JavaScript na stronie`, errors.length === 0, errors.join(' | '))
  await context.close()
}

async function main() {
  for (const [url, label] of [
    [`${api}/health`, `port ${apiPort}`],
    [`${secondApi}/health`, `port ${apiPort + 1}`],
    [`${jwtApi}/health`, `port ${apiPort + 2}`],
    [web, `port ${webPort}`],
  ]) {
    if (await responds(url)) throw new Error(`${label} jest zajęty. Ustaw LOOK_API_PORT albo LOOK_WEB_PORT.`)
  }
  const fromFile = async (path) => ({ name: basename(path), mimeType: 'application/pdf', buffer: await readFile(path) })
  const real = process.argv[2] ? { main: process.argv[2], second: null } : await realPdfs()
  const source = real.main
    ? await fromFile(real.main)
    : { name: 'Wniosek o wydanie zaświadczenia.pdf', mimeType: 'application/pdf', buffer: samplePdf() }
  const second = real.second ? await fromFile(real.second) : null

  await mkdir(shots, { recursive: true })
  start(
    join(root, 'backend', '.venv', 'bin', 'python'),
    ['-m', 'uvicorn', 'app.main:app', '--app-dir', join(root, 'backend'), '--port', String(apiPort), '--log-level', 'warning'],
    { cwd: root, env: { ...process.env, LLM_FIXTURE: fixture } },
  )
  start(process.execPath, [join(frontend, 'node_modules', 'vite', 'bin', 'vite.js'), '--port', String(webPort), '--strictPort'], {
    cwd: frontend,
    env: { ...process.env, API_URL: api },
  })
  start(
    join(root, 'backend', '.venv', 'bin', 'python'),
    ['-m', 'uvicorn', 'app.main:app', '--app-dir', join(root, 'backend'), '--port', String(apiPort + 2), '--log-level', 'warning'],
    { cwd: root, env: { ...process.env, LLM_FIXTURE: fixture, JWT_ENABLED: 'true', JWT_SECRET: jwtSecret } },
  )
  jwtToken = execFileSync(join(root, 'backend', '.venv', 'bin', 'python'), ['-m', 'app.auth', 'token', '--hours', '1'], {
    cwd: join(root, 'backend'),
    env: { ...process.env, JWT_SECRET: jwtSecret },
    encoding: 'utf-8',
  }).trim()
  if (second) {
    start(
      join(root, 'backend', '.venv', 'bin', 'python'),
      ['-m', 'uvicorn', 'app.main:app', '--app-dir', join(root, 'backend'), '--port', String(apiPort + 1), '--log-level', 'warning'],
      { cwd: root, env: { ...process.env, LLM_FIXTURE: secondFixture } },
    )
    await waitFor(`${secondApi}/health`, 'drugie API')
  }
  await waitFor(`${api}/health`, 'API')
  await waitFor(`${jwtApi}/health`, 'API z tokenem')
  await waitFor(web, 'Vite')

  const browser = await chromium.launch()
  try {
    for (const viewport of viewports) await uploadChecks(browser, source, viewport)
    for (const viewport of viewports) await walk(browser, source, viewport)
    if (second) for (const viewport of viewports) await walkShort(browser, second, viewport, 'p9')
    const jsonFiles = await anyJsonFiles()
    await anyJsonChecks(browser, jsonFiles)
    console.log(`dowolny JSON: ${jsonFiles.length} plików (${jsonFiles.map((path) => basename(path)).join(', ')})`)
  } finally {
    await browser.close()
  }
  console.log('mapa zależności: ekranu jeszcze nie ma (etap 4), bez zrzutu')
  console.log(real.main ? `papier: ${source.name}${second ? ` i ${second.name}` : ''}` : 'papier: plik generowany w skrypcie, bo nie ma materialy/')
  console.log(`zrzuty: ${shots}/f1-*.png, f2-*.png${second ? ' i p9-*.png' : ''}`)
}

process.on('exit', stopAll)
// Zdarzenie exit nie przychodzi po sygnale, a osierocone serwery blokowałyby porty następnego biegu.
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => process.exit(130))
main()
  .then(() => {
    stopAll()
    console.log(failures.length ? `LOOK: FAIL (${failures.length})` : 'LOOK: PASS')
    process.exit(failures.length ? 1 : 0)
  })
  .catch((error) => {
    stopAll()
    console.error(`LOOK: FAIL (${error.message})`)
    process.exit(1)
  })
