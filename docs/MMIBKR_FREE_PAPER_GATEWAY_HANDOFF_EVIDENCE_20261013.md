# MM-IBKR free paper Gateway handoff — boundary evidence (2026-10-13)

**Execution authority:** independent MM-IBKR lane, not a fleet role. No Cloudflare Containers purchase, no live/paper broker orders, no new API token, no new service account. GitHub clock-in: [issue #842](https://github.com/XoticHaze/mm-IBKR/issues/842#issuecomment-6143828238) at `2026-10-13T10:44:42Z`.

## Results: separate facts, not interchangeable

| Evidence | Stage | Conclusion |
| --- | --- | --- |
| [Push #38386066177](https://github.com/XoticHaze/research-compute-public-/actions/runs/38386066177) | 15 unit tests, pinned gnzsnz IB Gateway+IBC image inspection, synthetic predecessor release, checkpoint save, second GitHub job exact restore and safety gate | **PASS**; no broker process/login |
| [PR #38386107432](https://github.com/XoticHaze/research-compute-public-/actions/runs/38386107432) | Same two-job regression on PR merge test head | **PASS** |
| [October 12 live admission #38322428844](https://github.com/XoticHaze/research-compute-public-/actions/runs/38322428844) | One fresh GitHub runner obtained sealed production-live Gateway environment, started existing IBKR controller and independently read expected account, positions and open orders without an order | **PASS** for one-run login/read, not cross-runner auth |
| Existing selected-runtime cloud owner | 355-minute GitHub job bound, `session_seconds` up to 18000, checkpoint cache and successor handoff | Free finite compute state/strategy handoff exists; NOT authenticated Gateway migration |
| Existing production-live owner | Per-run Docker volume `mmibkr-live-jts-$GITHUB_RUN_ID` removed by cleanup | No durable Jts/2FA handoff across runners established |

## Contract tested in this PR

- Synthetic test source only (`synthetic_only=true`, `account_mode=paper`, `read_only_api=true`).
- Separate GitHub runner jobs: predecessor writes a fixed synthetic checkpoint and exact source/run-bound release receipt; successor restores via GitHub cache and validates content hash and source/run/job identity.
- Reject altered checkpoint, unknown credential or account fields, stale source/run, duplicate predecessor/successor job identity, unreleased predecessor, active predecessor Gateway/owner, or order/broker-login claims.
- Successor explicitly reports `gateway_authentication_transfer_proven=false`, `jts_transfer_proven=false`, `ibc_reauthentication_requirement=UNTESTED`, `execution_ownership_granted=false`, `production_handoff_ready=false`.
- Canonical B1 immutable `ghcr.io/code-hustler-ft3d/ibg-controller@sha256:5db4074ec952d130937afc3bb926ee97f115d09f7f46676eb16d98c2805572b5` is pulled and inspected with `--network none` and a shell entrypoint, **not** logged in or started as Gateway.
- No private source, Jts files, broker credentials, account ID, positions, or order data are included in GitHub cache. Even synthetic test output cannot grant live execution.

## Next empirical proof: real paper-only Gateway authentication on a successor VM

This remains **NOT EXECUTED** in the present PR. A real test must use the established sealed paper credential authority and an approved exact GitHub OIDC workflow identity; a new workflow must not assume it can unwrap paper credentials. The existing paper authority is not automatically accessible to this probe.

**Exact authority evidence:** `cloudflare/fleet-authority/src/index.js` limits `ibkr-paper/seal` to `refs/heads/ibkr-b1-authority-v1` with workflow ref `XoticHaze/research-compute-public-/.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml@refs/heads/ibkr-b1-authority-v1`; the new PR branch cannot request sealed paper login credentials. Testing actual paper 2FA succession therefore requires a reviewed extension of this *specific* existing B1 surface or an independently authorized paper test identity—not an OIDC bypass, blanket shared secret, or surprise login.

1. Verify unique paper DU username and absence of other active sessions or competing jobs. Reuse the existing IBC / ib-gateway image authority. Start read-only paper Gateway on predecessor with protected account credentials *only inside the authorized existing private-input boundary*; require managed DU account and read positions / open orders, no order mutations.
2. Produce sanitized broker session state metadata, including authenticated/no-2FA status, account type (not number), control-plane generation, checkpoint digest, and opaque broker-order reconciliation fingerprint. Never place Jts authentication files or bearer material in public Actions artifacts/cache/logs.
3. Prepare successor source, container, strategy state and cryptographic checkpoint in parallel, but **do not authenticate the same broker username on two machines simultaneously**. Fenced release of predecessor comes first.
4. On successor VM, start read-only paper Gateway+IBC with one-run sealed credentials. Independently classify `AUTH_REUSED_WITHOUT_INTERACTION`, `NEW_2FA_REQUIRED`, `AUTH_FAILED` or `UNKNOWN`, based on real account readback. Do not equate process readiness or prior cached Jts bytes with broker authentication.
5. Compare read-only positions, open orders/executions and account contract before any execution ownership. If stale/unknown/2FA, fail closed and leave execution disabled. Measure handoff downtime and repeated trials near session boundary.
6. Only after real session succession is proven and GitHub Actions usage conditions are assessed, decide whether a free always-on broker alternative is needed. Cloudflare Paid Containers are not needed for the present tests.

**Explicit limitations:** This PR proves only free GitHub VM-to-VM *synthetic checkpoint and ownership fencing*. It does **not** prove paper IBC login across a VM change, weekly 2FA reuse, true 5-hour real broker continuity, or eligibility to use GitHub Actions as a production broker host. Leave live orders off.
