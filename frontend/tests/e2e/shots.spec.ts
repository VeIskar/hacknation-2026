import { test } from '@playwright/test';
import { screens } from './screens';

// Zrzut kazdego ekranu przy szerokosci telefonu. Agent otwiera PNG z frontend/shots/
// i ocenia wyglad, a nie sam kod. Katalog shots/ nie trafia do repo.
// Numer z listy ekranow jest w nazwie pliku, zeby "/" i "/start" sie nie nadpisywaly.
screens.forEach((path, index) => {
  test(`zrzut ${path}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    const slug = path.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'start';
    const name = `${String(index + 1).padStart(2, '0')}-${slug}`;
    await page.screenshot({ path: `shots/${name}.png`, fullPage: true });
  });
});
