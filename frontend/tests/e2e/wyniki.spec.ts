import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

// REPLAY: odpowiedź POST /api/forms to zapisany wynik z wyniki/ (bajt w bajt).
// Bez modelu, bez dokumentów źródłowych. Test mierzy przetwarzanie zapisanych plików,
// nie skuteczność nowych wywołań modelu.
const FORMS = ['F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9'];

function minimalPdf(): Buffer {
  const stream = 'BT /F1 12 Tf 72 760 Td (WNIOSEK) Tj ET';
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = '%PDF-1.4\n';
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(pdf.length);
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  pdf += offsets.map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`).join('');
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf, 'latin1');
}

for (const name of FORMS) {
  test(`${name}: zapisany wynik COI w podglądzie i pobraniu (REPLAY)`, async ({ page }) => {
    const raw = await readFile(fileURLToPath(new URL(`../../../wyniki/${name}.coi.json`, import.meta.url)));
    const form = JSON.parse(raw.toString('utf-8')) as { tabs: { title: string }[] };
    const pageErrors: Error[] = [];
    page.on('pageerror', (error) => pageErrors.push(error));
    await page.route('**/api/forms', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: raw }),
    );

    await page.goto('/');
    await page.getByLabel('Plik formularza').setInputFiles({
      name: `${name}.pdf`,
      mimeType: 'application/pdf',
      buffer: minimalPdf(),
    });
    await page.getByRole('button', { name: 'Analizuj formularz' }).click();

    // Formularz i liczba stron z JSON-a
    await expect(page.getByRole('heading', { name: 'Podgląd eUsługi' })).toBeVisible({ timeout: 15_000 });
    const total = form.tabs.length;
    await expect(page.getByText(`Krok 1 z ${total}`)).toBeVisible();
    await expect(page.getByRole('heading', { level: 3, name: form.tabs[0].title, exact: true })).toBeVisible();

    // Nawigacja: "Dalej" przechodzi dalej albo pokazuje błędy walidacji tej strony.
    await page.getByRole('button', { name: 'Dalej' }).click();
    const advanced = page.getByText(`Krok 2 z ${total}`);
    const blocked = page.locator('.eu-summary');
    await expect(advanced.or(blocked)).toBeVisible();
    if (await advanced.isVisible()) {
      await page.getByRole('button', { name: 'Wstecz' }).click();
      await expect(page.getByText(`Krok 1 z ${total}`)).toBeVisible();
    }

    // Pobrany JSON jest identyczny z zapisanym wynikiem
    await page.getByRole('button', { name: 'Pokaż JSON' }).click();
    const downloadControl = page
      .getByRole('button', { name: 'Pobierz JSON' })
      .or(page.getByRole('link', { name: 'Pobierz JSON' }));
    const [download] = await Promise.all([page.waitForEvent('download'), downloadControl.click()]);
    expect((await readFile(await download.path())).equals(raw)).toBe(true);

    // Warunki SHOW i walidatory liczone w przeglądarce nie rzuciły wyjątku
    expect(pageErrors.map(String)).toEqual([]);
  });
}
