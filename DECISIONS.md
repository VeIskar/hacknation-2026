# DECISIONS

One line per choice: what, why, licence. Product dependencies: MIT, Apache or BSD only.

## Template (prepared before the event, 2026-11-20)

| What                          | Why                               | Licence    |
| ----------------------------- | --------------------------------- | ---------- |
| react, react-dom 19.3         | UI                                | MIT        |
| vite 8, @vitejs/plugin-react  | dev server and build              | MIT        |
| tailwindcss 4, @tailwindcss/vite | styling with tokens in index.css | MIT       |
| typescript 7                  | type check in the gate            | Apache-2.0 |
| oxlint                        | lint in the gate                  | MIT        |
| vitest 5                      | unit tests                        | MIT        |
| @playwright/test 1.65         | e2e tests, test-only              | Apache-2.0 |
| @axe-core/playwright 4.14     | accessibility checks, test-only   | MPL-2.0    |
| fastapi 0.165, uvicorn 0.54   | API                               | MIT, BSD   |
| pytest, httpx, ruff           | backend tests and lint, test-only | MIT, BSD   |

Three MPL-2.0 packages are installed, none of them modified and none of them our source:

| Package                          | Comes from                    | Role                         |
| -------------------------------- | ----------------------------- | ---------------------------- |
| @axe-core/playwright, axe-core   | direct, test-only             | accessibility checks in e2e  |
| lightningcss                     | vite 8 and @tailwindcss/vite  | CSS build tool, not shipped  |
| certifi                          | httpx (httpcore)              | CA certificate bundle        |

Every other installed frontend package is MIT, Apache-2.0, BSD, ISC, 0BSD or BlueOak. If the
task rules require every dependency to be MIT, Apache or BSD, ask a mentor before submission.
Do not add a fourth exception.

Claude Code version used: (write `claude --version` here on the day)

## Event: web

(frontend dependencies and choices go here)

## Event: api

(backend dependencies and choices go here)

## Event: whole project

(scope, contract and demo choices go here)
