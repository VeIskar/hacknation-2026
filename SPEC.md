# SPEC (one page; filled by /hn-spec)

## Task and criteria

(official task name, the judging criteria with weights)

## User and problem

(one user, one sentence of pain)

## Demo flow

(numbered clicks from the first screen to the result)

## Must (at most 5, each visible in the demo; one owner per item)

1.

## Later (only if every Must is green)

## Out (said out loud, so nobody builds it)

## API contract

(every endpoint the demo flow needs: method, path, one example request, one example response.
Frontend builds against these examples while backend implements them.)

## Field contract

(only if the task has structured data: one JSON example shared by frontend and backend)

## Real and mocked

(what really works, what is a fixture)

## Acceptance test

frontend/tests/e2e/acceptance.spec.ts walks the demo flow. It is locked after review.
