# IBKR Paper-Proof Warm Reseal Fix Evidence — 2026-09-17

## Finding

The admitted `paper_submit_proof` step could exit nonzero before the existing graceful-stop and clean warm-state reseal steps. A blocked or failed proof therefore risked losing the reusable authenticated warm-state lifecycle even though the proof itself was correctly fail-closed.

## Repair

- The paper-proof step now has `id: paper_proof` and `continue-on-error: true` solely so lifecycle cleanup can continue.
- The existing Gateway graceful stop, clean warm-state seal, and artifact persistence remain after the proof step.
- A dedicated late assessment checks `steps.paper_proof.outcome` only after warm-state persistence and fails the job if the proof was not successful.
- Final private-runtime cleanup remains `if: always()`.
- Read-only remains the default mode; this repair does not loosen paper/live/global-cancel authority.

## Validation

Public GitHub-hosted run `35258527299` passed the combined no-broker contract suite covering:

- warm lifecycle ordering and controller-native seed reuse,
- credential-free command capsule v2,
- canonical HTTP-only paper-proof executor,
- encrypted proof return,
- warm selected-runtime activator,
- the new proof-failure → graceful-stop → reseal → persistence → late-failure ordering regression.

The validation emitted no broker login or broker order attempt.

An earlier patch-delivery run `35258170881` also executed the updated warm-state regression suite successfully: 17 tests passed. Its final git push failed only because an Actions `GITHUB_TOKEN` cannot update workflow files without the `workflows` permission; the reviewed product changes were subsequently applied through repository workflow-file authority and revalidated by `35258527299`.
