# CommandCenter Cloudflare SlenderIQ read-only R1

Status: **REVIEW-ONLY SOURCE** until the authorized owner has reviewed/merged the workflow and independently checked a real Cloudflare-origin receipt. This adds no Cloudflare API token, account, Worker, Cron, or deployment.

## Ownership and permitted operations

This is a fixed-scope extension of the existing SlenderIQ public-GitHub Cloudflare management precedent. It is not the neutral secure-compute administrator. It never writes Cloudflare state, reads private source, or grants runtime or trading permission.

| Typed operation | Fixed Cloudflare read | Result boundary |
| --- | --- | --- |
| cloudflare.worker_status | GET /accounts/{configured-account}/workers/scripts/{fixed-worker}/settings | Binding counts and presence of four pre-approved binding names, never values |
| cloudflare.release_status | GET /accounts/{configured-account}/workers/scripts/{fixed-worker}/deployments?per_page=1 | First/current deployment timestamp, traffic percentages, SHA-256 of sorted active version identities; **not** approved source proof |

Targets: mmibkr-operator-console, fleet-authority only. The separate neutral reference-release-broker-v1, reference-release-maintainer-v1, reference-maintenance-authority-v1 and any arbitrary account/Worker are **not** targets here.

## GitHub request path

After owner review and merge onto public main, the incumbent GitHub-linked ChatGPT worker may create or update exactly:

Repository: XoticHaze/research-compute-public-
Branch: main
Path: rendezvous/fire/cloudflare-worker-readonly-r1.json

Typed request JSON:

~~~json
{
  "schema": "commandcenter.cloudflare_worker_readonly_request.r1",
  "request_id": "cc-status-unique-nonce-001",
  "operation": "cloudflare.worker_status",
  "worker": "mmibkr-operator-console"
}
~~~

Use a **fresh request ID** for each desired read. This is a GET-only, idempotent observation; do not confuse its request ID with protected mutation replay approval. Once merged, the existing mainline push trigger only runs when that exact fire path changes. The workflow also exposes the same fixed operations through workflow_dispatch for an owner.

## Result and consumption

The workflow executes eight bounded local-source regression cases, uses existing SlenderIQ repository secrets, then performs one fixed GET and emits a sanitized JSON artifact named cloudflare-worker-readonly-<github.run_id>. GitHub artifact retention is 7 days: it is **not a perpetual durable CommandCenter receipt**. The owning CommandCenter consumer must read the exact GitHub run/artifact identity, verify the expected schema/target/operation and persist the final result in its already authorized durable GitHub receipt channel before claiming end-to-end control.

A Cloudflare deployment version-set fingerprint attests only to the Cloudflare API observation. It does **not** prove a particular private MM-IBKR source SHA, owner approval, full-app /markets backend, authenticated desktop/mobile render, or live trading. The V4 release must independently pass its own exact-SHA, Source Vault, browser, Access and negative-access gates.

## Safety and recovery

- On missing credentials, denied scope, unknown target, malformed result, non-100% summed deployment weights, absent deployment, network failure or oversized body: fail closed. Do not invent a healthy Worker state.
- Do not log the account ID, API token, raw Cloudflare response, unknown binding name, binding value, script source, deployment author or annotations.
- No request JSON can supply an account, arbitrary HTTP path/method, new Worker or deploy action.
- Never substitute this SlenderIQ route for an administrator of the isolated neutral compute account.
- If the public fire workflow is not merged/admitted, this is source-only. Do not trigger private GitHub Actions or use manual shell as an execution workaround.

### Closeout acceptance

Owner-reviewed source and 8/8 source tests; first authenticated read with exact GitHub workflow run and sanitized artifact; CommandCenter consumer persists a same-request durable receipt; negative target and denied-token behavior remain fail-closed. Until all four are proven, classify **CAPABILITY_STAGED_NOT_LIVE**.
