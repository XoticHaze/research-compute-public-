# MM-IBKR GitHub-only authenticated Gateway pool

**Date:** 2026-10-21. **Goal:** prove authenticated IB Gateway socket-client continuity across entirely independent GitHub-hosted compute jobs **before any VM deployment**. This does NOT constitute always-on trading and cannot exceed hosted job lifetime.

## Proven basis and mode

Existing sanctioned production-live owner:
`.github/workflows/mmibkr-selected-runtime-live-owner-r1.yml`.
Already-proven four-hour live owner: [run 39499524894](https://github.com/XoticHaze/research-compute-public-/actions/runs/39499524894). That run started Gateway **and** bot on one GitHub runner; it did not prove remote client reuse.

New **explicit manual-only** mode:
`admission_only=true, warm_handoff_mode=gateway_pool_5h`.

This keeps only one IB Gateway/controller online for approximately **4 hours 40 minutes** after startup, on the existing authorized GitHub owner. It requests the existing Fleet Authority sealed production-live credentials from the pre-existing allowed workflow identity, reads and binds the expected account before exposing the API to a tailnet-only listener, sets `READ_ONLY_API=yes` to disable broker API mutations, and **never starts the canonical bot**. Gateway/controller session health is checked with real broker account/positions/orders/executions reads, not merely TCP/JVM reachability.

At normal end the existing workflow gracefully stops Gateway, seals its settings/Jts warm state using the existing independent key and uploads its encrypted checkpoint before deleting credentials. GitHub-hosted jobs have a hard **six-hour** limit; this experiment does not make a permanently authenticated machine.

## One-time GitHub-to-GitHub private networking

Independent GitHub-hosted VMs are isolated; localhost socket 4001 on one runner does NOT appear on another. We use ephemeral Tailscale nodes authenticated by GitHub Actions federation. Official docs: https://tailscale.com/docs/integrations/github/github-action .

**Operator-provisioned Tailscale tailnet:** Create 2 different federated OIDC trust credentials, each with `auth_keys` scope and the exact authorized tag:
- Gateway: `tag:mmibkr-gateway` with GitHub secrets `MMIBKR_TS_GATEWAY_OIDC_CLIENT_ID` and `MMIBKR_TS_GATEWAY_OIDC_AUDIENCE`.
- Independent readers: `tag:mmibkr-reader` with GitHub secrets `MMIBKR_TS_READER_OIDC_CLIENT_ID` and `MMIBKR_TS_READER_OIDC_AUDIENCE`.
- Configure tailnet access policy to allow **ONLY** `tag:mmibkr-reader` to `tag:mmibkr-gateway:4001`, and **no** reader to other Gateway ports or nodes unless separately required. Example *access grant*, add into an already-reviewed Tailnet policy rather than overwriting unrelated rules:

```json
{
  "grants": [
    { "src": ["tag:mmibkr-reader"], "dst": ["tag:mmibkr-gateway"], "ip": ["tcp:4001"] }
  ]
}
```

Define `tagOwners` and federated identity claim limits separately. Enable MagicDNS resolution for ephemeral `mmibkr-gw-<run_id>` node names. GitHub's `id-token:write` permission is already present for the approved owner and new independent readers. The Tailscale Action is pinned to v4 commit `d1b6cd204f8dceda5b3eaad7f1f767be390056cd`; nodes are ephemeral and leave the tailnet after their job finishes.

Additionally provision `MMIBKR_PRODUCTION_LIVE_ACCOUNT` as a GitHub encrypted secret in the public compute repo for the **read-only reader** workflow, containing the exact live account expected by the current canonical owner. Never print this value. The Gateway-owner workflow itself continues deriving its expected account through existing Fleet Authority sealed data and does NOT need this new secret.

Optional encrypted repo secret `MMIBKR_READONLY_EXACT_CONTRACTS_JSON` is a JSON array of **reviewed, exact conId-based STK/FUT/OPT descriptors**. Sample *structural placeholders*, not real contract identities:

```json
[
  {"symbol":"EXAMPLE","secType":"STK","conId":123456},
  {"symbol":"FUTEXAMPLE","secType":"FUT","conId":234567,"lastTradeDateOrContractMonth":"20261218"},
  {"symbol":"OPTEXAMPLE","secType":"OPT","conId":345678,"lastTradeDateOrContractMonth":"20261120","right":"C","strike":100.0,"multiplier":"100"}
]
```

**Never submit these placeholders.** Use real exact current source-selected dated MNQ contract, actual equity conIds, and an explicitly selected option descriptor if option qualification is desired. A missing option is **NOT_CONFIGURED**, not implied PASS. The reader calls `reqContractDetails`, not `placeOrder` or `whatIfOrder`. Qualifying a contract does not prove a live order would be accepted.

## GitHub-only staged run

1. First merge the source-reviewed public PR after CI passes. Do **not** switch the private MM canonical live bot to split mode. Ensure no other authenticated Gateway uses the intended live account.
2. Open [Canonical Production Live Owner Actions](https://github.com/XoticHaze/research-compute-public-/actions/workflows/mmibkr-selected-runtime-live-owner-r1.yml) and use **Run workflow** on `main`: `admission_only=true`, `warm_handoff_mode=gateway_pool_5h`, empty `warm_predecessor_run`. Attend one IB Key approval if IBKR prompts. Do not repeatedly dispatch it on challenge delays.
3. In that run's `owner` job wait for `MMIBKR_GATEWAY_ONLY_POOL_READY=1`. The exact run ID is the label `mmibkr-gw-<run_id>`. The Gateway runs as an API read-only session for another ~4h40.
4. At any time during the pool, open [Independent GitHub Gateway Readers](https://github.com/XoticHaze/research-compute-public-/actions/workflows/mmibkr-gh-independent-readers-r1.yml) on `main`, input **exact running Gateway run ID** and select **`handoff_ab`**. A preflight verifies the old Gateway owner's workflow path, active run, expected hold step, then starts **two separate GitHub VMs** A and B with separately tagged read-only Tailscale peers and distinct broker client IDs. A remains connected, B overlaps and later re-reads the same live broker account after A disconnects. For subsequent lightweight controls, select **`single_read`** on the same workflow: this launches just one fresh independent GitHub worker that can optionally qualify the exact instrument descriptors and exits without disturbing the authenticated Gateway.
5. Check reader artifacts `mmibkr-gateway-client-a` and `mmibkr-gateway-client-b`. Require two real broker account/positions/all-open-orders/executions reads; exact expected account; A/B different client IDs; chronological overlap; A disconnect before B second read; zero broker mutations; no new IB Key prompt corroborated **separately** by original Gateway/controller logs and the user's phone. If anything fails, classify exact stage; do not run surprise extra logins or orders. Gateway holder remains alive regardless of reader job success.
6. During the remaining authenticated window, more independent reader workflows can be invoked without another Gateway login. Separate no-order *source* gates for futures roll, STK/OPT exact selection, session, quote, exposure/margin and idempotency can be tested with synthetic/broker-read inputs; do not claim contract lookup equals a broker-submitted order acceptance. `whatIfOrder` can be separately reviewed if explicitly desired, but is not used by this A/B workflow.

## Boundaries

- This GitHub-only plan does **not** require Oracle, Google Cloud, paid VPS, home host, router port-forwarding or Cloudflare Containers.
- An ephemeral GitHub holder runner is **not** an indefinite credential host; at 4h40+ cleanup the authenticated Gateway exits by design. Moving that exact container/network recipe to a persistent compute host later is a placement change, not a StrategySpec rewrite.
- Holder's broker `READ_ONLY_API=yes` is real API-level mutation protection. Worker `readonly=True` and unique client IDs are helpful but *not* security authorization alone; tailnet ACLs and the holder's API read-only mode are essential.
- Both reader and Gateway profile outputs contain broker/strategy **evidence only**, not new trade authority. Original single-writer fences and canonical `main.py` submit/flatten/cancel remain untouched.
- PR/CI by itself cannot show IBKR connected or prove no 2FA prompt. The live Gateway experiment is **not run** until the operator provisions tailnet credentials and starts a manual dispatch.
