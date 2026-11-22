# DESIGN (read before any UI work)

The product is a public-service tool. It must look calm and official, not like a template.
Judges reward simplicity and accessibility. Tokens live in frontend/src/index.css (`@theme`).

## Order of work

1. Grey screens with a working flow first. State and tests before colour.
2. Then typography and spacing. Then the one action colour. Nothing else.
3. Polish only what exists. No redesign in the last three hours.

## Look

- Flat backgrounds. One action colour (`action`), used only on the primary button and links.
- One layer. A border only around a separate object (a document, an application). No cards
  inside cards, no shadows, no gradients, no glass, no glow.
- Left-aligned content in one column, max width 40rem. Screen title at the top, the primary
  action at the bottom of the step.
- An icon only where it carries meaning. No emoji. No decorative illustration.
- One animation at most, where it means something. Respect `prefers-reduced-motion`.
- Real names of documents, offices and benefits. No filler text.
- Text contrast at least 4.5:1, measured. Body text 18 px, line height 1.5.

## Forms (the core of the product)

- One topic per step. Show "Krok 2 z 5" as text, not only as a bar.
- A visible `<label>` above every field. Never a placeholder instead of a label.
- Hint text under the label, linked with `aria-describedby`. Say the format: "11 cyfr".
- Group radios and checkboxes in `<fieldset>` with a `<legend>`.
- Validate on submit of the step, not on every key. On error: an error summary at the top with
  links to the fields, focus moved to the summary, the message repeated next to the field,
  `aria-invalid="true"` on the field. Messages say how to fix it: "Wpisz 11 cyfr numeru PESEL".
- Mark optional fields with "(opcjonalnie)". Do not use a red asterisk alone.
- Use the right `type`, `inputmode` and `autocomplete` (e.g. `inputmode="numeric"` for PESEL).
- Every interactive element: at least 44 by 44 px, a visible focus ring (never remove the
  `:focus-visible` rule), an accessible name. The ring is an outline: no `outline-none` or
  `outline-hidden`, and a shadow alone does not count. The e2e test checks this.
- Every screen has one visible `<h1>` that names it. The e2e test checks this too.
- A review step before sending: every answer with a "Zmień" link back to its step.
- Never lose what the user typed: keep the draft in state and restore it after reload.

## Text

- Polish, at most 15 words per sentence, no jargon, no English.
- Buttons say what happens: "Dalej", "Wyślij wniosek", not "OK" or "Submit".

## Limits

- No national emblem, no mObywatel logo, no imitation of an official service's look.

## Two zones (lead decision, 21.11)

- Workbench (the official's tool: loading, waiting, source view, JSON, report) follows
  "Visual direction: Jasny urząd" below.
- eUsługa preview (what a citizen sees) follows "Forms" above and the COI standards strictly.
  The workbench frames it and never restyles it.
- Motion: allowed when it shows where something came from or where it went.
- Fonts: font files in the repo, no CDN. OFL-1.1 allowed for unmodified font files only,
  recorded in DECISIONS.md.

## Visual direction: Jasny urząd (lead decision, 22.11; overrides "Look" for the workbench)

- White page. Light grey #F3F5F8 only for areas with a job: the file drop zone, the waiting
  panel, the JSON panel header.
- Navy #10284F for the service bar, headings, the current step and the selected element.
  Primary actions #0052A5 everywhere, in the workbench and in the eUsługa preview.
- Yellow only marks a paper source: pale fill #FFF4C7 with a 2 px #D9A900 underline, number
  tabs #FFE38A. Never on buttons, steps or focus.
- Radius 4 px for controls and tags, 6 px for panels. Paper sheets keep square corners.
- Shadows: the paper sheet, and a 2 px bottom shadow on the primary button. Nothing else.
- No eyebrow above headings, no coloured bar down one side of a box, monospace only for JSON.
- Motion only when it shows where something came from or where it went: under 300 ms,
  ease-out, off under prefers-reduced-motion.
- Reference screens: frontend/design/jasny-urzad/ (outside git).
