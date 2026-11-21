---
name: hn-stan
description: Save the state of work into the progress file so a new session, Codex or a teammate can continue. Use before sleep, at a usage limit, before switching agents. Manual only.
disable-model-invocation: true
---

# hn-stan: state for whoever continues

Your progress file is PROGRESS.md, or PROGRESS.web.md / PROGRESS.api.md when the file .hn-area
exists. Rewrite its "State" section (keep the sections below it). At most 25 lines:

- Time, and the output of `git log -1 --oneline` and `git status --short | wc -l`.
- Done: the "Must" items from SPEC.md that work, each with the test that proves it.
- In progress: the current step, the files touched, what is left.
- Broken or red right now: exact command and its last failing line. Say "nothing" if nothing.
- Next three steps, in order.
- Decisions waiting for the human.

Then run `bash scripts/gate.sh` and write its last line under the section. Do not change any
other file. Do not commit.

To resume in a new session or in Codex, the human says: "Read AGENTS.md, SPEC.md and the State
section of the progress file, check the state against git, then continue with the first next
step."
