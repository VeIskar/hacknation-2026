---
name: hn-demo
description: Stage 8. Freeze check before submission - gate, e2e, accessibility, a clean docker compose start, README and PITCH. No new features. Manual only.
disable-model-invocation: true
---

# hn-demo: freeze check

No new features and no redesign in this stage. Fix only what the checks below report.
Run this as the lead, on the integrated main branch, after everyone has pushed.

1. `bash scripts/gate.sh all` and `cd frontend && npm run test:e2e`. Paste the last lines.
2. Run the `a11y` subagent. Fix every violation it reports, then run it again.
3. Clean start: `docker compose down`, `docker compose up --build -d`, then
   `curl -s http://localhost:8000/health` and `curl -s -o /dev/null -w '%{http_code}'
   http://localhost:5173/`. Then `cd frontend && npm run test:e2e` against the containers, then
   `docker compose down`. Paste the results.
4. Review everything since the last demo tag: follow .claude/skills/hn-recenzja/SKILL.md with
   that tag as the argument. Fix only findings that break the demo flow or leak a secret;
   list the rest in README.md under "Ograniczenia".
5. README.md: how to run it (one command), what is real and what is mocked, licences of
   dependencies (from DECISIONS.md), and the section "Narzędzia przygotowane przed wydarzeniem".
6. Run the `pitch` subagent to write PITCH.md.
7. Print: the checklist with PASS or FAIL per line, and the commit message. Never commit.
