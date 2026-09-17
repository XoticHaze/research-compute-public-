# IBKR Warm Reuse Acceptance - 2026-09-17

## Accepted authority run

- Repository: `XoticHaze/research-compute-public-`
- Branch: `ibkr-b1-authority-v1`
- Head: `28a833aecbf048e496e045fe4bdae1e797545f96`
- Workflow run: `35202149589`
- Broker job: `105139288010`
- Validation runner: `1000014699`
- Broker runner: `1000014700`
- Broker job conclusion: `success`

This was a fresh GitHub-hosted broker runner and used the stable admitted GitHub OIDC workload identity. Fleet Authority trust was not broadened.

## Root cause closed

The clean warm artifact must not be restored directly into the live `TWS_SETTINGS_PATH`. The pinned `ibg-controller` expects a separate `GATEWAY_WARM_STATE` seed which `apply_warm_state()` copies into the live JTS config directory before launch.

The restored seed must also be owned/readable by the controller image runtime identity. The pinned image runs as a non-root user, so extraction as root followed by owner-only permissions made a correctly mounted seed unreadable. The accepted workflow now:

1. decrypts the clean-v2 artifact into a dedicated warm seed volume;
2. derives the runtime UID/GID from the exact pinned controller image;
3. changes ownership of the restored seed to that runtime identity;
4. proves the seed can be copied while mounted read-only as the actual controller user;
5. binds the read-only seed as `GATEWAY_WARM_STATE`;
6. keeps `TWS_SETTINGS_PATH` as a distinct live volume;
7. waits for the paper Gateway API;
8. runs the canonical post-auth read-only consumer;
9. gracefully stops Gateway and publishes the next encrypted clean warm state.

## Required acceptance markers observed

```text
IBKR_WARM_STATE_SEED_READABLE=1
IBKR_WARM_STATE_RESTORED=1
IBKR_WARM_STATE_SEED_MODE=CONTROLLER_NATIVE
IBKR_CONTROLLER_NATIVE_WARM_SEED_BOUND=1
IBKR_AUTH_PATH=WARM_STATE_RESTORED
IBKR_GATEWAY_API_READY=1
IBKR_WARM_SESSION_REUSED=1
IBKR_CONSUMER_READY=1
IBKR_GATEWAY_GRACEFUL_STOP=1
IBKR_WARM_STATE_SEALED=1
IBKR_WARM_STATE_PERSISTED=1
IBKR_WARM_REUSE_READY=1
IBKR_PRIVATE_RUNTIME_DESTROYED=1
```

No IBKR Mobile approval step ran on the accepted warm reuse path.

## Post-auth consumer evidence

The accepted handoff reported:

- authenticated paper session: true
- API connected: true
- account summary readable: true
- positions readable: true
- open orders readable: true
- contract qualification: true
- historical market data: true
- canonical forward-bar materialization: true
- order submission: false
- AMAT and APH qualified successfully
- 200 forward bars per symbol, 400 total

The cloud workflow remains read-only at this milestone. It does not own MM-IBKR strategy intent, sizing, execution policy, submit, cancel, flatten, or live-trading authority.

## Published artifacts

### Reusable clean warm state

- Name: `ibkr-b1-warm-state-clean-v2`
- Artifact ID: `10488825288`
- Digest: `sha256:0aa5035cc0d02c8a99b5411165b2222eef6e49c90d2c1103eee951c09f39e63b`
- Expires: `2026-10-17T08:55:22Z`

### Canonical post-auth handoff

- Name: `ibkr-cloudflare-readonly-b1-35202149589`
- Artifact ID: `10488004708`
- Digest: `sha256:cbdb96434e7e6d07ba9ae4b797220f335fa7c5ac0e295eb4bd2b0275834fdf00`
- Expires: `2026-10-17T08:55:25Z`

## Next boundary

Warm authenticated public encrypted compute is no longer the blocker. The next work is to bind hardened compute to MM-IBKR's existing canonical selected-runtime execution mechanics through a narrow authenticated command/receipt boundary. Cloud compute must remain an execution surface, not a second trading authority.
