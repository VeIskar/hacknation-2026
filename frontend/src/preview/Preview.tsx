import { useEffect, useRef, useState } from 'react'
import type { FocusEvent, FormEvent, MouseEvent } from 'react'
import { AlertIcon } from '../components/icons.tsx'
import type { SourceMatch } from '../sourceMatches.ts'
import type { CoiField, CoiForm, CoiTab } from '../types.ts'
import { fieldsOf, initialAnswers, isEmptyAnswer, isSection, takesAnswer } from './answers.ts'
import type { Answer, Answers } from './answers.ts'
import { hiddenIds } from './conditions.ts'
import { Field } from './Field.tsx'
import { fieldFocusId } from './ids.ts'
import { RichText } from './RichText.tsx'
import { isRichTextEmpty } from './richText.ts'
import { pageErrors } from './validators.ts'
import type { FieldError } from './validators.ts'

function shownAnswer(field: CoiField, answer: Answer | undefined): string {
  if (isEmptyAnswer(answer)) return 'Brak odpowiedzi'
  if (field.type === 'CONSENT_SECTION') return 'Zaznaczono'
  return typeof answer === 'string' ? answer : (answer ?? []).join(', ')
}

function findField(tab: CoiTab, fieldId: string): CoiField | undefined {
  return fieldsOf(tab).find((field) => field.id === fieldId)
}

function firstShown(tab: CoiTab, hidden: ReadonlySet<string>): string | null {
  return tab.questions.find(({ field }) => !hidden.has(field.id))?.field.id ?? null
}

/** Skąd wybór: klik, fokus z klawiatury albo nowa strona. */
export type SelectHow = 'klik' | 'fokus' | 'strona' | 'zrodlo'

interface Props {
  /** Formularz po `normalizeForm`: wszystkie klucze są na miejscu. */
  form: CoiForm
  /** `id` pola lub sekcji, której JSON pokazuje panel obok. */
  selectedId?: string | null
  onSelect?: (id: string | null, how: SelectHow) => void
  sources?: ReadonlyMap<string, SourceMatch>
  focusSource?: SourceMatch | null
  page: number
  onPage: (page: number) => void
  onHidden: (hidden: ReadonlySet<string>) => void
}

function sourceTargetId(id: string) {
  return `podglad-${id}`
}

function SourceMarker({ source, selected, onSelect }: { source: SourceMatch; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      className="zrodlo-znacznik"
      data-preview-link={source.id}
      aria-label={`Pokaż źródło ${source.number}, strona ${source.page}.`}
      aria-description={source.title}
      aria-pressed={selected}
      onClick={(event) => {
        event.stopPropagation()
        onSelect()
      }}
    >
      {source.number}
    </button>
  )
}

/**
 * eUsługa tak, jak zobaczy ją mieszkaniec. Strefa trzyma się DESIGN.md "Forms" i nie bierze
 * stylu warsztatu. Odpowiedzi żyją tutaj, więc przejście między stronami ich nie gubi.
 */
export function Preview({ form, selectedId = null, onSelect, sources, focusSource, page, onPage, onHidden }: Props) {
  const [answers, setAnswers] = useState<Answers>(() => initialAnswers(form))
  // null do pierwszego przeliczenia: pole z warunkiem SHOW nie może mignąć, zanim warunek się policzy.
  const [hidden, setHidden] = useState<ReadonlySet<string> | null>(null)
  const [errors, setErrors] = useState<{ page: number; list: FieldError[] } | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const summaryRef = useRef<HTMLDivElement>(null)
  const focusNext = useRef<'heading' | 'summary' | null>(null)
  const focusedSource = useRef<SourceMatch | null>(null)

  useEffect(() => {
    let stale = false
    void hiddenIds(form, answers).then((next) => {
      if (!stale) setHidden(next)
    })
    return () => {
      stale = true
    }
  }, [form, answers])

  // Po zmianie strony czytnik ekranu ma usłyszeć jej tytuł, a po błędach podsumowanie.
  useEffect(() => {
    const target = focusNext.current
    focusNext.current = null
    if (target === 'heading') headingRef.current?.focus()
    if (target === 'summary') summaryRef.current?.focus()
  })

  useEffect(() => {
    if (hidden) onHidden(hidden)
  }, [hidden, onHidden])

  useEffect(() => {
    if (!hidden || !focusSource || focusedSource.current === focusSource) return
    const { id, parentId, tabIndex } = focusSource
    if (page !== tabIndex) return
    focusedSource.current = focusSource
    if (hidden.has(id) || (parentId && hidden.has(parentId))) {
      return
    }
    const field = findField(form.tabs[page], id)
    const control = field && document.getElementById(fieldFocusId(field, answers[id]))
    const target = control && !control.matches(':disabled') ? control : document.getElementById(sourceTargetId(id))
    target?.focus()
  }, [answers, focusSource, form, hidden, page])

  if (!hidden) return null

  const tab = form.tabs[page]
  const last = page === form.tabs.length - 1
  const finish = tab.type === 'FINISH'
  const shownErrors = errors?.page === page ? errors.list.filter((error) => !hidden.has(error.fieldId)) : []
  const errorOf = (field: CoiField) => shownErrors.find((error) => error.fieldId === field.id)?.message

  function answer(field: CoiField, value: Answer) {
    setAnswers((current) => ({ ...current, [field.id]: value }))
  }

  function goTo(next: number) {
    setErrors(null)
    onPage(next)
    focusNext.current = 'heading'
    onSelect?.(firstShown(form.tabs[next], hidden ?? new Set()), 'strona')
  }

  async function next(event: FormEvent) {
    event.preventDefault()
    // Warunki liczymy jeszcze raz z bieżących odpowiedzi: walidacja nie może oprzeć się
    // na widoczności sprzed ostatniej zmiany.
    const hiddenNow = await hiddenIds(form, answers)
    const found = pageErrors(tab, answers, hiddenNow)
    setHidden(hiddenNow)
    if (found.length > 0) {
      setErrors({ page, list: found })
      focusNext.current = 'summary'
    } else if (!last) {
      goTo(page + 1)
    }
  }

  function jumpTo(event: MouseEvent, error: FieldError) {
    event.preventDefault()
    const field = findField(tab, error.fieldId)
    if (field) document.getElementById(fieldFocusId(field, answers[field.id]))?.focus()
  }

  function selectionProps(field: CoiField) {
    return {
      id: sourceTargetId(field.id),
      tabIndex: -1,
      'data-wybrany': selectedId === field.id ? true : undefined,
      onClick: (event: MouseEvent) => {
        event.stopPropagation()
        onSelect?.(field.id, 'klik')
      },
      onFocus: (event: FocusEvent) => {
        event.stopPropagation()
        onSelect?.(field.id, 'fokus')
      },
    }
  }

  function marker(field: CoiField) {
    const source = sources?.get(field.id)
    return source && <SourceMarker source={source} selected={selectedId === field.id} onSelect={() => onSelect?.(field.id, 'zrodlo')} />
  }

  function renderField(field: CoiField, loose = false) {
    const source = marker(field)
    const className = loose ? 'eu-section eu-luzne' : 'eu-element'
    return (
      <div key={field.id} className={className} {...selectionProps(field)} role={takesAnswer(field) ? undefined : 'group'} aria-label={takesAnswer(field) ? undefined : field.title || undefined}>
        <div className={source ? 'zrodlo-wiersz' : undefined}>
          {source}
          <Field field={field} answer={answers[field.id]} error={errorOf(field)} onChange={(value) => answer(field, value)} />
        </div>
      </div>
    )
  }

  return (
    <form className="eu" noValidate onSubmit={next} aria-label="eUsługa">
      <div className="eu-head">
        <p className="eu-step" id="eu-krok">
          Krok {page + 1} z {form.tabs.length}
        </p>
        {/* Pasek tylko powtarza tekst wyżej, więc czytnik ekranu go pomija. */}
        <div className="eu-bar" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${form.tabs.length}, minmax(0, 1fr))` }}>
          {form.tabs.map((other, index) => (
            <span key={other.id} data-done={index <= page} />
          ))}
        </div>
      </div>
      <h3 className="eu-page" ref={headingRef} tabIndex={-1} aria-describedby="eu-krok">
        {tab.title}
      </h3>

      {shownErrors.length > 0 && (
        // Fokus przechodzi na ramkę, więc czytnik ekranu przeczyta ją sam. Rola alert dałaby
        // drugie ogłoszenie tej samej treści.
        <div className="eu-summary" ref={summaryRef} tabIndex={-1}>
          <div>
            <h4>
              <AlertIcon size={22} />
              Popraw błędy na tej stronie
            </h4>
            <ul>
            {shownErrors.map((error) => {
              const field = findField(tab, error.fieldId)
              return (
                <li key={error.fieldId}>
                  <a href={field ? `#${fieldFocusId(field, answers[field.id])}` : undefined} onClick={(event) => jumpTo(event, error)}>
                    {error.message}
                  </a>
                  <span className="eu-summary-where"> Sekcja: {error.sectionTitle}</span>
                </li>
              )
            })}
            </ul>
          </div>
        </div>
      )}

      {tab.questions.map(({ field: section }) => {
        if (hidden.has(section.id)) return null
        if (!isSection(section)) return renderField(section, true)
        const headingId = `eu-sekcja-${section.id}`
        const source = marker(section)
        return (
          <section key={section.id} className="eu-section" aria-labelledby={headingId} {...selectionProps(section)}>
            <div className={source ? 'zrodlo-wiersz' : undefined}>
              {source}
              <h4 id={headingId}>{section.title}</h4>
            </div>
            {section.type === 'REPEATING_SECTION' && (
              <p className="eu-note">W eUsłudze tę sekcję można dodać kilka razy. Podgląd pokazuje jedną.</p>
            )}
            {!isRichTextEmpty(section.description) && (
              <div className="eu-note">
                <RichText html={section.description} />
              </div>
            )}
            {section.repeatingSectionGrid.map(({ field }) => hidden.has(field.id) ? null : renderField(field))}
          </section>
        )
      })}

      {finish && (
        <div className="eu-review">
          {form.tabs.map((other, index) => {
            if (other.type === 'FINISH') return null
            const rows = other.questions
              .filter(({ field: section }) => !hidden.has(section.id))
              .flatMap(({ field: section }) => (isSection(section) ? section.repeatingSectionGrid.map(({ field }) => field) : [section]))
              .filter((field) => takesAnswer(field) && !hidden.has(field.id))
            return (
              <div key={other.id} className="eu-review-page">
                <h4>{other.title}</h4>
                <dl>
                  {rows.map((field) => (
                    <div key={field.id}>
                      <dt>{field.title || 'Zgoda'}</dt>
                      <dd>{shownAnswer(field, answers[field.id])}</dd>
                    </div>
                  ))}
                </dl>
                <button type="button" className="eu-link" onClick={() => goTo(index)}>
                  Zmień<span className="eu-sr"> odpowiedzi na stronie „{other.title}”</span>
                </button>
              </div>
            )
          })}
          <p className="eu-note">To koniec podglądu. Wniosku nie można stąd wysłać.</p>
        </div>
      )}

      <div className="eu-nav">
        {page > 0 && (
          <button type="button" className="eu-button eu-button-second" onClick={() => goTo(page - 1)}>
            Wstecz
          </button>
        )}
        {!last && (
          <button type="submit" className="eu-button">
            Dalej
          </button>
        )}
      </div>
    </form>
  )
}
