# MM-IBKR free paper Gateway handoff — boundary evidence (2026-10-13)

**Execution authority:** independent MM-IBKR lane, not a fleet role. No Cloudflare Containers purchase, no live/paper broker orders, no new API token, no new service account. GitHub clock-in: [issue #842](https://github.com/XoticHaze/mm-IBKR/issues/842#issuecomment-6143828238) at `2026-10-13T10:44:42Z`.

## Results: separate facts, not interchangeable

| Evidence | Stage | Conclusion |
| --- | --- | --- |
| [Push #38386066177](https://github.com/XoticHaze/research-compute-public-/actions/runs/38386066177) | 15 unit tests, pinned Gateway controller image inspection, synthetic predecessor release, checkpoint save, second GitHub job exact restore and safety gate | **PASS**; no broker process/login |
| [PR #38386107432](https://github.com/XoticHaze/research-compute-public-/actions/runs/38386107432) | Same two-job regression on PR merge test head | **PASS** |
| [Real paper warm handoff A #38386762807](https://github.com/XoticHaze/research-compute-public-/actions/runs/38386762807) | Fresh public GitHub runner; sealed paper credential via approved B1 OIDC; restored encrypted clean-stop-v2 warm state, canonical IBG controller; authenticated API and readable account summary; `IBKR_WARM_SESSION_REUSED=1`, mobile challenge `0`, operator action `NONE`; graceful stop and warm-state reseal | **PASS** |
| [Real paper warm handoff B #38387209651](https://github.com/XoticHaze/research-compute-public-/actions/runs/38387209651) | Another fresh runner, started only after A stopped and saved encrypted warm state; same restored session, authenticated API/readable summary, no mobile challenge/operator action; resealed successor artifact and cleaned private material | **PASS**, repeatable (two samples) |
| [Canonical B1 artifact provenance hardening](https://github.com/XoticHaze/research-compute-public-/commit/6f5daa97b65303dbf84587ea3a363f217a146954) | New read-only metadata check requires artifact source run ID, exact B1 branch and SHA, nonself predecessor and emits sanitized artifact lineage before decryption | **Implemented**, awaiting own first broker-authenticated exercise |
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

## Real paper authorization and remaining five-hour experiment

**Real paper Gateway warm-session reuse is now proven twice**, separately from the synthetic handoff PR. The new PR branch did **not** gain sealed paper credentials: both real checks used the existing OIDC-authorized `ibkr-b1-authority-v1` workflow. Each run's sealed Gateway environment was ephemeral, and account reads—not process startup—established actual authentication. No 2FA prompt was required in either run.

**Exact B1 authority:** `cloudflare/fleet-authority/src/index.js` binds `ibkr-paper/seal` to `refs/heads/ibkr-b1-authority-v1` and the exact workflow ref `XoticHaze/research-compute-public-/.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml@refs/heads/ibkr-b1-authority-v1`. Keep this allowlist unchanged. Source branch changes for A/B used the established explicit `[ibkr-login]` trigger with no paper mutation modes enabled.

**Remaining independent gates for a continuous five-hour strategy owner:**

1. Prove the canonical StrategySpec / selected runtime five-hour process checkpoints include strategy state, market data, and next-signal ownership identity. Preserve distinct broker-session state from strategy-state artifacts.
2. Prior to expiration, prepare a successor compute window while the predecessor alone owns the broker username. Require durable state/position/open-order lineage and an exclusive release fence before successor paper login. No concurrent authenticated IBKR sessions.
3. Reuse the existing B1 controller-native warm state and sealed one-run credentials. Require fresh successor read-only account summary, positions, open orders and execution reconciliation; source artifact run ID plus cryptographic digest must match the predecessor. The new metadata lineage check must be exercised on a future approved B1 run.
4. Measure from predecessor disarm to successor authoritative read, evaluate 2FA and session-reset behavior over longer multi-hour / weekly windows, and refuse order execution on gaps, unresolved order IDs or uncertain account state.
5. Keep GitHub Actions use bounded and compliant: the free five-hour compute window is not an entitlement to an unsupported perpetual production brokerage host. Evaluate this separately from demonstrated technical handoff.

**Security review still required before production:** B1 `ibkr-b1-warm-state-clean-v2` artifacts are AES-GCM encrypted with a 250,000-iteration PBKDF2 key derived from the paper password. Confidentiality therefore depends on password entropy against offline guessing; public artifact transport, retention, KDF and a stronger per-run envelope key must be reviewed before treating this as fully hardened live credential storage. This test did not publish plaintext credentials/account details, but two successful decrypts are not themselves a public-publication privacy audit.

**Explicit limits:** Two real paper read-only Gateway restorations on separate fresh hosted runners **passed**, along with one independent synthetic checkpoint/fencing pair. A full 5-hour continuous production broker process, live-order singleton authority, reconciled open-order migration, Sunday/weekly manual reset resilience, and GitHub Actions production suitability are **not yet proven**. No live orders.
