---
name: hn-krok
description: Stage 3. Build exactly one step from SPEC.md under the gate, then stop with a commit message for the human. Manual only.
disable-model-invocation: true
argument-hint: "[optional: which Must item or step]"
---

# hn-krok: one step, gate, stop

Your progress file is PROGRESS.md, or PROGRESS.web.md / PROGRESS.api.md when the file
.hn-area exists (see "Team" in AGENTS.md). With .hn-area you touch only your own directory.

1. Read SPEC.md and the last 15 lines of your progress file. Pick the step named in the
   argument, or the first "Must" item you own that the progress file does not mark as done.
   Say which one in one line.
2. Plan first: at most 10 lines, appended to your progress file under "Plan". Name the files
   you will touch and the test that will prove the step. If the step needs a new dependency,
   add its line to DECISIONS.md (why, licence) before installing.
3. Implement the step and its tests. Build against the "API contract" and "Field contract" in
   SPEC.md exactly as written: when the other side is not ready, frontend uses the contract's
   example response as a fixture and backend tests post the contract's example request. If
   the contract is wrong or incomplete, stop and say so; do not change it yourself.
   A new screen gets its path added to frontend/tests/e2e/screens.ts in the same step.
4. Run `bash scripts/gate.sh`. If the step changed anything visible, also run
   `cd frontend && npm run test:e2e` and open the PNG files in frontend/shots/ to look at the
   result. For UI work follow DESIGN.md.
5. Paste the last lines of both outputs. Append one line to your progress file under "Log":
   done / next / blocker.
6. Stop and print the commit message `step N: ...`. Never commit. Do not start the next step.

If the gate is still red after two attempts at the same error, stop and report the error and
what you tried, instead of trying a third variation.
