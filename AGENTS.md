# AGENTS.md (keep under 80 lines; every rule traces to a real failure)

## Mission
Read SPEC.md first. Build ONLY what SPEC.md lists under "Must".
Ship one working vertical slice before adding features.

## Layout (fixed names; the gate depends on them)
- frontend/  Vite + React + TS. Unit tests in frontend/src, e2e in frontend/tests/e2e.
- backend/   FastAPI in backend/app/main.py (GET /health returns 200).
             Tests in backend/tests. Virtualenv in backend/.venv.

## Commands (the only blessed ones)
- setup: (cd frontend && npm ci && npx playwright install chromium) &&
         python3 -m venv backend/.venv &&
         backend/.venv/bin/pip install -r backend/requirements.txt
- up:    docker compose up --build            (web :5173, api :8000)
- gate:  bash scripts/gate.sh                 (your area from .hn-area; without it, all)
         bash scripts/gate.sh all             (lint + tsc + vitest, ruff + pytest)
         bash scripts/gate.sh web|api [args]  (one side; args go to vitest or pytest)
- e2e:   cd frontend && npm run test:e2e      (Playwright + axe; starts web and api;
                                              writes screenshots to frontend/shots/)

## Definition of done (evidence, not claims)
Paste the last lines of gate.sh and test:e2e output in your final message.

## Hard rules
- Never run git commit. After a green gate, stop and print the message
  "step N: ...". The human commits and tags.
- Never edit frontend/tests/e2e/*.spec.ts to make a test pass. Ask the human.
  You may only ADD paths to frontend/tests/e2e/screens.ts, never remove one.
- Never disable lint rules, axe rules or TypeScript checks.
- No new dependency without one line in DECISIONS.md (why, license).
  Licenses: MIT, Apache or BSD only. Three MPL-2.0 exceptions are recorded in
  DECISIONS.md (axe, lightningcss, certifi). Do not remove them and do not add another.
- UI text in Polish, max 15 words per sentence, no jargon.
- Every interactive element: visible focus, accessible name, 44px target.
- No real personal data. Demo data is generated in frontend/src/data/demo.ts.
  PESEL, NIP and REGON in demo data must pass their checksum.
- The LLM is called only from backend/app/llm.py, configured by LLM_BASE_URL,
  LLM_MODEL and LLM_API_KEY. Tests never call it: they read
  backend/tests/fixtures/fields.json.
- Secrets only in .env files, never committed. The example file is env.example.

## Team (several people, one repository)
- A file .hn-area (never committed) holding `web` or `api` names your area. With it:
  edit only frontend/ (web) or backend/ (api), the gate checks only that side, and your
  progress file is PROGRESS.web.md or PROGRESS.api.md. Without it you are the lead:
  whole repository, PROGRESS.md.
- Need a change outside your area? Do not make it. Add one line under "Requests" in your
  progress file and tell the human.
- "API contract" and "Field contract" in SPEC.md change only when the humans agree. The
  lead edits SPEC.md, then both sides follow. Never bend one side to match the other.
- DECISIONS.md: add your line under the heading of your area.

## Workflow
1. Plan in plan mode. Write the plan into your progress file (max 10 lines).
2. Implement one step, run gate, stop, print the commit message.
3. Append one line to your progress file: done / next / blocker.
Stage procedures live in .claude/skills/hn-*/SKILL.md (spec, krok, napraw, recenzja, stan,
demo). Claude Code runs them as /hn-...; any other agent reads the file and follows it.

## Where to look
SPEC.md (scope, API and field contract) · DESIGN.md (look, form patterns; read before UI
work) · DECISIONS.md (choices, licenses) · PROGRESS*.md (state, plan, log, requests) ·
PITCH.md (demo story)

## Learned rules
(date + what went wrong; delete if not violated in 2 sessions)
