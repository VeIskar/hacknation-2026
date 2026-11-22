import { Preview } from '../preview/Preview.tsx'
import type { CoiForm } from '../types.ts'

/** Środek ekranu wyniku: tytuł wniosku i eUsługa na własnej kartce. */
export function ResultPanel({ form }: { form: CoiForm }) {
  return (
    <>
      <h2 className="tytul-wniosku">{form.title}</h2>
      <div className="rama">
        <Preview form={form} />
      </div>
    </>
  )
}
