# Existing operator Worker: private Pi live financial bridge (code deployed, finance locked)

<!-- CURRENT_PROD_STAGE_20261114_WORKER_CODE_DEPLOYED -->
## CURRENT RELEASE RESULT: Worker code in production; private money still locked (Nov 14, 2026 UTC)

**Actual deployed, source frozen:** [PR #2148](https://github.com/XoticHaze/research-compute-public-/pull/2148) merged as `c65396629f657297ba90d5f9e7e00fd994519ff6`. Existing approved, encrypted [public deploy run #43537675732](https://github.com/XoticHaze/research-compute-public-/actions/runs/43537675732), with fire `ce6ba7d93912a2b8e5af6ff8371bf69bbab9e6d5`, finished **CONTRACT=SUCCESS; DEPLOY=SUCCESS**. Wrangler deployed `mmibkr-operator-console`, initial version `ef7354a8-fbd1-4d27-84e6-f71e1616cfca`; Cloudflare control-plane, Access email reconciliation, exact frozen private UI vault materialization, OIDC bindings, unauthenticated fail-close, R2 receipt publication and source destruction succeeded. Authoritative release receipt: `main:rendezvous/receipts/mmibkr-operator-console-deploy-r2.json`.

**Still disabled/held:** finance machine Service Auth and protected secrets (no `PI_LIVE_FINANCE_INGEST_ENABLED=1` or `PI_LIVE_FINANCE_ORIGIN_ADMITTED=1`), protected Pi root financial reader (CommandCenter #1191) and fixed courier (MM #1655) not installed, newly selected V4 finance UI **not** source-vault/owner-approved or served (old frozen private UI `f6f6dcdcbad3df8c5d50cab5ac2652b4781a648d` was deployed). Do **not** repeat public Worker source CI/deploy to cure missing root/client credentials; follow source/credential/owner admission in MM-IBKR [#1654](https://github.com/XoticHaze/mm-IBKR/issues/1654). Neither this deployment nor a 403/503 proves live account money or trading authority.

Rollback remains independently owner-gated: if the newly merged Worker source causes a served regression, use the existing reviewed public release/rollback workflow and the previously accepted immutable static source, never remove human Access protections or expose private source. The feature remains default OFF until separate admission.

---

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

## Exact Cloudflare Access Service Auth admission (owner-managed)

The existing `mmibkr-operator-console.slenderiq.workers.dev` human application is NOT a machine identity. Cloudflare's official Access application-path contract says a **more-specific URL path policy takes precedence**, without inheriting the broader site's human allow policy:
https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/
and Cloudflare documents path-specific Worker Access protection here:
https://developers.cloudflare.com/workers/configuration/cloudflare-access/

For this branch, the owner must **independently inspect current original-account Access application state** before creating/changing anything. The intended narrow machine policy is a self-hosted Access application scoped to the **exact URL path** `/v1/pi-live-financial` on the *existing* Worker hostname, with `Service Auth` decision allowing **one** dedicated service token. The broad operator human Access application/email policy must stay intact for `/bot-console`, `/api/operator/live-account` and the existing operator pages. Do not use an Access `Bypass` policy, a wildcard that authorizes unrelated routes, or a shared browser-user credential. Protect every alternate Worker hostname/preview/reachable route with the owning Access policies, because the Worker checks signed principal claims independently but an unprotected alternate route would be an unwanted second ingress.

Cloudflare official service token contract:
https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/
The root courier uses **exactly** `CF-Access-Client-Id` and `CF-Access-Client-Secret`; fresh service secret formatting may start with `cfast_` and must be read from protected root-only files, never logged, emailed or committed. Prefer enabling `Strict service token authentication` (Cloudflare's documented `401/403` on rejected tokens rather than login redirects), with the current account's existing policy/app compatibility reviewed first. The courier independently refuses HTTP redirects regardless.

The Worker verifies a signed `Cf-Access-Jwt-Assertion` using the CURRENT original team JWKS, distinct machine application `aud`, `type=app`, `common_name` exactly matching the enrolled service Client ID, empty `sub`, and no human email; it also validates the Pi HMAC and exact production account hash. Cloudflare documents these service-token JWT fields here:
https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/

Require these verified **private runtime bindings**, not repository literals:

- Worker `PI_LIVE_FINANCE_HMAC_KEY`, `PI_LIVE_EXPECTED_ACCOUNT_SHA256`, `PI_LIVE_FINANCE_ACCESS_AUD`, `PI_LIVE_FINANCE_SERVICE_CLIENT_ID`, plus existing `ACCESS_TEAM_DOMAIN` human Access bindings. Independently validate actual Access issuer/audience and no public errors containing secrets.
- Pi root `/etc/commandcenter-pi/pi-live-financial-hmac-key` (HMAC hex), `/etc/commandcenter-pi/pi-live-financial-access-client-id`, `/etc/commandcenter-pi/pi-live-financial-access-client-secret`, `/etc/commandcenter-pi/pi-live-financial-delivery-approval.json`, and existing protected expected-account seal; all protected files root-only `0600` and separately owner-reviewed.
- Keep `PI_LIVE_FINANCE_INGEST_ENABLED`, `PI_LIVE_FINANCE_ORIGIN_ADMITTED`, and `MMIBKR_FULL_V4_ROUTES_ADMITTED` **unset/off** until their respective protected admission receipts exist.

**Attended acceptance order:** read current Access application/policy via scoped administrator first; admit exact machine service-token/path rule; install and inspect the independently approved root collector/projector/courier source; deploy the reviewed exact Worker+selected V4 assets using existing allowed public-encrypted release; verify unauthorized POST is 403 and unauthorized human GET denied, then a genuine signed Pi cycle produces a status-only 202 acknowledgement and an authorized same-origin GET with observed financial values, no HMAC/account ID leakage, and a 503 after 420 seconds without new data. Record exact deployment version and browser result. An ordinary GitHub PR cannot prove any of these steps.

**Precaution:** the existing Worker-host Access configuration and an independently approved service-token issuer must be verified as actually present, not inferred from source. This is SOURCE_ONLY until root/Access/deploy receipts independently establish it.
