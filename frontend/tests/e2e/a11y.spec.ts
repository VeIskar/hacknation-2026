import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { screens } from './screens';

for (const path of screens) {
  test(`a11y ${path}`, async ({ page }) => {
    await page.goto(path);
    // Pusta albo wysypana strona nie ma czego naruszyc i przeszlaby wszystkie testy ponizej.
    await expect(page.locator('h1').first(), 'ekran ma widoczny naglowek h1').toBeVisible();
    // Tagi axe nie sa kumulatywne. Bez wcag21a i wcag21aa wypadaja reguly z WCAG 2.1,
    // miedzy innymi autocomplete-valid, wazna dla formularzy.
    const result = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(result.violations).toEqual([]);
  });

  // Sama klawiatura: Tab dochodzi do elementow, kazdy ma widoczny obrys fokusu,
  // a fokus nie utyka ani nie krazy w petli.
  test(`klawiatura ${path}`, async ({ page }) => {
    await page.goto(path);
    const tabbable = await page
      .locator('a[href], button:not([disabled]), input:not([disabled]), select, textarea')
      .count();
    const sinceWrap = new Set<string>();
    let reached = 0;
    for (let i = 0; i < tabbable + 2; i++) {
      await page.keyboard.press('Tab');
      const info = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        const cs = getComputedStyle(el);
        // Wskaznikiem fokusu jest obrys (DESIGN.md). Cien sie nie liczy: Tailwind ustawia
        // box-shadow takze bez fokusu, a w trybie wysokiego kontrastu cien znika.
        const transparent = /^transparent$|^rgba\(.*,\s*0\)$|\/\s*0\)$/.test(
          cs.outlineColor.trim(),
        );
        const ring =
          cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2 && !transparent;
        if (!el.dataset.kbd) {
          el.dataset.kbd = String(document.querySelectorAll('[data-kbd]').length + 1);
        }
        return { id: el.dataset.kbd, ring, tag: el.tagName };
      });
      // Fokus wyszedl poza strone: to koniec okrazenia, nie pulapka. Bez tego ekran
      // z jednym przyciskiem dawal falszywy blad, bo po okrazeniu wraca ten sam element.
      if (!info) {
        sinceWrap.clear();
        continue;
      }
      expect(info.ring, `widoczny obrys fokusu na <${info.tag}>`).toBe(true);
      expect(
        sinceWrap.has(info.id),
        'fokus utknal: Tab wraca do tego samego elementu, zanim wyjdzie ze strony',
      ).toBe(false);
      sinceWrap.add(info.id);
      reached++;
    }
    if (tabbable > 0) expect(reached).toBeGreaterThan(0);
  });
}
