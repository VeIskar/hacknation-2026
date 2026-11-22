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
  const card = Object.fromEntries(
    await page.locator('.karta > div').evaluateAll((rows) => rows.map((row) => [row.querySelector('dt').textContent, row.querySelector('dd').textContent])),
  )
  const shown = `${card.Strony} stron, ${card.Sekcje} sekcji, ${card.Pola} pól`
  const counted = `${form.tabs.length} stron, ${sections.length} sekcji, ${fields.length} pól`
  check(`${label}: karta liczy to samo co JSON`, shown === counted, `karta ${shown}, JSON ${counted}`)
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
    const toggle = page.getByRole('button', { name: 'Pokaż oryginał' })
    await toggle.waitFor()
    // Pytamy o całą treść papieru, nie o płótno: płótno jest niewidoczne także wtedy, gdy PDF jeszcze się rysuje.
    check(`${label}: wąski ekran zwija papier do przycisku`, !(await page.locator('#papier-tresc').isVisible()))
    await shot(page, '02-plik-wybrany')
    await toggle.click()
    await sheet.waitFor({ timeout: 20_000 })
    await shot(page, '02b-oryginal')
    await page.getByRole('button', { name: 'Ukryj oryginał' }).click()
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

// Krótki przepływ na drugim pliku: wielostronicowy PDF pokazuje miniatury i przyklejony papier.
async function walkShort(browser, source, [width, height], prefix) {
  const label = `${prefix} ${width}`
  const context = await browser.newContext({ viewport: { width, height }, locale: 'pl-PL' })
  const page = await context.newPage()
  const errors = watch(page)
  const shot = shooter(prefix, width, label)
  await page.clock.install()
  await toResult(page, source, width, shot, label, secondApi)
  const form = await sameDocument(page, source, label)
  check(`${label}: formularz z folderu 9 ma inny tytuł niż atrapa folderu 5`, !form.title.includes('nadpłaty'), form.title)
  if (width >= PAPER_BESIDE_FROM) {
    const thumbnails = page.getByRole('group', { name: 'Strony oryginału' }).getByRole('button')
    if ((await thumbnails.count()) > 1) {
      await thumbnails.nth(1).click()
      await page.getByText(/^Strona 2 z \d+$/).waitFor()
      check(`${label}: miniatura przełącza stronę papieru`, (await thumbnails.nth(1).getAttribute('aria-pressed')) === 'true')
      await page.getByRole('button', { name: 'Dalej' }).scrollIntoViewIfNeeded()
      const top = await page.getByRole('region', { name: 'Oryginał' }).evaluate((element) => element.getBoundingClientRect().top)
      check(`${label}: papier zostaje w oknie przy przewijaniu`, top >= 0 && top < 40, String(Math.round(top)))
      await page.screenshot({ path: join(shots, `${prefix}-05-przewiniete-${width}.png`) })
    }
  }
  check(`${label}: brak błędów JavaScript na stronie`, errors.length === 0, errors.join(' | '))
  await context.close()
}

async function walk(browser, source, [width, height]) {
  const context = await browser.newContext({ viewport: { width, height }, acceptDownloads: true, locale: 'pl-PL' })
  const page = await context.newPage()
  const errors = watch(page)
  const shot = shooter('f1', width, String(width))

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
  const form = JSON.parse(await readFile(await download.path(), 'utf-8'))
  check(`${width}: „Pobierz JSON” daje plik .json`, name.endsWith('.json'), name)
  check(`${width}: pierwsza strona to „Dane”, ostatnia to FINISH`, form.tabs[0].title === 'Dane' && form.tabs.at(-1).type === 'FINISH')

  await showJson.click()
  check(`${width}: drugi klik wraca do karty`, await page.getByRole('tab', { name: 'Karta' }).getAttribute('aria-selected') === 'true')
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
  if (second) {
    start(
      join(root, 'backend', '.venv', 'bin', 'python'),
      ['-m', 'uvicorn', 'app.main:app', '--app-dir', join(root, 'backend'), '--port', String(apiPort + 1), '--log-level', 'warning'],
      { cwd: root, env: { ...process.env, LLM_FIXTURE: secondFixture } },
    )
    await waitFor(`${secondApi}/health`, 'drugie API')
  }
  await waitFor(`${api}/health`, 'API')
  await waitFor(web, 'Vite')

  const browser = await chromium.launch()
  try {
    for (const viewport of viewports) await walk(browser, source, viewport)
    if (second) for (const viewport of viewports) await walkShort(browser, second, viewport, 'p9')
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
