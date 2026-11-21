import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

// Kroki 1-8 z "Demo flow" w SPEC.md. Tresc wniosku daje fixture modelu (LLM_FIXTURE),
// wiec plik musi tylko przejsc kontrole typu i odczyt tekstu. PDF powstaje tutaj, bo
// materialy COI leza poza gitem.
function pdfWithText(text: string): Buffer {
  const stream = `BT /F1 12 Tf 72 760 Td (${text}) Tj ET`;
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

test('urzednik zamienia plik wniosku w podglad eUslugi i JSON', async ({ page, browser, baseURL }) => {
  // 1-3
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Wczytaj formularz' })).toBeVisible();
  await page.getByLabel('Plik formularza').setInputFiles({
    name: 'Wniosek o wydanie zaświadczenia.pdf',
    mimeType: 'application/pdf',
    buffer: pdfWithText('WNIOSEK O WYDANIE ZASWIADCZENIA'),
  });
  await page.getByRole('button', { name: 'Analizuj formularz' }).click();

  // 4: dane inicjalne z rejestru sa wpisane i zablokowane
  await expect(page.getByRole('heading', { name: 'Podgląd eUsługi' })).toBeVisible({ timeout: 15_000 });
  const pesel = page.getByRole('region', { name: 'Twoje dane' }).getByLabel('Numer PESEL');
  await expect(pesel).toHaveValue(/^\d{11}$/);
  await expect(pesel).not.toBeEditable();

  // 5: warunek SHOW
  const otherPerson = page.getByRole('region', { name: 'Dane innej osoby' });
  const otherAddress = page.getByRole('region', { name: 'Adres zamieszkania innej osoby' });
  await expect(otherPerson).toBeHidden();
  await page.getByRole('radio', { name: 'Innej osoby' }).check();
  await expect(otherPerson).toBeVisible();
  await expect(otherAddress).toBeVisible();

  // 6: walidator ZIP_CODE
  await otherAddress.getByLabel('Kod pocztowy').fill('12345');
  await page.getByRole('button', { name: 'Dalej' }).click();
  await expect(otherAddress.getByText('Wpisz kod pocztowy w formacie 00-000')).toBeVisible();

  // 7
  await page.getByRole('button', { name: 'Pokaż JSON' }).click();
  await expect(page.getByText(/"techName":\s*"twoje_dane"/).first()).toBeVisible();
  const downloadControl = page
    .getByRole('button', { name: 'Pobierz JSON' })
    .or(page.getByRole('link', { name: 'Pobierz JSON' }));
  const [download] = await Promise.all([page.waitForEvent('download'), downloadControl.click()]);
  expect(download.suggestedFilename()).toMatch(/\.json$/);
  const form = JSON.parse(await readFile(await download.path(), 'utf-8'));
  expect(form.tabs[0].title).toBe('Dane');
  expect(form.tabs.at(-1).type).toBe('FINISH');

  // 8: nowa karta, bo ekran wczytania jest pewny tylko przed pierwszym wynikiem
  const fresh = await browser.newPage({ baseURL });
  await fresh.goto('/');
  await fresh.getByLabel('Plik formularza').setInputFiles({
    name: 'wniosek.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('To nie jest PDF.'),
  });
  await fresh.getByRole('button', { name: 'Analizuj formularz' }).click();
  await expect(fresh.getByRole('alert')).toContainText('nie pasuje do rozszerzenia');
  await fresh.close();
});
