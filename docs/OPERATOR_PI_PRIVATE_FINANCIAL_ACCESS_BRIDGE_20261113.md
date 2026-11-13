# Existing operator Worker: private Pi live financial bridge (review, not deployed)

Parent: private `XoticHaze/mm-IBKR#1654` and `#842`, consumer `#1655`; collector `XoticHaze/CommandCenter#1191`; current public Worker owner `XoticHaze/research-compute-public-`.

## Architectural correction

The **actually deployed** Access-locked operator service is the Cloudflare Worker named `mmibkr-operator-console`. Its Durable Object `OPERATOR_STATE` and human Access JWT/email policy already exist. The private MM Python `pi_live_account_api.py` is not deployed with the Cloudflare static assets; routing `ui-react/dist` alone cannot make Python `/api` endpoints work.

This source adds the same financial-envelope protocol to the **incumbent Worker + incumbent Durable Object**, not a second broker, a second dashboard, or a replacement paper stream:

- Machine `POST /v1/pi-live-financial`: existing Worker, protected by a separately path-scoped Cloudflare Access **Service Auth** application/policy. The Worker additionally verifies the Cloudflare-signed RS256 assertion, the exact service token client ID (`common_name`), distinct app audience, and fresh root HMAC over the exact account/cycle snapshot. No browser credentials or anonymous bearer token can publish.
- Durable Object `/pi-finance/store`: private, atomic monotonic last-cycle store. Reject rollback, same-cycle conflict, stale/future money, forged accounts, inconsistent positions and invented writer/margin claims. Duplicate identical cycle returns a nonfinancial receipt.
- Human `GET /api/operator/live-account`: same existing signed human Access JWT plus email allowlist; live money has a 420-second freshness bound and returns `503` when absent/expired. Response deliberately drops HMAC and account digest. Existing `GET /api/operator-snapshot` continues to report paper only. No cache.

Python source `mm-IBKR#1655` remains a contract and source-side adapter reference until the release owner chooses one served BFF. This Worker is the **candidate serving consumer**; do not deploy both Python and Worker consumers as competing source-of-truth services.

## Explicitly not admitted in this source PR

Do **not** enable or deploy this feature merely because Node tests passed. Existing Worker defaults OFF without both protected flags:

- `PI_LIVE_FINANCE_INGEST_ENABLED=1`
- `PI_LIVE_FINANCE_ORIGIN_ADMITTED=1`

It additionally requires protected Worker bindings (names only):

- `PI_LIVE_FINANCE_HMAC_KEY`: 32- or 64-byte hexadecimal secret, independently provisioned on the approved Pi root and Worker. It must never enter Git, logs, browser JS, public compute inputs or command receipts.
- `PI_LIVE_EXPECTED_ACCOUNT_SHA256`: digest of the root-sealed exact production account (not the account number). Bind independently, never infer from incoming packet.
- `PI_LIVE_FINANCE_ACCESS_AUD`: the audience of a dedicated path-scoped Cloudflare Access Service Auth application for the machine publisher.
- `PI_LIVE_FINANCE_SERVICE_CLIENT_ID`: exact enrolled Access service token client ID. Pi holds matching token secret in protected root-only storage; credentials are never supplied in chat or Git.
- Existing human `ACCESS_TEAM_DOMAIN`, `ACCESS_AUD`, `ACCESS_ALLOWED_EMAILS` remain unchanged. The machine app audience is distinct from the human browser app. The Worker never treats a human `email` claim as a machine principal.

The **owner must independently verify** that the service token's Access app covers the actual published hostname and the exact machine POST path on `workers.dev`; the Worker cryptographically checks its issued JWT and denies all other identities. See Cloudflare's *Service tokens* and *Application token* documentation; a raw service header alone is not proof of Access authentication.

## Producer/transport release sequence

1. Root-install the existing CommandCenter exact-account financial collector PR #1191 through the already protected Pi release mechanism. Root-owned `0600` private financial evidence and same-cycle count-only observer are required. Do not open another broker client or copy money to private Git status receipts.
2. Consume those two fixed root-owned files with the MM-IBKR projector in #1655, verifying same account, timestamp, currency and no unsupported inferred ownership or positions. Bind a fresh HMAC envelope. A direct Pi HTTPS courier must use a *fixed exact* allowlisted Worker origin/path, standard TLS with no redirects, separate Access service credentials in protected root storage, bounded payload size and nonfinancial receipt. No arbitrary URL/user-supplied shell, SSH, Gateway restart or private Actions.
3. Owner-review this public Worker module's final immutable source SHA, service app policy, secret read/write custody, and no raw-money telemetry. Deploy only by the **existing public, encrypted, pinned** `mmibkr-operator-console-deploy-r1.yml` release identity after independent approved-source admission. Public Actions must never receive plaintext private source/financial payloads.
4. Only after verifying private transport and Cloudflare Access issuer/audience/allowlist, separately set both enablement flags. Test unauthorized `401/403`, exact machine signed cycle `202`, browser logged-in `200`, absent/stale account `503`, and replay/conflicting cycle refusal. Check authenticated browser and network trace for no account hash/HMAC or cache.
5. Deploy the reviewed MM V4 React source that embeds `LivePiAccountPanel` on the existing `/bot-console`. Verify actual live Pi values in-browser. The public Worker still rejects `/markets`, `/portfolio`, `/portfolio/positions` by default. Source now requires a separate owner-managed `MMIBKR_FULL_V4_ROUTES_ADMITTED=1` gate to allow those exact browser paths after an accepted full V4 static/backend release; a generic SPA 200 is never proof of readiness. This PR **does not** declare the all-four-route product accepted.
6. Separately prove bot effective writer lease, strict fill-ledger commit, and pending unrelated-order margin reservations under at least 30% remaining cushion. The visibility path cannot permit new live order exposure and cannot adopt/flatten external holdings. Natural evaluation must be read from its existing strategy packet owner, not invented from a money or count snapshot.

## Verification and rollback

Native local `node --test` of the module: 12/12 cases passed with synthetic HMAC money, stale/future cycles, forged source and risks, Durable Object replay/conflict, and machine identity admission. A separate synthetic **Python-produced** MM envelope also passed JS HMAC verification, proving the cross-language canonical JSON contract. This is not live Pi, deployed Worker integration or browser acceptance.

Rollback: unset the two flags first (all machine POST requests denied), then revert the Worker release source using the existing approved rollback path. The last stored DO snapshot cannot be read by an unauthorized browser; it expires at 420 seconds for an authorized operator even if no new data arrives. Never clear a replay ledger to make stale broker balances appear fresh.

Status: `SOURCE_BRANCH_REVIEW_ONLY`, `NO_SERVICE_AUTH_POLICY_ADMITTED`, `NO_ROOT_FINANCIAL_COLLECTOR_INSTALLED`, `NO_PRODUCTION_MACHINE_DELIVERY`, `NO_SERVED_MONEY_READBACK`. No root/broker mutations in this source change.