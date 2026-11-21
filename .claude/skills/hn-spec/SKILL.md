---
name: hn-spec
description: Stage 1. Interview the human one question at a time, then write a one-page SPEC.md and one failing acceptance test. Manual only.
disable-model-invocation: true
argument-hint: "[task text or path to the task file]"
---

# hn-spec: one-page specification

Input: the official task text (pasted, or a file path in the argument). If there is none, ask for it and stop.

1. Read the task text and the judging criteria. List the criteria with their weights in three lines.
2. Interview the human. One question per turn, each with your own best guess attached so they
   can answer "yes". At most 12 questions. Cover, in this order: who the single user is, the one
   flow the demo shows from first click to result, what counts as proof it works, what is
   explicitly out, which input files or data exist today, what is mocked.
3. Do not design screens or pick libraries during the interview. Do not write code.
4. Write SPEC.md by filling the headings that are already in the file. Hard limits: one page,
   at most 5 items under "Must", every "Must" item observable in the demo. Put everything else
   under "Later" or "Out". Fill "Field contract" only if the task has structured data.
   Fill "API contract" with every endpoint the demo flow needs, one example request and one
   example response each: frontend and backend are built in parallel against it, so an
   endpoint missing here blocks someone. Ask who owns each "Must" item and write the name
   next to it.
5. Write ONE acceptance test in frontend/tests/e2e/acceptance.spec.ts that walks the demo flow
   and fails today for the right reason. Run `cd frontend && npx playwright test
   tests/e2e/acceptance.spec.ts` and paste the failing lines.
6. Stop. Tell the human to review SPEC.md, then to lock the tests with the command from
   README.md ("Zatrzask na testy"). Do not start building.
