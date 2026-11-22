import { describe, expect, it } from 'vitest'
import { structureProblems, technicalProblems } from '../check.ts'
import { DEMO_ID_CARD } from '../data/demo.ts'
import { formStats } from '../format.ts'
import type { CoiField, CoiForm } from '../types.ts'
import { fieldsOf, initialAnswers } from './answers.ts'
import type { Answers } from './answers.ts'
import { hiddenIds } from './conditions.ts'
import { initialData } from './initialData.ts'
import { normalizeForm } from './normalize.ts'
import { KNOWN_VALIDATORS, pageErrors, validateField, validatorNames } from './validators.ts'

// Wzorce COI z folderów 1 i 5 (materialy/, poza gitem, D5) i zapisane wyniki prawdziwego API
// (Eden AI, ../generated-forms-final/F2–F9, poza repozytorium). Vite czyta je przy uruchomieniu;
// bez nich glob jest pusty i test pomijany. Testy nie wołają API ani modelu.
const references = import.meta.glob('../../../materialy/[15]. */*.json', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>
const apiResults = import.meta.glob('../../../../generated-forms-final/F*.coi.json', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>
const files = { ...references, ...apiResults }
const paths = Object.keys(files)

function allFields(form: CoiForm): CoiField[] {
  return form.tabs.flatMap(fieldsOf)
}

describe.skipIf(paths.length === 0)('wzorce COI i wyniki API w podglądzie', () => {
  it.each(paths)('%s: kontrola techniczna, walidatory, dane inicjalne i warunki', async (path: string) => {
    const raw = JSON.parse(files[path]) as CoiForm
    const form = normalizeForm(raw)
    expect([...structureProblems(raw), ...technicalProblems(form)]).toEqual([])
    const stats = formStats(form)
    expect(stats.pages).toBeGreaterThanOrEqual(2)
    expect(stats.fields).toBeGreaterThan(0)

    const fields = allFields(form)
    for (const field of fields) {
      for (const name of validatorNames(field)) expect(KNOWN_VALIDATORS, `${field.techName}: ${name}`).toContain(name)
      const initial = initialData(field)
      // Każde pole z danymi inicjalnymi dostaje przykładową wartość albo świadomy brak danych.
      if (initial) expect(initial.known, `${field.techName}: ${initial.key}`).toBe(true)
    }

    const answers = initialAnswers(form)
    const hidden = await hiddenIds(form, answers)
    for (const tab of form.tabs) {
      expect(tab.questions.some(({ field }) => !hidden.has(field.id)), tab.title).toBe(true)
      expect(() => pageErrors(tab, answers, hidden)).not.toThrow()
    }
  })
})

// Formularz 9 z prawdziwego API: jeden plik, jeden JSON, warunki na dwóch poziomach.
const f9Path = Object.keys(apiResults).find((path) => path.endsWith('/F9.coi.json'))

describe.skipIf(!f9Path)('formularz 9 z API: warunki SHOW i walidatory', () => {
  const form = f9Path ? normalizeForm(JSON.parse(apiResults[f9Path]) as CoiForm) : ({ tabs: [], flow: { links: [] }, title: '' } as unknown as CoiForm)
  const byTech = new Map<string, CoiField>()
  for (const tab of form.tabs) {
    for (const { field } of tab.questions) {
      byTech.set(field.techName, field)
      for (const cell of field.repeatingSectionGrid) byTech.set(cell.field.techName, cell.field)
    }
  }
  const field = (techName: string) => {
    const found = byTech.get(techName)
    if (!found) throw new Error(`brak pola ${techName}`)
    return found
  }
  const shown = async (answers: Answers, ...techNames: string[]) => {
    const hidden = await hiddenIds(form, answers)
    return techNames.map((techName) => !hidden.has(field(techName).id))
  }
  const start = () => ({ ...initialAnswers(form) }) as Record<string, Answers[string]>

  it('ma 4 strony, ostatnia to strona końcowa, i jest technicznie poprawny', () => {
    expect(form.tabs.map((tab) => tab.type)).toEqual(['MAIN', 'MAIN', 'MAIN', 'FINISH'])
    expect(technicalProblems(form)).toEqual([])
  })

  it('„W czyim imieniu” przełącza sekcje innej osoby i podmiotu', async () => {
    const answers = start()
    expect(await shown(answers, 'dane_innej_osoby', 'dane_podmiotu')).toEqual([false, false])
    answers[field('wybierz_w_czyim_imieniu_wnioskujesz').id] = 'Innej osoby'
    expect(await shown(answers, 'dane_innej_osoby', 'dane_podmiotu')).toEqual([true, false])
    answers[field('wybierz_w_czyim_imieniu_wnioskujesz').id] = 'Osoby prawnej lub jednostki organizacyjnej'
    expect(await shown(answers, 'dane_innej_osoby', 'dane_podmiotu', 'adres_siedziby')).toEqual([false, true, true])
  })

  it('rodzaj wnioskodawcy, zaznaczenie i wybór sterują polem dowodu i skrzynki ePUAP', async () => {
    const answers = start()
    expect(await shown(answers, 'dane_wnioskodawcy_klub_sportowy')).toEqual([false])
    answers[field('rodzaj_wnioskodawcy').id] = 'Wnioskodawca – Klub sportowy'
    expect(await shown(answers, 'dane_wnioskodawcy_klub_sportowy', 'seria_i_numer_dowodu_osobistego_pelnomocnika')).toEqual([true, false])
    answers[field('dane_pelnomocnika_klubu_sportowego').id] = ['Wypełnij dane pełnomocnika']
    expect(await shown(answers, 'seria_i_numer_dowodu_osobistego_pelnomocnika')).toEqual([true])

    answers[field('dane_klubu_sportowego').id] = ['Wypełnij dane klubu']
    const way = field('korespondencja_z_urzedem_wybierz_preferowany_sposob').id
    answers[way] = 'Skrzynka ePUAP'
    expect(await shown(answers, 'adres_skrzynki_epuap', 'adres_skrzynki_edoreczenia')).toEqual([true, false])
    answers[way] = 'eDoręczenia'
    expect(await shown(answers, 'adres_skrzynki_epuap', 'adres_skrzynki_edoreczenia')).toEqual([false, true])
    // Bez klubu cała sekcja znika razem z polami, które od niej zależą.
    answers[field('rodzaj_wnioskodawcy').id] = 'Wnioskodawca – Prezydent Miasta Zgierza'
    expect(await shown(answers, 'dane_wnioskodawcy_klub_sportowy', 'adres_skrzynki_edoreczenia')).toEqual([false, false])
  })

  it('walidatory dowodu i ePUAP działają na polach z API', () => {
    const card = field('seria_i_numer_dowodu_osobistego_pelnomocnika')
    expect(validatorNames(card)).toEqual(['REQUIRED', 'SERIAL_NUMBER_ID_CARD'])
    expect(validateField(card, '')).toBe('Uzupełnij pole „Seria i numer dowodu osobistego pełnomocnika”')
    expect(validateField(card, 'AB300000')).toBe('Wpisz 3 litery i 6 cyfr numeru dowodu osobistego')
    expect(validateField(card, 'ABA300001')).toBe('Sprawdź numer dowodu osobistego, bo jeden znak jest błędny')
    expect(validateField(card, DEMO_ID_CARD.toLowerCase())).toBeNull()

    const epuap = field('adres_skrzynki_epuap')
    expect(validatorNames(epuap)).toEqual(['EPUAP'])
    expect(validateField(epuap, '')).toBeNull()
    expect(validateField(epuap, 'skrytka')).toBe('Wpisz adres skrzynki ePUAP w formacie /identyfikator/skrytka')
    expect(validateField(epuap, '/rdos-wroclaw/skrytka')).toBeNull()

    // API nie dało tu ADE (etykieta „eDoręczenia” bez łącznika). Front nie dopisuje walidatora.
    expect(validatorNames(field('adres_skrzynki_edoreczenia'))).toEqual([])
  })

  it('rodzaj wniosku pokazuje dane wyróżnienia, a „Inna dyscyplina” pole na nazwę', async () => {
    const answers = start()
    expect(await shown(answers, 'dane_wyroznienia_sportowego', 'nazwa_innej_dyscypliny')).toEqual([false, false])
    answers[field('rodzaj_wniosku').id] = 'Wniosek o przyznanie wyróżnienia sportowego'
    answers[field('konkretna_dyscyplina_sportowa').id] = ['Inna dyscyplina']
    expect(await shown(answers, 'dane_wyroznienia_sportowego', 'nazwa_innej_dyscypliny')).toEqual([true, true])
    answers[field('rodzaj_wniosku').id] = 'Wniosek o przyznanie stypendium sportowego'
    expect(await shown(answers, 'dane_wyroznienia_sportowego')).toEqual([false])
  })

  it('pola z danymi inicjalnymi: imię i nazwisko zablokowane, z przykładową wartością', () => {
    const initial = allFields(form).filter((item) => initialData(item))
    expect(initial.map((item) => [item.defaultValue, item.readOnly])).toEqual([
      ['MLPZ.name', true],
      ['MLPZ.surname', true],
    ])
    const answers = initialAnswers(form)
    expect(initial.map((item) => answers[item.id])).toEqual(['Anna', 'Przykładowa'])
  })
})
