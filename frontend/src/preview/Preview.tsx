import { useEffect, useRef, useState } from 'react'
import type { FormEvent, MouseEvent } from 'react'
import { AlertIcon } from '../components/icons.tsx'
import type { CoiField, CoiForm, CoiTab } from '../types.ts'
import { initialAnswers, isEmptyAnswer, takesAnswer } from './answers.ts'
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
  for (const { field: section } of tab.questions) {
    for (const { field } of section.repeatingSectionGrid) if (field.id === fieldId) return field
  }
  return undefined
}

/**
 * eUsługa tak, jak zobaczy ją mieszkaniec. Strefa trzyma się DESIGN.md "Forms" i nie bierze
 * stylu warsztatu. Odpowiedzi żyją tutaj, więc przejście między stronami ich nie gubi.
 */
export function Preview({ form }: { form: CoiForm }) {
  const [answers, setAnswers] = useState<Answers>(() => initialAnswers(form))
  // null do pierwszego przeliczenia: pole z warunkiem SHOW nie może mignąć, zanim warunek się policzy.
  const [hidden, setHidden] = useState<ReadonlySet<string> | null>(null)
  const [page, setPage] = useState(0)
  const [errors, setErrors] = useState<FieldError[]>([])
  const headingRef = useRef<HTMLHeadingElement>(null)
  const summaryRef = useRef<HTMLDivElement>(null)
  const focusNext = useRef<'heading' | 'summary' | null>(null)

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

  if (!hidden) return null

  const tab = form.tabs[page]
  const last = page === form.tabs.length - 1
  const finish = tab.type === 'FINISH'
  const shownErrors = errors.filter((error) => !hidden.has(error.fieldId))
  const errorOf = (field: CoiField) => shownErrors.find((error) => error.fieldId === field.id)?.message

  function answer(field: CoiField, value: Answer) {
    setAnswers((current) => ({ ...current, [field.id]: value }))
  }

  function goTo(next: number) {
    setErrors([])
    setPage(next)
    focusNext.current = 'heading'
  }

  async function next(event: FormEvent) {
    event.preventDefault()
    // Warunki liczymy jeszcze raz z bieżących odpowiedzi: walidacja nie może oprzeć się
    // na widoczności sprzed ostatniej zmiany.
    const hiddenNow = await hiddenIds(form, answers)
    const found = pageErrors(tab, answers, hiddenNow)
    setHidden(hiddenNow)
    if (found.length > 0) {
      setErrors(found)
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

  return (
    <form className="eu" noValidate onSubmit={next} aria-label="eUsługa">
      <p className="eu-step" id="eu-krok">
        Krok {page + 1} z {form.tabs.length}
      </p>
      <h3 className="eu-page" ref={headingRef} tabIndex={-1} aria-describedby="eu-krok">
        {tab.title}
      </h3>

      {shownErrors.length > 0 && (
        // Fokus stoi na ramce, a ogłasza się jej wnętrze: z rolą i fokusem na jednym elemencie
        // czytnik ekranu przeczytałby podsumowanie dwa razy.
        <div className="eu-summary" ref={summaryRef} tabIndex={-1}>
          <div role="alert">
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
        const headingId = `eu-sekcja-${section.id}`
        return (
          <section key={section.id} className="eu-section" aria-labelledby={headingId}>
            <h4 id={headingId}>{section.title}</h4>
            {!isRichTextEmpty(section.description) && (
              <div className="eu-note">
                <RichText html={section.description} />
              </div>
            )}
            {section.repeatingSectionGrid.map(({ field }) =>
              hidden.has(field.id) ? null : (
                <Field key={field.id} field={field} answer={answers[field.id]} error={errorOf(field)} onChange={(value) => answer(field, value)} />
              ),
            )}
          </section>
        )
      })}

      {finish && (
        <div className="eu-review">
          {form.tabs.map((other, index) => {
            if (other.type === 'FINISH') return null
            const rows = other.questions
              .filter(({ field: section }) => !hidden.has(section.id))
              .flatMap(({ field: section }) => section.repeatingSectionGrid.map(({ field }) => field))
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
