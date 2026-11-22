import type { ReactNode } from 'react'
import { DICTIONARIES } from '../data/demo.ts'
import type { CoiField } from '../types.ts'
import type { Answer } from './answers.ts'
import { fieldDomId } from './ids.ts'
import { RichText } from './RichText.tsx'
import { isRichTextEmpty } from './richText.ts'
import { isRequired, validatorNames } from './validators.ts'

interface Props {
  field: CoiField
  answer: Answer | undefined
  error: string | undefined
  onChange: (answer: Answer) => void
}

const FORMAT_HINTS: Record<string, string> = {
  PESEL: '11 cyfr',
  NIP: '10 cyfr',
  REGON: '9 albo 14 cyfr',
  ZIP_CODE: 'Format: 00-000',
}

// Dane z rejestru mówią, czym jest pole, więc przeglądarka może je podpowiedzieć.
const AUTOCOMPLETE: Record<string, string> = {
  'MLPZ.name': 'given-name',
  'MLPZ.surname': 'family-name',
  'MLPZ.postCode': 'postal-code',
  'MLPZ.phoneNumber': 'tel',
  'MLPZ.email': 'email',
}

function hintFor(field: CoiField): string | null {
  if (field.readOnly) {
    return field.defaultValueType === 'EXTERNAL_SYSTEM' ? 'Dane z rejestru. Nie możesz ich zmienić.' : 'Tego pola nie możesz zmienić.'
  }
  const names = validatorNames(field)
  const format = Object.keys(FORMAT_HINTS).find((name) => names.includes(name))
  return format ? FORMAT_HINTS[format] : null
}

function inputProps(field: CoiField) {
  const names = validatorNames(field)
  const source = typeof field.defaultValue === 'string' ? field.defaultValue : ''
  const email = names.includes('EMAIL') || source === 'MLPZ.email'
  const digitsOnly = names.includes('PESEL') || names.includes('NIP') || names.includes('REGON')
  return {
    type: email ? 'email' : source === 'MLPZ.phoneNumber' ? 'tel' : 'text',
    inputMode: field.type === 'NUMBER' ? ('decimal' as const) : digitsOnly ? ('numeric' as const) : undefined,
    autoComplete: AUTOCOMPLETE[source] ?? 'off',
  }
}

function Optional({ field }: { field: CoiField }) {
  if (field.readOnly || isRequired(field)) return null
  return <span className="eu-optional"> (opcjonalnie)</span>
}

export function Field({ field, answer, error, onChange }: Props) {
  const id = fieldDomId(field)
  const text = typeof answer === 'string' ? answer : ''
  const list = Array.isArray(answer) ? answer : []

  if (field.type === 'TEXT_BLOCK' || field.type === 'INFO_SECTION') {
    return (
      <div className="eu-text">
        {field.title && <p className="eu-text-title">{field.title}</p>}
        <RichText html={field.description} />
      </div>
    )
  }

  const hint = hintFor(field)
  const hasDescription = !isRichTextEmpty(field.description)
  const describedBy =
    [hasDescription && `${id}-opis`, (hint || field.tooltipMessage) && `${id}-format`, error && `${id}-blad`]
      .filter(Boolean)
      .join(' ') || undefined
  const invalid = error ? true : undefined
  const notes = (
    <>
      {hasDescription && (
        <div className="eu-hint" id={`${id}-opis`}>
          <RichText html={field.description} />
        </div>
      )}
      {(hint || field.tooltipMessage) && (
        <p className="eu-hint" id={`${id}-format`}>
          {[field.tooltipMessage, hint].filter(Boolean).join(' ')}
        </p>
      )}
      {error && (
        <p className="eu-error" id={`${id}-blad`}>
          <span className="eu-sr">Błąd: </span>
          {error}
        </p>
      )}
    </>
  )
  const wrap = (body: ReactNode) => (
    <div className="eu-field" data-invalid={invalid}>
      {body}
    </div>
  )

  if (field.type === 'CONSENT_SECTION') {
    const consents = field.consentSectionConfig?.consents ?? []
    const toggle = (index: string) => onChange(list.includes(index) ? list.filter((item) => item !== index) : [...list, index])
    const boxes = consents.map((consent, i) => {
      const checked = list.includes(String(i))
      // Błąd dotyczy tylko wymaganej zgody bez zaznaczenia, nie całej grupy.
      const missing = Boolean(error) && Boolean(consent.required) && !checked
      return (
        <label className="eu-choice" key={i}>
          <input
            id={`${id}-${i}`}
            type="checkbox"
            checked={checked}
            disabled={field.readOnly}
            aria-invalid={missing ? true : undefined}
            aria-describedby={missing ? `${id}-blad` : undefined}
            onChange={() => toggle(String(i))}
          />
          <span>
            <RichText html={consent.description} inline />
            {!consent.required && <span className="eu-optional"> (opcjonalnie)</span>}
          </span>
        </label>
      )
    })
    return wrap(
      field.title ? (
        <fieldset>
          <legend>{field.title}</legend>
          {notes}
          {boxes}
        </fieldset>
      ) : (
        <>
          {notes}
          {boxes}
        </>
      ),
    )
  }

  if (field.type === 'RADIO' || field.type === 'CHECKBOX') {
    const radio = field.type === 'RADIO'
    const pick = (name: string) => {
      if (radio) onChange(name)
      else onChange(list.includes(name) ? list.filter((item) => item !== name) : [...list, name])
    }
    return wrap(
      <fieldset aria-describedby={describedBy}>
        <legend>
          {field.title}
          <Optional field={field} />
        </legend>
        {notes}
        {field.options.map((option, i) => (
          <label className="eu-choice" key={option.id}>
            <input
              id={`${id}-${i}`}
              type={radio ? 'radio' : 'checkbox'}
              name={id}
              checked={radio ? text === option.name : list.includes(option.name)}
              disabled={field.readOnly}
              aria-invalid={invalid}
              onChange={() => pick(option.name)}
            />
            <span>{option.name}</span>
          </label>
        ))}
      </fieldset>,
    )
  }

  const label = (
    <label htmlFor={id} id={`${id}-etykieta`}>
      {field.title}
      <Optional field={field} />
    </label>
  )
  const shared = { id, 'aria-describedby': describedBy, 'aria-invalid': invalid }

  // Wyłączona lista wyboru znika z kolejności Tab i wygląda jak edytowalna. Wartość tylko do
  // odczytu pokazuje więc zwykłe pole tekstowe niżej.
  if (field.type === 'SELECT' && !field.readOnly) {
    const names = field.dictionaryName ? (DICTIONARIES[field.dictionaryName] ?? []) : field.options.map((option) => option.name)
    const value = list[0] ?? ''
    return wrap(
      <>
        {label}
        {notes}
        <select {...shared} value={value} onChange={(event) => onChange(event.target.value ? [event.target.value] : [])}>
          <option value="">Wybierz</option>
          {names.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </>,
    )
  }

  if (field.type === 'FILE_UPLOADER') {
    return wrap(
      <>
        {label}
        {notes}
        {/* Natywna kontrolka pliku mówi językiem przeglądarki, nie strony. Stąd przezroczysty input
            na całej strefie: klik i klawiatura działają natywnie, a tekst jest nasz. */}
        <div className="eu-upload">
          {/* Nazwa zawiera widoczny napis przycisku, żeby zadziałało też sterowanie głosem. */}
          <input
            {...shared}
            aria-labelledby={`${id}-etykieta ${id}-przycisk`}
            aria-describedby={[describedBy, `${id}-plik`].filter(Boolean).join(' ')}
            type="file"
            title=""
            disabled={field.readOnly}
            onChange={(event) => onChange(event.target.files?.[0]?.name ?? '')}
          />
          <span className="eu-upload-button" id={`${id}-przycisk`} aria-hidden="true">
            {text ? 'Zmień plik' : 'Wybierz plik'}
          </span>
          <span className="eu-upload-state" id={`${id}-plik`}>
            {text ? `Dodany plik: ${text}` : 'Nie dodano pliku'}
          </span>
        </div>
      </>,
    )
  }

  if (field.type === 'TEXTAREA') {
    return wrap(
      <>
        {label}
        {notes}
        <textarea {...shared} rows={5} value={text} readOnly={field.readOnly} onChange={(event) => onChange(event.target.value)} />
      </>,
    )
  }

  if (field.type === 'DATEPICKER') {
    return wrap(
      <>
        {label}
        {notes}
        <input {...shared} type="date" value={text} readOnly={field.readOnly} onChange={(event) => onChange(event.target.value)} />
      </>,
    )
  }

  return wrap(
    <>
      {label}
      {notes}
      <input {...shared} {...inputProps(field)} value={field.type === 'SELECT' ? list.join(', ') : text} readOnly={field.readOnly} onChange={(event) => onChange(event.target.value)} />
    </>,
  )
}
