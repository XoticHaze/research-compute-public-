# CCPI neutral Cloudflare owner signer: one-time dashboard deployment (no Mac command)

**Target:** independently administered **Shared Compute Neutral Authorization** account `b33595eb85f346b0d1bf201810b4499a`. **Not** the original SlenderIQ account, `ce43cd7b917d98a4bb4866d30eed99c0`.

**Security classification:** initial **inert** Worker source bootstrap only. This is NOT owner consent for Ed25519 issuance, a Pi root trust enrollment, a `pi.release.apply` install, or a generic neutral Worker deployment API. Protected root enrollment/activation are separately gated.

## Source identity and standalone package

- Public source repository: `XoticHaze/research-compute-public-`.
- Dedicated one-time branch: `release/ccpi-neutral-owner-firstseal-20261114`. **Pin/record its exact head SHA in the Cloudflare deployment receipt before enabling any signing.**
- Original reviewed common source: commit `eb8085ca0397ffb28af597e003b22fa44baf0fff` from PR #2150.
- Cloudflare Builds **root directory:** `cloudflare/pi-owner-authority` (relative to Git repo root).
- Deploy command: `npm run deploy`. No build command is required.
- The package intentionally includes a **local copy of the existing unchanged, content-addressed owner signer module**, so standalone Builds does not depend on files outside this root directory. Its Git blob is `f6de8813cb8f8b022ff475465e065653b98558f8`. The entrypoint changes only relative import paths from the parent project's module to this identical local copy.
- Wrangler pin: `4.131.2`; config `wrangler.jsonc` targets script `ccpi-owner-cloudflare-authority` with SQLite Durable Object class `PiOwnerApprovalState`.
- Do **not** connect this Worker to any GitHub Actions workflow, original-account factory token, user-supplied deploy token, or the existing broker-only Editor token.

## Independent Cloudflare account owner action (web UI, no Mac / SSH / Node)

1. In your **neutral-account Cloudflare dashboard**, verify the selected account ID matches `b33595eb85f346b0d1bf201810b4499a`. First check whether `ccpi-owner-cloudflare-authority` already exists. If it does, inspect its live source/version and binding; do not overwrite an unknown active signer.
2. Create a new Worker from a GitHub repository in **Workers & Pages**, using `XoticHaze/research-compute-public-`. Set the **production branch** to `release/ccpi-neutral-owner-firstseal-20261114`, root directory `cloudflare/pi-owner-authority`, deploy command `npm run deploy`, preview builds **disabled**. The Worker name must match `ccpi-owner-cloudflare-authority` exactly. Review any auto-generated build API token and the scope before accepting. Do not copy a neutral-admin API token into GitHub secrets or CI.
3. Verify the resulting Worker version, source identity and `PI_OWNER_APPROVER` SQLite DO binding in the **neutral** account. The script has **no initial activation flags**; every protected route requires authenticated Cloudflare Access, and no Ed25519 key should exist or be issued at this stage.
4. **Immediately disconnect the Git repository** in Worker **Settings > Builds > Disconnect**, and read back that no repository is connected, no previews or unattended build deployments remain. Independently audit any automatically created Builds API token, retaining/restricting/revoking only as allowed by the owning-neutral-account policy. **Do not initialize or enroll a signing key until GitHub can no longer redeploy this Worker and the active version is independently checked.**
5. Next configure a **direct** Cloudflare Access application for the exact Worker hostname in the same neutral account, enforce exact approved owner identity, and set `PI_OWNER_ACCESS_AUD` to the actual Access application AUD and `PI_OWNER_SIGNER_ALLOWED_EMAILS` to that reviewed owner email. Access must protect all production routes; no public `/api/status` exception.
6. Keep all flags `PI_OWNER_SIGNER_ENABLED=0`, `PI_OWNER_FIRST_ISSUE_ENABLED=0`, `PI_OWNER_FIRST_ENROLL_ENABLED=0`, `PI_OWNER_NORMAL_RELEASE_ENABLED=0` until their own protected first-use approvals. **Do not** set a GitHub queue token unless its read/write scope has been independently verified. No `PI_OWNER_INIT_CODE_SHA256`, key, or private secret should be committed or displayed in logs.
7. Share a **sanitized** neutral-account Worker name, active version and disconnected-Builds readback with CC. Do not send credentials, activation codes or signer private state. CC can independently reconcile subsequent Pi public-key enrollment and the same-ID signed release receipt.

**Security caution:** connecting a Git repo to Cloudflare Builds temporarily delegates deployment authority to that repository/Builds integration. It is acceptable *only before the new signer exists*, and must be revoked/verified before key initialization. If the neutral administrator cannot prove disconnection and isolation, **stop**, keep the signer disabled, and use an independently authorized narrow admin deployment path instead.

**Documented UI mechanism:** Cloudflare Workers Builds allows Git branch, root directory and deploy command customization; it documents `Settings > Builds > Disconnect` for removing repository connection. Refer to:
- https://developers.cloudflare.com/workers/ci-cd/builds/
- https://developers.cloudflare.com/workers/ci-cd/builds/configuration/
- https://developers.cloudflare.com/workers/ci-cd/builds/build-branches/

## Remaining Pi protected acceptance

The canonical Pi root verifier source is merged in `XoticHaze/CommandCenter` at `617f01b34751bc73f1de0fc60e4c3b3451259f42`. Its immutable 39-file artifact is already published at `XoticHaze/CommandCenter-gate-control` `pi-node-release-artifacts` commit `615dca6b6acdedf40cd58caa1989c09261e2cbf3`, path `pi-node/artifacts/ccpi-update-617f01b34751`.

Fresh Pi read-only root status `mw-20261114114726797-cloudflare-root-gates-readonly` completed 2026-11-14T11:56:32Z and independently reports `owner_device_public_key_root_owned_pem_header_present=false`. The first root-owned verification key seal and protected root-worker install therefore remain separately admitted operations. A future **normal** release must bind exact request/source/predecessor/TTL to Cloudflare-owner Ed25519 signing, then verify a new Pi root generation with same-ID `passed` outbox. No root release, Gateway restart, order or live setting change is authorized by this handoff.
