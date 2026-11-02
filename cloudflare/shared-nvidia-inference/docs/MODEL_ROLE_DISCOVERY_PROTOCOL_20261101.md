# NVIDIA submodel research: capability discovery before CommandCenter admission
**Research stage:** source implementation and offline contract checks only. No live inference from these new role tasks has been confirmed. No real CommandCenter job, household imagery, private repository source, agent tool action, or production change is authorized.

## Why this exists
Do not use the former toy 4/4 score or the 24 deterministic action-label cases as evidence of a useful autonomous workforce. Coding repairs already demonstrate **potential**: Poolside Laguna XS 2.1 achieved five verified fictional Python fixes after retries and reviewer correction; MiniMax M3.1 Flash achieved three, with remaining provider timeout/format uncertainty. These outcomes do not establish first-pass rates on real repositories or fitness for other roles.

## First bounded research comparison
- First-wave models: `poolside/laguna-xs-2.1` and `minimaxai/minimax-m3.1-flash`. This is a **pilot**, not a model shortlist or final ranking. Next cohorts must include qualified models from the authenticated NVIDIA catalog and at least one non-specialized baseline where accessible.
- Five task families with *two different fictional evidence sets each*: cross-source investigation, unstructured structured extraction, permission-aware tool planning (plans only, never tool calls), reliability-first analysis under unknown costs, and operator-facing writing.
- Ten distinct fixed tasks total, 20 model×task first-pass inferences if both candidates are available. No raw model answer or reasoning leaves the private Service Binding. Source-owned fixed selectors, output schema, prompt, model and target host remain non-user-controllable.
- Counterfactual holdouts change canonical hashes, incident timestamps, counts, tool access and model performance. Replaying a memorized original answer must fail the paired hidden oracle. All "expected answers" are in the independent scorer, not the user prompts.
- Operator prose is **not** objectively quality-qualified: format and anchor checks alone are insufficient. Mark `human_review_required`; the current sanitized receipt deliberately contains no text for human judgement. A separately approved private human-review surface would be necessary to qualify this role.
- Scorer pass does not authorize deployments, live broker or home actions. These tasks use entirely fictional public test data.

## Model-native discovery defaults, not optimization ceilings
| Model | Preliminary generation budget | Sampling | Provider profile | Interpretation |
|---|---:|---|---|---|
| Poolside Laguna XS 2.1 | 8,192 | temperature 1.0, top_p 0.95 | NVIDIA endpoint default is 8,192, maximum 16,384 | Start at provider defaults, then measure usage |
| MiniMax M3.1 Flash | 8,192 | temperature 1.0, top_p 0.95 | NVIDIA exposes up to 65,536 generated tokens and optional reasoning effort levels | 8,192 is a first-wave diagnostic allowance, **not** the maximum; expand when `finish_reason=length` or reasoning evidence shows truncation |
Sources: https://docs.api.nvidia.com/nim/reference/poolside-laguna-xs-2-1-infer and https://docs.api.nvidia.com/nim/reference/minimaxai-minimax-m3-1-flash-infer and https://docs.api.nvidia.com/nim/reference/minimaxai-minimax-m3-1-flash .

**Usage-rights and size guard:** NVIDIA's current MiniMax M3.1 Flash model page labels the hosted model **"for research and development only"** under the NVIDIA Software and Model Evaluation License and its community license. A successful research benchmark is NOT commercial/production-use clearance; revisit the exact provider deployment terms before any commercial integration. NVIDIA describes MiniMax M3.1 Flash as 428B total / 23B active parameters, versus Poolside Laguna XS 2.1 at 33B total / 3B active, so they are not equivalent local resource targets. Poolside's model page says commercial and non-commercial use are supported subject to its applicable OpenMDW license; NVIDIA's hosted API trial has separate trial terms. Model sizes alone do not predict hosted latency or cost. Sources: https://docs.api.nvidia.com/nim/reference/minimaxai-minimax-m3-1-flash and https://docs.api.nvidia.com/nim/reference/poolside-laguna-xs-2-1 .

Provider 429 is **availability**, not model quality; aborted/timeout and decode errors have separate failure classifications. A fixed 75-second per-request transport safety timeout is **not** a model ability threshold. Record it separately, and increase only after reviewing provider throughput and Cloudflare/transport limits. The existing shared pacing queue's soft 40 RPM is not a verified account-wide provider allowance.

## Qualification receipt design
For each attempted fixed case record: exact source revision, model ID, task ID, first-pass answer correctness, each contract check result count, format validity, finish reason, prompt/completion/reasoning token COUNTS if provider supplied them, HTTP class, failure class, latency, and explicit `production_authorized=false`. Missing usage metadata is **unknown**, not zero. Never label model success when a request failed due to 429, connection, timeout, or response decoding. Preserve the exact provider-count/timeout evidence separately from scored wrong answers.

For cross-model comparisons, report **per-skill** first-pass pass rate and case coverage, p50/p95 latency, timeout/429/error counts, observed output-token distribution, and human reviewer edit burden if an approved private review surface exists. No single global composite score hides disqualifying failure categories. Do not convert 2 tasks per skill into a confident production guarantee. Repeat with at least one new independent task set and a benchmark baseline before making role decisions. Keep model providers and hardware availability separate from model capability.

## Deployment and execution boundary
- Public source location: `XoticHaze/research-compute-public-`, `cloudflare/shared-nvidia-inference`. This is **public synthetic source** and permitted public CI; it is NOT the user's private project repository.
- Existing bound private Cloudflare Worker identity and Secrets Store binding must remain unchanged. `workers_dev=false`, `preview_urls=false`, fixed Service Binding only. No public route or generic inference proxy.
- Existing public compute caller workflow in `XoticHaze/waterboys-fantasy-compute` pins a **historical** Worker source commit and does not invoke the new discovery route. No new discovery model performance may be claimed from that older workflow.
- New source must be reviewed against the owning deployment authority, bound Worker deployment must succeed with secret reference preserved, and exact deployed revision must be independently read back *before* any private authenticated discovery run. A failed deploy or unverified route is a hold, not permission to bypass it.
- The staged local loopback caller accepts up to **20 distinct** fixed `(model_index, task_index)` requests per ephemeral session, rejects replay and mixing with other suites, and stops after an upstream rate limit, pending outcome, or transport failure. This is more reproducible than relaunching the runtime for every case. No public deployment or provider run is implied.
- An approved future public synthetic runner can invoke a **fixed** case selector over loopback Service Binding. Do not copy `NVIDIA_API_KEY`, private repo content, personal files or raw output into a public workflow or logs. Never run private GitHub Actions compute.
- No standalone lab repository is necessary yet. Keep evidence and pilot role code in the existing approved research infrastructure until genuine live skill results show further investment worthwhile.

## Current state / objective next gate
**Prepared:** two candidate request profiles, ten fixed paired cross-skill tasks, independent scoring and adversarial regressions, private Worker gate, local-only caller, metadata sanitization.
**Not yet observed:** new tasks executed against the authenticated provider; model-specific true pass rates; fresh token/length behavior under changed settings; human evaluation; deployed Worker running this exact source; CommandCenter production integration. These are not interchangeable.
**Highest-value next experiment:** after exact bound deployment admission, one first-pass 20-case synthetic comparison with receipts, no retry masking, plus focused MiniMax reattempts of the previously truncated/time-limited coding functions. Then expand across the eligible catalog and more difficult tasks based on observed gaps, not model names.

This document is a research handoff, not release authorization.
