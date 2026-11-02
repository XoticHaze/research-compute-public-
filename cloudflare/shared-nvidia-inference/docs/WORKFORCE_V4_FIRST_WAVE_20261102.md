# Independent v4 evidence assessment: first-wave public-source candidate

**Status:** SOURCE_CANDIDATE_ONLY, provider calls=0, private input=0, production roles=0.
**Ownership:** existing NVIDIA workforce PR #2095, its existing Cloudflare Service Binding and operator-review/CommandCenter consumer chain.
**Manual source contributor:** MW-20261102113623638.
**Historical v3:** frozen, 20/30 exact objective classifications, 2 writing examples ungraded; not a narrative or production reliability demonstration.

## What is implemented now

- `src/workforce_v4_contract.js`: three independently authored advisory response schemas, fixed enum vocabulary, bounded input, explicit source references, uncertainty and proposed-only status. **No dependency on grading oracle or expected labels.**
- `src/workforce_v4_holdout.js`: **60 new PUBLIC FICTIONAL FIRST-WAVE** tasks, 20 per role (receipt triage, incident diagnosis, long-document reconciliation); four source/identity variants and five changed-fact patterns. Each has potentially misleading untrusted notes and unrelated evidence. No household/customer/broker/private repository text.
- `src/workforce_v4_grader.js`: objective exact-label/ref scorer, invented-source-ID rejection, approval-authority check, and sanitized result. Even when objective fields pass, full-task acceptance remains false until separately validated blind human review.
- `tests/workforce_v4_holdout.test.mjs`: structural 60-case coverage, independent prompt contract, scored positive/negative cases, invalid citations, unauthorized proposals, malformed responses, and no-private-input/production assertions.
- `src/workforce_v4_value_gate.js` + `tests/workforce_v4_value_gate.test.mjs`: optional measured deterministic/small-model/stronger-worker comparison on matching input digests. Require at least 20 distinct mechanisms, 3 formats, no invented refs or authority violations, observed latency/review effort and priced comparisons before treating a model as advantageous. Code remains preferred when it performs as well or better. This analytic source can never validate cryptographic signatures, admit private data, or activate production.
- `src/workforce_v4_provider_runner.js` + `tests/workforce_v4_provider_runner.test.mjs`: fixed-index/catalog-bound, private-only candidate adapter. All provider I/O is injected, so the test suite uses mocked network responses and verifies that tool calls are rejected, per-case API statuses are sanitized, and no raw model text, user prompts or secret data can leave in receipts. **This adapter is not imported into the deployed Worker handler, caller or workflow and performs zero live inference by itself.** Owner review plus admitted release is needed before wiring it.

**Important statistical caveat:** The public first wave has only five factual answer patterns per role with four identity/dossier variants. The 20 cases per role are intentionally correlated and do **not** yet count as 20 independent production-qualification trials. Their expected labels are source-visible, not sealed from an adversarial observer. Do **not** claim independent blinded validation or claim M2 acceptance from these fixture counts. A separately prepared, concealed final holdout with varied underlying mechanisms and precommitted oracle is required.

## Required evidence before any NVIDIA run or role selection

1. Source owner reviews the exact v4 contract, case identities and gold against role facts before model inference. Fix any contradictions and independently verify case variation and coverage. Pinned source SHA and manifest hashes must be recorded first.
2. Confirm a scope-admitted **public fictional-only** execution path and exact private Service Binding/Secrets Store readback. The current v4 files are **not wired to any provider route or public workflow**. Do not add an arbitrary prompt/selector or a public Worker endpoint. No private Actions compute or protected operations.
3. Independently run offline source checks on an admitted surface; record exact source, runner, job and results. Public CI green alone is not provider capability.
4. Only after owner admission, execute measured first-pass model attempts on frozen public fictional tasks using existing fixed, bounded private diagnostic transport. Restore diagnostic flag to disabled and independently read back.
5. On identical held-out inputs, compare (a) existing deterministic verifiers, (b) Poolside, (c) a qualified stronger worker. Compare exact field correctness **separately** from author-written explanation quality. Correctly classify provider rate-limit, timeouts, 4xx/5xx as availability/transport, not reasoning errors.
6. Human blind reviewers score evidence-grounded rationale accuracy, useful abstention, misleading causality, readability and rework time. All model-generated raw text stays within its approved private review consumer; public receipts contain only bounded score metadata.
7. Create independent hidden holdouts with realistic fact/format diversity and no oracle leak into model prompt or schema before any promotion discussion. The proposed >=90% strict, 0 critical authority violations, 0 invented citations and >=20% observed reviewer time-saving are **candidate gates**, not approved production policy.
8. Only exact owning consumer/security authority may admit real private input or activate an advisory model. General A1 two-sided transport remains held, unless separately approved private consumer service binding is established.

## Role design rather than a new workforce

**Persistent deterministic core** handles queue polling, ack/heartbeat checks, request-result/identity/signature validation, state reducers, source/schema drift and bounded replay-safe checkpoints. Models must never replace cryptography, arithmetic, validation or approvals.

Optional model enrichments on verified snapshots:
- receipt conflict *explanations* and reconciliation suggestions;
- incident hypotheses with unknown-source labeling and citations;
- long-document synthesis and explicit abstention;
- later, research hypothesis exploration and semantic-change review.

When models or the scheduled fleet are absent, deterministic workers still complete permitted checks and preserve the latest checkpoint. Model-specific work is deferred, downgraded or escalated rather than blocking the entire queue. No new recurring ChatGPT automation, dashboard, broker or standalone orchestration layer.

### Comparators and usefulness (do not substitute sample counts)

Use an owner-prepared sampling frame from actionable queue items, include failures and near-duplicates, and measure baseline `operator_seconds`, `model_latency_seconds`, `review_seconds`, `rework_seconds`, `provider_cost_usd` and `accepted_action` per task. Compare end-to-end net saved seconds and false-escalation cost. A cheaper deterministic method wins when it provides equivalent correctness; no model assignment is automatically justified by a high fixture score.
