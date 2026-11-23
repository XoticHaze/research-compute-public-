# Bounded Blender public CPU worker, candidate only

This is a public, fixed-recipe compute worker *implementation*, not a running or admitted compute capacity. The existing CommandCenter job router, issuer and A1 encrypted capsule must authorize external execution. It is forbidden to bypass an unadmitted placement by manually selecting a workflow or uploading private CommandCenter source to public compute.

## Pre-existing, reusable mechanics

- CommandCenter `compute/execute_job.py`, `compute/router.py` and `compute/launch_placed_job.py` own the job and placement boundary.
- This public repository already has a P-256/AES-GCM sealed two-sided request/result implementation in `scripts/opaque_bidirectional_capsule_p256_aesgcm_v1.py`.
- The existing Cloudflare fleet-authority has previously issued ephemeral encrypted envelopes, and independent prior public runs proved encrypted input/result. This worker does not recreate crypto, tokens, Workers or a new generic execution router.
- Current protected generic R1 admission is separate from historical, individually admitted job proofs. No promise of a production Blender launch until the live issuer, driver, signed ticket and return consumer are admitted.

## New fixed worker

Source: `scripts/creative/blender_fixed_worker_v1.py` and `scripts/creative/industrial_arm_v1.py`. All inputs are explicitly public. `source.commit` must equal the immutable checkout HEAD. Request only selects a predefined `industrial_arm_v1` recipe and bounded preview parameters, not script, shell, input URLs or private files. The job produces `arm.blend`, `arm.glb`, `preview.png`, `receipt.json` plus a bounded executor log.

The admitted executor sets `CC_APPROVED_BLENDER_BINARY` to Blender 5.2 or newer, verifies its pinned runtime/image identity and invokes:

```sh
python3 scripts/creative/blender_fixed_worker_v1.py --job <FIXED_ADMITTED_JOB_JSON> --source-root <PINNED_PUBLIC_CHECKOUT> --output-root <TRUSTED_EPHEMERAL_OUTPUT_ROOT>
```

Arguments are supplied by the authenticated infrastructure/typed controller, never accepted as arbitrary user shell. The worker enforces a 300-second Blender timeout and two CPU threads. The source-only negative tests do not require Blender.

## Need to complete before execution

1. Runtime authority registers/selects an independently admitted Blender-compatible public-encrypted executor, with pin-proven Blender 5.2+ binary. The current generic public route is held; do not alias it or pass a fake A1 certificate.
2. A real signed placement and nonce claim passes the existing CommandCenter verifier; current trusted issuer list is empty. Existing Cloudflare neutral first seal is a separate protected release authority and should be reconciled, not rebuilt.
3. The admitted public worker executes this fixed recipe and returns the required *encrypted* full artifact payload to a private consumer, with public fixed-field metadata only. Avoid plaintext private references/designs.
4. The receiving consumer verifies exact immutable job digest, actual file hashes and sizes, Blender version, real GLB animation and the PNG. A source test or receipt alone is not visual acceptance.
5. Operator approves/revises via the CommandCenter bounded review-loop contract, creating a new immutable job for the next iteration. Do not auto-approve, silently overwrite accepted assets or claim persistent Blender service hosting on ephemeral Actions runners.

**Execution state:** SOURCE CANDIDATE. No Blender runtime tested, no active worker, no render result, no GPU, no server, no claimed signed generic ticket.
