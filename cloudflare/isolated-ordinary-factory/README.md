# CC isolated ordinary Worker factory: new Cloudflare account

**Status:** public, source-only bootstrap candidate. NO new Cloudflare account ID has been read back; no Worker or credential has been deployed to that new account. The owning operator reports that `CC Ordinary Deployments` account exists.

## Why a separate account?

The live October 12 original SlenderIQ factory-token test proved same-role Workers Admin DENY blocks ordinary Worker creation (HTTP403). Deleting DENY would expose protected original-account Workers. The separate existing neutral account hosts sensitive signers and Studio. Neither should receive a standing new-Worker administrator.

`CC Ordinary Deployments` is a **new, empty ordinary-resource account**. Its account-specific Workers product Admin will be kept **inside Cloudflare**, on a dedicated factory Worker, with no access to original SlenderIQ or Shared Compute Neutral. This preserves project neutrality without a management token per new project.

## Pinned-source generator

Use **the existing** source implementation in `cloudflare/shared-worker-factory/src`, not an independently maintained controller. `scripts/prepare.mjs` checks six exact Git blob hashes, converts the two old account pins to the new account, adds the factory self-name to the protected-name rules, enables Cloudflare Worker-specific secrets as well as Secrets Store handles, and creates a new isolated-account Wrangler config. It refuses both existing account IDs, invalid IDs, accidental cross-account overwrites, or source drift.

```sh
# From a checkout of this PUBLIC repo at the approved merged SHA:
node cloudflare/isolated-ordinary-factory/scripts/prepare.mjs --account-id NEW_32_HEX_ACCOUNT_ID
node --test cloudflare/isolated-ordinary-factory/tests/*.test.mjs
```

Generated (not committed): `cloudflare/isolated-ordinary-factory/.generated/wrangler.jsonc`, `src/*.js`, `manifest.json`. Confirm their new account ID matches the **Cloudflare dashboard** before first deployment. The generated manifest is nonsecret and contains SHA256 for every emitted file. The script never opens the network and never stores or accepts API tokens.

## Durable post-Access binding contract

The first factory source built on 2026-11-23 at public commit `b6154dae...` intentionally generated `FACTORY_ACCESS_AUD:""` and `FACTORY_ALLOWED_EMAILS:""` plain variables, correctly denying owner API access. After Cloudflare Access has been applied **All traffic**, those values MUST be provisioned once as **Cloudflare per-Worker secrets** and never copied into the public repository or GitHub Actions. The generator now deliberately omits these two keys from Wrangler `vars`, while keeping every `*_ENABLED` flag pinned to `0` and `FACTORY_PROPOSAL_ONLY` at `1`. Cloudflare confirms encrypted secrets survive code deployments, while declared plain `vars` would be overwritten. Existing deployed empty vars must be converted rather than duplicated.

**Important:** The Worker policy initially created as `Cloudflare account members` is account-member scoped, not necessarily an exact owner email. Before binding privileged administrator tokens, make an application-specific policy with `Include Cloudflare Account Member` AND `Require exact verified owner email`, or replace it with an equivalent exact-owner only Allow. Check `Access > Applications` to avoid accidentally broadening a shared policy. Do not use email-domain, Everyone or Bypass. Verify anonymous denial, owner login and mismatched identity rejection.

The owner's supplied string `aud-92ab3c2198104cea377953f65c7858c7de9e2a2c08e3b90442b1bcb8bb054706` is a **user-reported label/tag**, not yet an authenticated API read. The suffix is exactly 64 hex chars, a typical AUD shape. Do not silently trim the `aud-` prefix: use exactly what the Access app lists as **Application Audience (AUD) Tag**. Cloudflare runtime `ctx.access.aud` must compare byte-for-byte to the secret value.

## One-time initial install (owner authorization)

1. Confirm **new account ID** and display name `CC Ordinary Deployments` in the Cloudflare account switcher and record the immutable ID in CommandCenter. The SlenderIQ token `CC SlenderIQ Factory Provisioner TEMP R1` is account-scoped and **cannot operate on this account**.
2. Use a **new-account authorized Cloudflare owner OAuth session** for the initial `wrangler deploy --config cloudflare/isolated-ordinary-factory/.generated/wrangler.jsonc`. The new factory is `cc-ordinary-worker-factory`; its Durable Object `FACTORY_LEDGER` is SQLite; all execution and mutation switches start at zero; no privileged secrets are bound. The initial deploy may create a new Worker but **not any ordinary project Worker**.
3. Immediately protect the **factory Worker** with Cloudflare Access for **All traffic** and **owner-only** policy. Convert/create `FACTORY_ACCESS_AUD` and `FACTORY_ALLOWED_EMAILS` as **per-Worker encrypted Cloudflare secrets** via the dashboard **after verifying the exact AUD tag in Zero Trust > Access > Applications > application settings**. The current deployed v5aab4b02 has **blank plain variables** at these names. Dashboard edits may create a new live version, so inspect the exact resulting version and settings. Future generated source intentionally OMITS these vars and does not overwrite the Cloudflare-stored secret values; never deploy the old generator with blank Access vars again. The owner's provided tag was `aud-` followed by 64 hex characters: do NOT guess whether `aud-` is part of the actual AUD until comparing with the official Access app's AUD field. Verify unauthorized denial and owner `/v1/status` before enabling any executor flag. Never assume an existing SlenderIQ Access policy is available in the new account.
4. Create **one account-owned new-account only** Workers **product Admin** token, named `CC Ordinary Deployments Factory Admin R1`, with no other product permissions. Bind its bearer to `FACTORY_WORKERS_ADMIN` as a **Cloudflare per-Worker encrypted secret** (source accepts string secrets or Secrets Store handles). Do NOT put it in GitHub Actions, source code, chat, public results or Library. This key can manage ordinary Workers in **this one isolated account only**. No extra Secrets Store/R2/KV subscription is required for the minimal bootstrap.
5. Enable only `FACTORY_EXECUTOR_ENABLED=1` and `FACTORY_CREATE_ENABLED=1` **after** Access, exact deployment identity, account pin, credential isolation and the DO ledger are verified. Leave `FACTORY_SCOPED_TOKEN_ENABLED=0`, `FACTORY_STAGE_VERSION_ENABLED=0`, machine flags `0` until their independent receipts. The reviewed source's owner `/v1/execute` is **disabled by default**, because `FACTORY_PROPOSAL_ONLY=1`; owner-approved **private GitHub queue** requires its independently scoped `FACTORY_QUEUE_GITHUB_TOKEN` Cloudflare secret and a reviewed proposal from `CommandCenter-gate-control`. Do not disable proposal-only without explicit protected owner review.
6. Execute scratch A/B creation, exact identity readback, identical request replay denial, protected-target rejection, and only then off-traffic SHA256-pinned source stage. Do not attach a production route or promote traffic on scratch tests.

## Permanent no-Mac publisher: separate acceptance

The isolated new-account factory solves *ordinary Worker creation*. It does **not** grant the right to touch existing original SlenderIQ, neutral signers, protected websites, or the Studio Worker. For a truly no-Mac general publisher, the next separately admitted release operation needs:

- New-account machine caller protected by Access and validated GitHub OIDC, plus CommandCenter **project-specific typed authorization**, short TTL, one-use DO request identity and immutable proposal/receipt. The current public workflow's OIDC source only authorizes **read**, and must not be treated as a write grant.
- New-account ordinary releases: pinned source/asset hashes, existing Worker immutable ID, Cloudflare per-account secret, off-traffic version, readback, owner-approved traffic promotion, rollback.
- Existing Worker deployment across other accounts uses **different** account-bound publisher credentials; no cross-account admin. The existing original SlenderIQ and neutral Account IDs must be rejected by the isolated factory.
- Neutral Studio needs its separate existing-Worker Editor/Access binding and exact asset-hash promotion. It remains in Shared Compute Neutral, not the new ordinary account.
- Repeat A/B and two ordinary release examples with **zero new dashboard setup or Mac invocation** after the account's one-time trust bootstrap. Do not advertise permanent no-Mac publisher until this has a working live receipt.

## Security and cost

Do not enable Cloudflare Builds for this privileged factory: a continuously regenerating build credential and unreviewed source changes are not an approved administration boundary. No private GitHub Actions compute. Public workflow runs here are **offline source tests only**; they never receive Cloudflare account tokens.

Keep `CC SlenderIQ Factory Provisioner TEMP R1` unchanged until the user approves SlenderIQ-side retirement. It expires 2026-11-30; the new account needs its own authority and keeping the old token does not provide a credential fallback for the new account.
