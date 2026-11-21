---
name: hn-napraw
description: Stage 4. Fix one bug - reproduce it, confirm the cause, make the smallest change, add a regression test. Manual only.
disable-model-invocation: true
argument-hint: "<what is broken and how to see it>"
---

# hn-napraw: one bug

1. Reproduce first. Run the failing command or test and paste the failing lines. If you cannot
   reproduce it in two attempts, stop and say exactly what you ran.
2. Find the cause in the code and state it in one sentence with file:line. Do not stop at the
   first plausible guess: show the line that produces the wrong value.
3. Make the smallest change that removes the cause. No refactoring, no unrelated clean-up.
4. Add or extend one test that fails without the fix. Tests under frontend/tests/ are locked:
   put a new unit test next to the code (frontend/src or backend/tests), or ask the human.
5. Run `bash scripts/gate.sh` (and `npm run test:e2e` in frontend/ if the bug was visible).
   Paste the last lines.
6. If the bug revealed a rule worth keeping, add one dated line under "Learned rules" in
   AGENTS.md. Stop and print the commit message `fix: ...`. Never commit.
