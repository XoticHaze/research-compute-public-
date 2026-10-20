# Shared NVIDIA inference — private Cloudflare smoke (staged)

**State: SOURCE STAGED ONLY. NO WORKER DEPLOYED, NO SECRET BINDING VERIFIED,
NO NVIDIA INFERENCE CLAIM.** CommandCenter canonical provider registry:
`XoticHaze/CommandCenter/config/providers/nvidia_shared_inference.v1.json`;
tracking: [CC #929](https://github.com/XoticHaze/CommandCenter/issues/929).

## Operator-established facts (2026-10-19 CDT)

The operator says a fresh NVIDIA Developer API key was saved in the
**shared-compute Cloudflare account** with name `NVIDIA_API_KEY`.
Treat this as operator-attested storage, not Cloudflare API proof of a binding
or an authenticated inference completion. Never request the key value in
chat, and do not duplicate it into GitHub Secrets or public compute.

This Worker is a deliberately isolated **private provider route** for
CommandCenter, Voice Engine, HAOS role selection and future News Intelligence.
It does NOT share a key globally among agents or put it on
`fleet-authority`, `mmibkr-operator-console`, or any neutral security Worker.

## Provisioning route order: cloud-first, operator terminal as fallback

Cloudflare provisioning is **not tied to macOS**. First recover current
CommandCenter ordinary-account Worker creation and deployment authority;
reconcile with the successful October 13 canary provisioner/token scope
evidence in [CC PR #912](https://github.com/XoticHaze/CommandCenter/pull/912).
Those partial canary proofs do not establish a live reusable factory executor.
Inspect the current source and live grant scope before reusing any credential.

Preferred path is an already-authorized Cloudflare-side ordinary-account
factory/executor and governed deploy route, using reviewed Secrets Store
binding metadata and a private approved diagnostic caller. CI may deploy
only if its specifically admitted deployment identity has sufficient
ordinary-worker and binding authority; a generic public CI runner must
not receive the NVIDIA key or unrestricted management credentials.
Do not grant the NVIDIA key to neutral security Workers or widen existing
neutral credentials. Keep the account separation selected in CommandCenter
`docs/security/SHARED_COMPUTE_NEUTRAL_ACCOUNT_SEPARATION_V1.md`.

If no suitable reusable deployment authority can be proven, a one-time
operator-approved bootstrap is a separate explicitly identified gate;
it may be done through the Cloudflare dashboard or an authorized CLI
on any operator-controlled platform, **not necessarily the Mac**.
The local Wrangler caller documented below is an optional diagnostic
fallback, not a required or default route. Nothing in this PR alone
proves that a remote factory or live cloud diagnostic has run.

## One-time Cloudflare admission

1. Verify the name `NVIDIA_API_KEY` exists under the intended Cloudflare
   account **Secrets Store**, with `Workers` permission scope. A secret
   created under one Worker's *Settings → Variables and Secrets* is different
   and does not imply account-level Secrets Store access.
2. Approve a dedicated internal-only Worker, `cc-shared-nvidia-inference`,
   through the existing trusted non-neutral Worker factory (preserve all
   pre-existing deploy credentials / scopes). Its Wrangler config has
   `workers_dev: false`, `preview_urls: false`, no route, and
   `CC_NVIDIA_DIAGNOSTIC_ENABLED: "0"`.
3. Before deploying, prepare the **reviewable store binding** using only the
   Cloudflare account Secrets Store ID (NOT the NVIDIA API key). Copy the real
   store ID from https://dash.cloudflare.com/?to=/:account/secrets-store .
   From this Worker directory run:

   ~~~sh
   node scripts/render-secret-binding.mjs --store-id <32-character-store-id>
   ~~~

   This renders the locally ignored, owner-readable file `wrangler.bound.jsonc`.
   It contains only the store ID, secret name and binding name; never a key
   value. The generator does not deploy, authenticate or run an inference.
   When an authorized deployment is later approved, use Wrangler's
   `--config wrangler.bound.jsonc` rather than the default unbound manifest.
   Never copy a store ID from a different/neutral security Cloudflare account.

4. **Only after the Worker exists**, bind the account Secrets Store secret
   through Workers → `cc-shared-nvidia-inference` → Settings → Bindings →
   Add → Secrets Store. Binding variable **`NVIDIA_API_KEY`** and secret
   name **`NVIDIA_API_KEY`**. Deploy the reviewed binding; do NOT bind to
   any shared neutral Worker. This configuration file intentionally omits
   `secrets_store_secrets` because the actual account store ID has not been
   verified in the source. Before any further Wrangler redeploy, reconcile
   binding source-of-truth to the real store ID or preserve it explicitly;
   never fabricate store IDs.
5. Admit one private **Service Binding** from an approved internal
   CommandCenter test caller to this Worker. There is no public HTTP route.
   Do not enable diagnostics until that invocation/authentication path
   is proven and approved.
6. Temporarily set `CC_NVIDIA_DIAGNOSTIC_ENABLED=1` only on the private
   Worker. Service-bound caller sends **POST**
   `/internal/diagnostics/nvidia` with no body. The request does not select
   the model, prompt or URL.
7. Examine the sanitized receipt and disable diagnostics again. Only then
   publish operator-reviewed provider capabilities to CC; no raw provider
   responses, API key, HTTP error body or household prompts are published.

Official binding guidance:
https://developers.cloudflare.com/secrets-store/integrations/workers/

## Exactly bounded first request

At most two NVIDIA requests, to fixed HTTPS origin
`https://integrate.api.nvidia.com`:
- `GET /v1/models` with bound key; emit only HTTP status, count, whether
  `openai/gpt-oss-20b` appears.
- `POST /v1/chat/completions` with same bound key, fixed synthetic prompt,
  fixed model `openai/gpt-oss-20b`, `max_tokens=64`. Emit only HTTP status,
  response-shape booleans and elapsed time. No model answer logged/returned.

If account/catalog returns 200 but completion 403, compare to existing HAOS
HTTP 500 carrying **provider 403**. A catalog listing is not model inference
authorization. No retry storm, fallback key discovery, price estimate,
automated promotion, HAOS config writes, device control or news-source access.

## Cross-project interpretation

CC model discovery can publish reviewed availability/latency evidence.
Voice Engine PR #3 remains canonical for model-role benchmark ranking.
Home Assistant's independent stored NVIDIA key remains unchanged until
the new shared credential has passed a live inference test and HA Assist
tool/entity contracts are qualified. News Intelligence P11 can later use
the shared inferencer for **sentiment/relevance/ticker/entity scoring**, not
as news ingest or publication timestamps: preserve P11 publication-time
admission, coverage and OOS ablation. Evolution Auditor should track
`OPERATOR_SECRET_SAVED_BINDING_PENDING`, then source deployment, binding
proof, catalog/inference proof, consumer access and product promotion as
separate states.

## CI / local offline proof

From `cloudflare/shared-nvidia-inference`: `npm test`.
Tests use fake Cloudflare bindings and fake NVIDIA responses, without any
provider credentials. A green test is *not* a live NVIDIA call.

## Optional operator-local fallback caller: no second permanent Worker (2026-10-19)

After the dedicated `cc-shared-nvidia-inference` Worker is deployed with its
verified account Secrets Store binding, the **first** diagnostic can use the
checked-in `local-probe/` caller instead of creating a persistent public
gateway or granting the NVIDIA secret to an existing neutral Worker.

The caller has **no NVIDIA credential**, **no account Secrets Store binding**,
and **no public hostname**. Its sole Cloudflare capability is a remote Service
Binding to `cc-shared-nvidia-inference`. Only a local POST to `/run-once`
with no body causes exactly one fixed upstream service call for that local
process; the caller sanitizes upstream receipt fields again.

Prerequisites: operator-approved Worker creation/deployment and secret binding
to the **ordinary shared-compute account**; authorized Wrangler login to that
account; and the private inference Worker's diagnostic flag temporarily
enabled to `1` **only after** the private Service Binding route is approved.
Cloudflare deployments attaching Secrets Store bindings require corresponding
Secrets Store binding/edit authority, which is separate from ordinary Worker
source-edit privileges. Do **not** expand existing neutral Worker deployment
credentials to get around that gate.

Start from the repository Worker directory on an operator-controlled machine:

```sh
npx wrangler@4 dev --config local-probe/wrangler.jsonc --ip 127.0.0.1 --port 8787
```

Once Wrangler reports the `NVIDIA_SERVICE` remote binding connected, run
this from a second terminal **once**:

```sh
curl --silent --show-error -X POST http://127.0.0.1:8787/run-once
```

The result is a **local, sanitized** catalog + completion receipt, not a
deployment promotion. Preserve only the approved receipt fields in the private
capability ledger; do not put raw responses or the store ID in public CI logs.
Immediately change `CC_NVIDIA_DIAGNOSTIC_ENABLED` back to `0` on the
deployed inference Worker, stop the local `wrangler dev` session, and verify
that a later diagnostic is unavailable. Do not deploy the local caller with
`wrangler deploy`. It is a one-time operator test harness, not a runtime
consumer. Home Assistant, Voice Engine and News Intelligence consumers still
require separate runtime admission.

The offline `npm test` suite covers caller ingress, single invocation, fixed
remote destination and receipt redaction. It does **not** verify that remote
bindings connect or that live NVIDIA inference works.
