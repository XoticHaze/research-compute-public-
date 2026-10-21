# MM-IBKR: Cloudflare Access SSH bridge — GitHub-to-GitHub first

**Prepared 2026-10-21. No IBKR login, live order, new VM or Cloudflare account mutation was made by this source change.**

This uses the **existing Cloudflare provider**, without managed Tailscale. A dedicated **Cloudflare Tunnel + Access Service Auth** protects a GitHub-hosted, temporary SSH origin. The broker socket remains localhost-only. OpenSSH authenticates a separately pinned host key and client key; its server is restricted to forwarding **exactly 127.0.0.1:4001**, with no password, shell, TTY or unrestricted forwarding. Both Cloudflare and SSH credentials are required. Broker read-only mode is still independently enforced by IB Gateway.

The existing production-owner workflow remains the **only** Fleet-authorized live credential consumer. Network configuration is checked *before* it requests private source/Gateway credentials. Provider selector `pool_transport` keeps the previously proven Tailscale implementation available as a fallback; default for the new proof is `cloudflare_access_ssh`.

## One-time Cloudflare configuration (operator-held)

1. In the existing Cloudflare account, create a **dedicated remotely managed Tunnel**, not a second Fleet Authority/Worker and not a generic Quick Tunnel. Configure a **published SSH route** on a hostname that belongs to an already Cloudflare-managed domain: `<chosen-subdomain>.<your-managed-zone>` → `ssh://localhost:2222`. A `*.workers.dev` Worker route is **not** a substitute for a managed-zone Access SSH app. Set that hostname as repo **variable** `MMIBKR_CF_SSH_HOSTNAME`.
2. Create a **Cloudflare Access self-hosted application** for that exact hostname, and require a **Service Auth** policy admitting only the dedicated GitHub-reader service token. No Bypass policy, no unauthenticated application route. Record the dedicated service token Client ID/Secret as GitHub **secrets** below. Access protects the edge, and SSH protects the forwarded payload end-to-end. If headless service-token authentication fails in a specific `cloudflared` release, fail closed and classify as transport; don't remove Access or pinning to work around it.
3. Save the dedicated **Tunnel token** (not a Cloudflare API key) into public compute repo GitHub Actions secret `MMIBKR_CF_GATEWAY_TUNNEL_TOKEN`. This allows the runner to attach as a tunnel connector only; it must not have rights to mutate unrelated Cloudflare applications or DNS. Keep the route bound to the dedicated application, not the user-facing command center.
4. Generate **two independent Ed25519 SSH key pairs** on trusted operator equipment, locally using `ssh-keygen -t ed25519`, one as the *Gateway SSH host key* and one as the *restricted reader user key*. Don't paste any private key or token into the chat or issues. Store host/reader private key PEM text encoded with Base64 strictly in GitHub Actions secrets, and the corresponding public SSH key text as specified below. Rotate/revoke when promoting persistent infrastructure.
5. Restrict this configuration to the explicit approved production live-owner workflow's **read-only** pool mode. No new order authority, account replacement, or trading mode changes.

| GitHub Actions setting | Type | Value |
|---|---|---|
| `MMIBKR_CF_SSH_HOSTNAME` | repo variable | Exact protected DNS name from Cloudflare Tunnel/Access |
| `MMIBKR_CF_GATEWAY_TUNNEL_TOKEN` | secret | Dedicated remotely managed Tunnel connector token |
| `MMIBKR_CF_GATEWAY_SSH_HOST_KEY_B64` | secret | Base64 contents of Gateway SSH private host key |
| `MMIBKR_CF_GATEWAY_SSH_HOST_PUBKEY` | secret | SSH host Ed25519 public key, no hostname prefix |
| `MMIBKR_CF_READER_SSH_PRIVKEY_B64` | secret | Base64 contents of restricted SSH reader private key |
| `MMIBKR_CF_READER_SSH_PUBKEY` | secret | Restricted reader Ed25519 public key |
| `MMIBKR_CF_ACCESS_SERVICE_TOKEN_ID` | secret | Dedicated Access Client ID |
| `MMIBKR_CF_ACCESS_SERVICE_TOKEN_SECRET` | secret | Dedicated Access Client Secret |
| `MMIBKR_PRODUCTION_LIVE_ACCOUNT` | secret | Existing exact expected live account, **only required for actual broker-read reader workflow**, not synthetic rehearsal |

Do not add these as public repository variables or commit them. Cloudflared binary is pinned to `2026.10.0` and checked against SHA-256 `d33ff2d14475178d2012c2c56beba87389ac5ded27649519f198a7d3134a99db` on all GitHub runners.

## First run: prove Cloudflare SSH transport **with NO IBKR**

1. [MM-IBKR Cloudflare SSH Network-Only Rehearsal](../.github/workflows/mmibkr-cf-ssh-network-rehearsal-r1.yml) → Actions → **Run workflow** on `main`.
2. This starts a dedicated outbound tunnel and a restricted SSH server on **one** GitHub runner, but exposes only a harmless local TCP echo fixture on 127.0.0.1:4001. No broker credentials are materialized and no Gateway process starts.
3. Two **separate** GitHub runner jobs authenticate against the Cloudflare Access service token, verify the pinned Gateway SSH key, establish their own local 127.0.0.1:14001 forward and send/verify distinct nonce echoes. Both must pass.
4. If Access redirects to a browser, Cloudflare Tunnel DNS or Access permission fails, hostname pinning mismatches, or either job cannot forward, do **not** proceed to IBKR. Investigate the exact stage and the reported failure without weakening authentication.
5. Stop using the synthetic test once the evidence is accepted. This is not a claim of API or trading continuity.

## Second run: same network, real Gateway still on GitHub

1. Ensure no other live authenticated Gateway owner conflicts. Open [Canonical Production Live Owner workflow](https://github.com/XoticHaze/research-compute-public-/actions/workflows/mmibkr-selected-runtime-live-owner-r1.yml), manually select `admission_only=true`, `warm_handoff_mode=gateway_pool_5h`, `pool_transport=cloudflare_access_ssh`, and blank predecessor. This owner is the existing Fleet-authorized credential workflow. It starts IB Gateway with **READ_ONLY_API=yes** and **does not start the canonical trading bot**. Attend one IB Key prompt if it appears.
2. Verify its `MMIBKR_GATEWAY_ONLY_POOL_READY=1` heartbeat and exact run ID. The account, positions, open orders and executions are polled during the 4h40 bounded holder lifetime. The network uses the **same dedicated Cloudflare Access SSH route** already proven with synthetic nonce.
3. Open [Independent GitHub Gateway Readers workflow](https://github.com/XoticHaze/research-compute-public-/actions/workflows/mmibkr-gh-independent-readers-r1.yml), enter **the exact active Gateway-owner run ID**, select `network_transport=cloudflare_access_ssh`, `test_mode=handoff_ab`; first independent runner attaches to the same Gateway, B overlaps and re-reads after A disconnects. **Neither reader logs into IBKR.**
4. For later separate work against that same authenticated Gateway, choose `test_mode=single_read`, or run other independent no-order source/contract test jobs. Exact `MMIBKR_READONLY_EXACT_CONTRACTS_JSON` (optional secret) may include real selected STK/datestamped FUT/fully-specified OPT descriptors to ask IBKR for `reqContractDetails` but cannot auto-pick an option, roll a future, place/cancel an order, or prove every downstream submit gate.
5. Confirm absence of additional IB Key approvals from controller telemetry and operator phone separately. GitHub A/B receipts don't independently prove the Gateway process identity or phone notification state. GitHub runner lifetime limits prevent a permanent session.

If Access WebSocket transport proves unreliable for long-lived broker client connections, keep **Cloudflare/Fleet** for control/credentials but migrate the private endpoint to **self-managed WireGuard on the persistent VM**, without changing canonical strategy code or A/B probe semantics. Managed Tailscale stays opt-in fallback, not an accepted production networking dependency.

## Invariants

No public broker TCP listener. No Cloudflare quick tunnel without Access. No `StrictHostKeyChecking=no`. No unverified/dynamically scanned SSH host key. SSH reader account is restricted to local forwarding of broker port 4001 and never grants shell access. Gateway's `READ_ONLY_API=yes` blocks broker order submission. An isolated GitHub job’s `clientId` does not constitute order authorization. Reuse canonical single-writer owner fencing before later mutating split trading runtime. Keep zero IBKR login attempts until the network-only rehearsal is green and the attended operator is present.

See [Cloudflare client-side SSH](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/use-cases/ssh/ssh-cloudflared-authentication/) and [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/).
