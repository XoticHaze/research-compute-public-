# IBKR B1 pre-2FA authorization recovery gate

## Current proven boundary

Canonical broker workflow authority:

- branch: `ibkr-b1-authority-v1`
- workflow: `.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml`
- allowed workflow SHA: `fb04a11547a99b85d05c382f2fefb3a641aeb664`
- credential binding contract: `IBKR_PAPER_USERNAME+IBKR_PAPER_PASSWORD`
- deliberate event contract: `push+workflow_dispatch`
- controller: `ibg-controller v0.10.0` / IB Gateway `10.45.1j`

The last broker attempt reached the launcher sequence:

`Connected -> Authenticating -> DISCONNECT_AUTHORIZATION_FAILED`

It did **not** reach `NS_AUTH_START`, a second-factor dialog, or the exact controller signal `Waiting for IB Key mobile approval`.
The v5 classifier waited for a human-readable credential error and observed none, so the result remains:

`authorization_rejected_no_ui_diagnosis`

Do not call raw controller `TWO_FA` a phone challenge. It is not authoritative.

## Retry freeze

Do **not** perform another broker login solely because code, CI, Worker deployment, or the controller changed.
Ordinary pushes run validation only. The broker job is gated behind either:

1. an explicit `workflow_dispatch`, or
2. a push whose commit message contains `[ibkr-login]`.

A new broker attempt is justified only after one of these facts changes:

- the intended IBKR credentials have been independently verified against Paper Trading, or
- the paper password has been reset and the Cloudflare bindings have been rotated to the verified values, or
- IBKR Client Services has cleared/identified an account-side login restriction.

## Operator-safe credential verification

Never paste the username/password into GitHub logs, issues, commits, ChatGPT, or other plaintext channels.

Preferred automation authority is the dedicated Paper Trading credential pair already represented by:

- `IBKR_PAPER_USERNAME`
- `IBKR_PAPER_PASSWORD`

IBKR currently documents that Paper Trading settings allow the operator to view the paper username/account number and reset the paper password. In Client Portal, use:

`User menu -> Settings -> Account Configuration -> Paper Trading Account`

Useful current IBKR documentation:

- https://www.ibkrguides.com/advisorportal/paper.htm
- https://www.ibkrguides.com/clientportal/accountmanagementforpapertradingaccount.htm
- https://www.ibkrguides.com/clientportal/aboutpapertradingaccounts.htm

IBKR also documents that many individual accounts may enter production credentials while selecting Paper Trading, while some account classes/regions still require dedicated paper credentials. Because this automation intentionally has a dedicated paper binding contract, verify the dedicated paper username/password first rather than silently switching credential classes.

### Independent verification

Use one of these without exposing the values:

1. Log into IBKR TWS/Gateway or Client Portal with **Paper Trading selected** and the intended dedicated paper credentials; or
2. use an authorized IBKR account connector that proves the intended account can authenticate; or
3. if the paper password is uncertain, reset it from the IBKR Paper Trading Account settings.

If IBKR reports the account is disabled/locked or the verified credentials cannot log in interactively, stop automated attempts and resolve the account state with IBKR first.

## Cloudflare cutover

After the credential pair is verified or reset, update the Cloudflare Worker secrets atomically:

- `IBKR_PAPER_USERNAME`
- `IBKR_PAPER_PASSWORD`

Do not add a production-credential fallback to source code and do not store either value in repository variables/files.

After secret rotation, `/healthz` must still prove only non-secret facts:

- `allowed_workflow_sha == fb04a11547a99b85d05c382f2fefb3a641aeb664`
- `credential_binding_contract == IBKR_PAPER_USERNAME+IBKR_PAPER_PASSWORD`
- `paper_username_binding_configured == true`
- `paper_password_binding_configured == true`
- `allowed_event_contract == push+workflow_dispatch`

The health endpoint intentionally does not expose credential values or reusable fingerprints.

## One-attempt acceptance chain

After credential/account verification, perform **one** deliberate broker attempt.

Accept outcomes in this order:

1. **Warm API ready**: reuse the authenticated session; no phone action is required.
2. **Exact IB Key mobile approval wait**: only the exact controller evidence `Waiting for IB Key mobile approval` authorizes telling the operator to approve IBKR Mobile.
3. **Explicit credential rejection**: controller-visible login failure / `bad-credentials` is a credential verdict; stop retries and correct the authority.
4. **Silent pre-NS authorization rejection**: `DISCONNECT_AUTHORIZATION_FAILED` without `NS_AUTH_START` and without a visible bad-credentials alert remains an account/authorization boundary; stop retries and investigate IBKR account state.
5. **Maintenance/reset**: retry only outside the guarded reset window.

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
