# IBKR B1 authentication recovery + resume gate

## Purpose

This file is the durable resume point for the IBKR Paper read-only authentication lane. It supersedes the earlier pre-2FA-only diagnosis in this file.

Do not restart the investigation from the original `DISCONNECT_AUTHORIZATION_FAILED` symptom. The credential boundary has moved materially since that point.

## Current source truth

Repository: `XoticHaze/research-compute-public-`

Canonical broker authority:

- branch: `ibkr-b1-authority-v1`
- current branch HEAD: `2cd779dc56b06c382c6320466c580c22edf19730`
- canonical workflow: `.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml`
- diagnostic comparator: `.github/workflows/ibkr-legacy-ibc-auth-comparator.yml`
- credential binding contract: `IBKR_PAPER_USERNAME+IBKR_PAPER_PASSWORD`
- deliberate event contract: `push+workflow_dispatch`
- allowed workflow contract: `canonical-b1+legacy-ibc-comparator`
- canonical controller path: `ibg-controller v0.10.0` / IB Gateway `10.45.1j`
- current IBC comparator: `ghcr.io/gnzsnz/ib-gateway:10.49.1c`, pinned by immutable digest

Recent auth-branch hardening after the original 10.49 comparator point:

- `0bec094d15c2bdff1c835ca1dfe486d52f230780` — `fix(ibkr): classify multiple paper users explicitly`
- `718b270636e780bf0c25c12c5ce75afdd2b8bc16` — `fix(ibkr): make post-auth pipeline direct entrypoint import-safe`
- `2cd779dc56b06c382c6320466c580c22edf19730` — `test(ibkr): guard direct post-auth entrypoint imports`

## Credential diagnosis: UPDATED

An earlier 10.49.1c comparator attempt exposed:

`NSErrorResponse.MULTIPLE_PAPER_ERROR`

IBKR said the submitted user had multiple Paper Trading users associated with it and requested one concrete Paper Trading username/password pair.

The operator then reverified that the configured username is the explicit Paper Trading username from IBKR Paper Trading settings. The operator did **not** replace it with a `DU...` account number. A `DU...` account number is not the login username and must not be substituted into `IBKR_PAPER_USERNAME`.

After that re-verification, the same sealed Cloudflare paper credential pair was tested again through the pinned 10.49.1c IBC comparator. The prior `MULTIPLE_PAPER_ERROR` did **not** reproduce. The comparator progressed into the IBKR authentication protocol and emitted evidence including:

- `NS_AUTH_START` / authentication protocol start
- `Passed pwd authentication.`
- `Authentication completed.`
- `IBKR_LEGACY_CREDENTIALS_ACCEPTED_PRE_2FA=1`

### Current credential conclusion

The current Cloudflare-sealed Paper Trading username/password pair has now been accepted by IBKR through the password/pre-2FA boundary.

Do **not** treat the current pair as unverified or reset/rotate it merely because of the older multi-paper result. Do **not** change the username to a `DU...` account number.

The active problem is now advancing the canonical attended path through the real second-factor/session boundary, not proving password validity again.

## Critical authority/deployment mismatch to resolve FIRST

At this checkpoint, repository source has a deliberate SHA mismatch that must be reconciled before another canonical broker attempt:

- auth branch HEAD = `2cd779dc56b06c382c6320466c580c22edf19730`
- `.github/workflows/fleet-authority-health-probe.yml` on `main` expects `2cd779dc56b06c382c6320466c580c22edf19730`
- `cloudflare/fleet-authority/src/index.js` checked into `main` still has `ALLOWED_WORKFLOW_SHA = '0bec094d15c2bdff1c835ca1dfe486d52f230780'`

Do not assume the live Worker has either value without proving `/healthz` after deployment.

### Cheapest decisive next executable

1. Update the Worker source pin to exactly `2cd779dc56b06c382c6320466c580c22edf19730`.
2. Use the existing Cloudflare deployment-trigger mechanism; do not invent a second deployment path.
3. Run/consume the existing Fleet Authority health probe.
4. Require live `/healthz` to prove all of:
   - `allowed_workflow_sha == 2cd779dc56b06c382c6320466c580c22edf19730`
   - `credential_binding_contract == IBKR_PAPER_USERNAME+IBKR_PAPER_PASSWORD`
   - `allowed_event_contract == push+workflow_dispatch`
   - `allowed_workflow_contract == canonical-b1+legacy-ibc-comparator`
   - paper username/password bindings configured
5. Only after that provenance gate is green, dispatch exactly **one** canonical `IBKR Cloudflare Read-Only B1 R1` run at the immutable auth-branch HEAD.

Do not make an auth-branch commit merely to trigger login; changing the SHA recreates the Worker-pin race. Use the existing deliberate dispatch path/workflow-dispatch once the Worker is pinned to the current immutable HEAD.

## Canonical attended-login acceptance chain

Watch the canonical run in this order:

1. **Warm API ready** — consume the authenticated session; no phone action required.
2. **Exact IB Key mobile wait** — only the literal signal `Waiting for IB Key mobile approval` is authority to tell the operator to approve IBKR Mobile.
3. **Real second-factor boundary without the exact mobile-wait token** — inspect exact controller/launcher evidence before instructing the operator.
4. **`MULTIPLE_PAPER_ERROR`** — stop; this would contradict the latest accepted-credential comparator and needs exact launcher evidence before changing credentials.
5. **Explicit bad-credentials/login-failed evidence** — stop; do not retry blindly.
6. **Other pre-NS authorization rejection** — stop and inspect the exact launcher reason.
7. **Maintenance/reset** — retry only outside the guarded reset window.

Never treat raw controller state `TWO_FA` as proof that a phone notification exists.

## First-auth completion criteria

A successful first attended authentication is not complete until all of these are true:

- real second-factor boundary observed (unless a warm session opens directly),
- IBKR Mobile approval accepted when actually required,
- local Paper API is readable,
- canonical post-auth broker/session handoff is materialized,
- forward-data artifact is materialized,
- encrypted Gateway warm-state artifact is published.

Then immediately run a second warm-reuse proof and require:

- warm state restored,
- API ready without a new phone challenge,
- ordinary read-only data jobs able to consume the authenticated session.

If cross-runner JTS state transplant fails, diagnose session portability. Do not fall back to repeated attended-login spraying.

## Post-auth pipeline already present

The canonical workflow is designed to continue beyond authentication rather than stopping at login. Its post-auth path is intended to:

- connect read-only to the local Paper API,
- verify the managed paper account,
- read broker time/account summary/positions/open orders,
- fetch AMAT/APH historical bars,
- emit normalized forward-bar evidence,
- materialize the broker/session handoff,
- publish encrypted warm Gateway state.

Recent commits `718b270...` and `2cd779...` specifically hardened direct post-auth entrypoint imports/tests. Preserve those changes.

## Safety / retry rules

- Paper/read-only only.
- Never paste or print credential values.
- One broker attempt per meaningful discriminator.
- Ordinary code pushes should remain validation-only.
- Do not use live credentials as a fallback.
- Do not change regional servers without new evidence.
- Do not downgrade/upgrade Gateway/controller merely to chase authentication after the 10.49 comparator accepted the current credential pair.
- Do not claim a second-factor push was sent unless the exact mobile-approval wait evidence exists.

## Historical context that is now CLOSED

These were useful discriminators but are no longer the active blocker:

- controller v0.10.0 / 10.45.1j version uncertainty
- guessed regional server override
- Cloudflare secret binding-name ambiguity
- generic `DISCONNECT_AUTHORIZATION_FAILED` as an unexplained credential verdict
- whether the current sealed pair can pass password authentication

The latest comparator moved the boundary forward: current credentials are accepted pre-2FA. Continue from the authority/deployment provenance gate, then one canonical attended login.
