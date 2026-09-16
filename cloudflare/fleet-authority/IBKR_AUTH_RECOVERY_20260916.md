# IBKR B1 pre-2FA authorization recovery gate

## Current proven boundary

Canonical broker authority:

- branch: `ibkr-b1-authority-v1`
- canonical workflow: `.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml`
- diagnostic comparator: `.github/workflows/ibkr-legacy-ibc-auth-comparator.yml`
- allowed workflow SHA: `8fe2cf4c5998bd5e5ef03d0bdc0e0280eefaa768`
- credential binding contract: `IBKR_PAPER_USERNAME+IBKR_PAPER_PASSWORD`
- deliberate event contract: `push+workflow_dispatch`
- controller path: `ibg-controller v0.10.0` / IB Gateway `10.45.1j`
- current IBC comparator: `gnzsnz/ib-gateway 10.49.1c` pinned by digest

Do not call raw controller `TWO_FA` a phone challenge. It is not authoritative.

## Exact cause discovered

The current 10.49.1c IBC comparator used the same sealed Cloudflare credential pair and reproduced the pre-2FA failure, but its launcher log exposed the server reason that 10.45.x had obscured:

`NSErrorResponse.MULTIPLE_PAPER_ERROR`

IBKR returned:

> The specified user has multiple Paper Trading users associated with it. Please log on using one of the Paper Trading users and corresponding password.

The sequence was:

`Paper Log In -> Connected ndc1.ibllc.com -> Authenticating -> MULTIPLE_PAPER_ERROR -> DISCONNECT_AUTHORIZATION_FAILED`

with **no** `NS_AUTH_START`, no second-factor dialog, and no IB Key mobile-approval wait signal.

Therefore the current failure is not evidence of a bad password and is not a 2FA failure. The submitted username is being treated by IBKR as a user that maps to multiple Paper Trading users. Gateway requires one concrete Paper Trading username and that paper user's corresponding password.

This also explains the historical MM-IBKR env comment:

`Paper login (use the specific paper user to avoid multi-paper prompt)`

## Retry freeze

Do **not** perform another broker login with the current Cloudflare credential values. Repeating the same username only reproduces the multi-paper rejection and can add unnecessary login pressure.

Ordinary code/CI pushes must remain validation-only. A broker attempt is justified only after the Cloudflare paper username/password have been changed to one explicit Paper Trading user pair.

## Operator-safe paper-user resolution

Never paste credentials into GitHub logs, issues, commits, ChatGPT, or other plaintext channels.

IBKR documents that the Paper Trading Account settings page lets the operator view the paper username/account number and reset the paper password:

`User menu -> Settings -> Account Configuration -> Paper Trading Account`

Use one concrete Paper Trading username shown there, not a production/master username that fronts multiple paper users.

Useful IBKR documentation:

- https://www.ibkrguides.com/orgportal/papertradingaccount.htm
- https://www.ibkrguides.com/advisorportal/paper.htm
- https://www.ibkrguides.com/clientportal/aboutpapertradingaccounts.htm

If the intended paper user's password is uncertain, reset that paper user's password from IBKR before rotating the authority.

## Cloudflare cutover

After choosing one explicit paper user, update the Worker secrets atomically:

- `IBKR_PAPER_USERNAME`
- `IBKR_PAPER_PASSWORD`

Do not add a production-credential fallback to source code and do not store either value in repository variables/files.

The non-secret health contract should continue to prove:

- `allowed_workflow_sha == 8fe2cf4c5998bd5e5ef03d0bdc0e0280eefaa768`
- `credential_binding_contract == IBKR_PAPER_USERNAME+IBKR_PAPER_PASSWORD`
- `paper_username_binding_configured == true`
- `paper_password_binding_configured == true`
- `allowed_event_contract == push+workflow_dispatch`

The health endpoint intentionally does not expose credential values or reusable fingerprints.

## One-attempt acceptance chain after rotation

After the explicit paper-user pair is installed, perform **one** deliberate broker attempt.

Accept outcomes in this order:

1. **Warm API ready**: reuse the authenticated session; no phone action is required.
2. **Exact IB Key mobile approval wait**: only `Waiting for IB Key mobile approval` authorizes telling the operator to approve IBKR Mobile.
3. **`MULTIPLE_PAPER_ERROR` again**: the username is still not one explicit paper user; stop and correct the authority.
4. **Explicit credential rejection**: controller-visible login failure / `bad-credentials` is a credential verdict; stop retries and correct the selected paper user's password.
5. **Other pre-NS authorization rejection**: stop retries and investigate the exact launcher reason before another attempt.
6. **Maintenance/reset**: retry only outside the guarded reset window.

Never reinterpret raw `TWO_FA` as outcome 2.

## First-auth completion criteria

A first attended authentication is not complete until all of these are true:

- exact real second-factor boundary observed (unless warm session already opened),
- IBKR Mobile approval accepted when required,
- local paper API is readable,
- canonical post-auth broker/session handoff is materialized,
- forward-data artifact is materialized,
- encrypted Gateway warm state is published.

Immediately follow with a second warm-reuse run. The durable objective is:

- warm state restored,
- API ready without a new phone challenge,
- ordinary read-only data jobs can consume the authenticated session.

If warm-state transplant across GitHub-hosted runners fails, diagnose session portability rather than falling back to repeated attended logins.
