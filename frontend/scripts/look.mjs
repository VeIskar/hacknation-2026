// Oczy: przechodzi przepływ na atrapie modelu i zapisuje zrzuty każdego stanu w 1440 i 390 px
// do frontend/shots/. Sprawdza też krok 8 (zły typ pliku), pobranie pliku JSON i podgląd eUsługi:
// dane z rejestru, warunek SHOW, błąd walidacji, przejście do strony końcowej.
//
// Użycie (z katalogu frontend/):
//   node scripts/look.mjs                      plik PDF generowany tutaj
//   node scripts/look.mjs /sciezka/wniosek.pdf prawdziwy plik, np. z materialy/ (poza gitem)
//
// Skrypt startuje własne API z LLM_FIXTURE i własny serwer Vite na osobnych portach, więc nie
// trafi w API bez atrapy ani w serwery innej sesji. Na końcu oba zatrzymuje.
import { AxeBuilder } from '@axe-core/playwright'
import { chromium } from '@playwright/test'
import { spawn } from 'node:child_process'
import { mkdir, readFile } from 'node:fs/promises'
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

async function walk(browser, source, [width, height]) {
  const context = await browser.newContext({ viewport: { width, height }, acceptDownloads: true, locale: 'pl-PL' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(String(error)))
  // Każdy stan dostaje zrzut i kontrolę axe z tymi samymi tagami co tests/e2e/a11y.spec.ts.
  const shot = async (target, name, prefix = 'f1') => {
    await target.screenshot({ path: join(shots, `${prefix}-${name}-${width}.png`), fullPage: true })
    const result = await new AxeBuilder({ page: target }).withTags(axeTags).analyze()
    const found = result.violations.map((violation) => `${violation.id} (${violation.nodes[0].target.join(' ')})`)
    check(`${width}: axe ${name}`, found.length === 0, found.join(', '))
  }

  // Zegar Playwrighta pozwala pokazać licznik po ponad minucie bez czekania minuty.
  await page.clock.install()
  await page.goto(web)
  await page.getByRole('heading', { level: 1, name: 'Wczytaj formularz' }).waitFor()
  await page.evaluate(() => document.fonts.ready)
  await shot(page, '01-pusty')

  await page.getByLabel('Plik formularza').setInputFiles(source)
  await page.locator('[data-ready="true"]').waitFor({ timeout: 20_000 })
  await shot(page, '02-plik-wybrany')

  // Oczekiwanie: atrapa odpowiada od razu, więc odpowiedź wstrzymujemy tutaj, nie w aplikacji.
  let release
  const held = new Promise((resolve) => {
    release = resolve
  })
  await page.route('**/api/forms', async (route) => {
    await held
    await route.continue()
  })
  await page.getByRole('button', { name: 'Analizuj formularz' }).click()
  await page.getByRole('heading', { level: 1, name: 'Analiza formularza' }).waitFor()
  await page.clock.fastForward(72_000)
  await shot(page, '03-oczekiwanie')
  release()

  await page.getByRole('heading', { level: 1, name: 'Podgląd eUsługi' }).waitFor({ timeout: 20_000 })
  await shot(page, '04-wynik')

  await page.getByRole('button', { name: 'Pokaż JSON' }).click()
  const jsonVisible = await page.getByText(/"techName":\s*"twoje_dane"/).first().isVisible()
  check(`${width}: „Pokaż JSON” pokazuje tekst JSON-a`, jsonVisible)
  await shot(page, '05-json')

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Pobierz JSON' }).click(),
  ])
  const name = download.suggestedFilename()
  const form = JSON.parse(await readFile(await download.path(), 'utf-8'))
  check(`${width}: „Pobierz JSON” daje plik .json`, name.endsWith('.json'), name)
  check(`${width}: pierwsza strona to „Dane”, ostatnia to FINISH`, form.tabs[0].title === 'Dane' && form.tabs.at(-1).type === 'FINISH')

  await page.getByRole('button', { name: 'Ukryj JSON' }).click()
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
    [web, `port ${webPort}`],
  ]) {
    if (await responds(url)) throw new Error(`${label} jest zajęty. Ustaw LOOK_API_PORT albo LOOK_WEB_PORT.`)
  }
  const sourcePath = process.argv[2]
  const source = sourcePath
    ? { name: basename(sourcePath), mimeType: 'application/pdf', buffer: await readFile(sourcePath) }
    : { name: 'Wniosek o wydanie zaświadczenia.pdf', mimeType: 'application/pdf', buffer: samplePdf() }

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
  await waitFor(`${api}/health`, 'API')
  await waitFor(web, 'Vite')

  const browser = await chromium.launch()
  try {
    for (const viewport of viewports) await walk(browser, source, viewport)
  } finally {
    await browser.close()
  }
  console.log('mapa zależności: ekranu jeszcze nie ma (etap 4), bez zrzutu')
  console.log(`zrzuty: ${shots}/f1-*.png i f2-*.png`)
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
