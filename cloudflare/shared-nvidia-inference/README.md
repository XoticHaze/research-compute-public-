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
3. **Only after the Worker exists**, bind the account Secrets Store secret
   through Workers → `cc-shared-nvidia-inference` → Settings → Bindings →
   Add → Secrets Store. Binding variable **`NVIDIA_API_KEY`** and secret
   name **`NVIDIA_API_KEY`**. Deploy the reviewed binding; do NOT bind to
   any shared neutral Worker. This configuration file intentionally omits
   `secrets_store_secrets` because the actual account store ID has not been
   verified in the source. Before any further Wrangler redeploy, reconcile
   binding source-of-truth to the real store ID or preserve it explicitly;
   never fabricate store IDs.
4. Admit one private **Service Binding** from an approved internal
   CommandCenter test caller to this Worker. There is no public HTTP route.
   Do not enable diagnostics until that invocation/authentication path
   is proven and approved.
5. Temporarily set `CC_NVIDIA_DIAGNOSTIC_ENABLED=1` only on the private
   Worker. Service-bound caller sends **POST**
   `/internal/diagnostics/nvidia` with no body. The request does not select
   the model, prompt or URL.
6. Examine the sanitized receipt and disable diagnostics again. Only then
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
