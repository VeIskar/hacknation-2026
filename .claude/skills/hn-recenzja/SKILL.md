---
name: hn-recenzja
description: Second opinion from Codex on the current work, with every finding checked against the code before anything is changed. Run after a "Must" item turns green and before the freeze, not after every step. Manual only.
disable-model-invocation: true
argument-hint: "[optional: tag or commit to review from, e.g. demo-1]"
---

# hn-recenzja: Codex reviews, you verify, then fix

Codex is a second reviewer with its own usage limit and each run takes several minutes. One
run per invocation. Never rerun it in the same turn.

1. Get the review. Set the Bash timeout to 600000 ms for this command.
   - No argument: `codex review --uncommitted 2>/dev/null`
   - Argument is a tag or commit: `codex review --base <argument> 2>/dev/null`
   The review is what the command prints. If `codex` is not installed, the command fails, or
   it prints nothing, run the `reviewer` subagent instead and continue with its findings.
2. Check every finding yourself. Open the file at the line it names and decide:
   - CONFIRMED: you can point at the line that breaks a "Must" item, the demo flow, the API or
     field contract, an accessibility rule from DESIGN.md, or leaks a secret.
   - FALSE: the code does not do what the finding says. Say why in one line.
   - LATER: true, but nothing in the demo depends on it. Findings about dependencies,
     licences, Dockerfiles, the gate scripts or the e2e spec files are always LATER: describe
     them for the human, do not change those files here.
   A finding is not confirmed because Codex said it. Do not skip this step.
3. Fix only CONFIRMED findings inside your area (see "Team" in AGENTS.md), the smallest change
   each, with a test that fails without the fix where one is possible. A confirmed finding
   outside your area becomes one line under "Requests" in your progress file.
4. Run `bash scripts/gate.sh` (and `cd frontend && npm run test:e2e` if anything visible
   changed). Paste the last lines.
5. Write REVIEW.md (not committed): one line per finding with its class and what you did.
   Print the same table, then the commit message. Never commit.
