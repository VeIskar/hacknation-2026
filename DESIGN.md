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

- Workbench (the official's tool: loading, waiting, source view, dependency map, report) may
  have a signature look: its own typeface, a paper and ink palette, motion. Still: contrast
  4.5:1, visible focus outline, prefers-reduced-motion, no decorative gradients, no glass,
  no glow, no emoji.
- eUsługa preview (what a citizen sees) follows "Forms" above and the COI standards strictly.
  The workbench frames it and never restyles it.
- Motion: allowed when it shows where something came from or where it went.
- Fonts: font files in the repo, no CDN. OFL-1.1 allowed for unmodified font files only,
  recorded in DECISIONS.md.

## Workbench depth (lead decision, 22.11; overrides "Look" for the workbench only)

- Three surfaces: desk (background), sheet (paper, eUsługa frame), panel (inspector).
  A sheet has one soft shadow, the same everywhere. No other shadows.
- Radius 8-12 px on panels and buttons. Paper sheets keep A4 proportions and square corners.
- One primary colour per zone: ink in the workbench, action blue inside the eUsługa preview.
