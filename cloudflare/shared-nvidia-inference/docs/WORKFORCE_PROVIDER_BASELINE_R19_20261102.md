# NVIDIA cross-project workforce: first provider evidence and next acceptance gates

**Observed review:** 2026-11-02. **Manual Worker origin:** `MW-20261102080556164`. All measurements below were independently recovered from the named existing public WaterBoys workflow **sanitized ZIP artifacts**. No raw model completions, provider API key, private case materials, or production mutation is recorded here. Source commits and mock test counts are not model-performance results.

## Actual first-wave provider receipts (historical)

| Source/oracle | Run (GitHub Actions) | Model | Completed cases | Exact-field cases | Correct fields | Median inference | Total inference |
|---|---|---|---:|---:|---:|---:|---:|
| `c0d9cc345dc7106045b4089048315b7efa33abe2` (v1) | [41400562521](https://github.com/XoticHaze/waterboys-fantasy-compute/actions/runs/41400562521) | `poolside/laguna-xs-2.1` | 8/8 | 0/8 | 12/28 | 2.726 s | 19.426 s |
| `c0d9cc345dc7106045b4089048315b7efa33abe2` (v1) | [41400849222](https://github.com/XoticHaze/waterboys-fantasy-compute/actions/runs/41400849222) | `openai/gpt-oss-20b` | 8/8 | 2/8 | 17/28 | 49.489 s | 404.061 s |
| `7db423306798d2e5420fe8f4e136f070b1f69f4b` (v2) | [41401866375](https://github.com/XoticHaze/waterboys-fantasy-compute/actions/runs/41401866375) | `poolside/laguna-xs-2.1` | 8/8 | 3/8 | 20/28 | 2.614 s | 19.468 s |

All three sessions used the initial eight news, market, Trader Ops, and data-lineage cases. **These are NOT comparable quality ratings across v1/v2**, because source/rubric and causal-news gold changed. v2 Poolside objective subroles: Trader Ops advisory freshness **2/2 strict**, market-data lineage **1/2 strict**, issuer-news relevance **0/2 strict**, and news timing **0/2 strict** under its now-superseded v2 oracle. These small synthetic observations cannot establish general task competence or production readiness.

[MiniMax run 41400264018](https://github.com/XoticHaze/waterboys-fantasy-compute/actions/runs/41400264018) yielded **zero scored cases**. It stopped after one `transport_or_decoding_failure` at approximately 90.047 s and no HTTP completion status; do not count this as an accuracy failure. The later v2 profile changed the token budget and experimental deadline. Its successful follow-up provider/role result remains unverified here.

## Current v3 and candidate source distinction

- **Current admitted WaterBoys source pin:** `d18a85c78e3db84ffde6d51cb3d785971e6f0a38` (observed-at causal-news v3). Triggered redeploy and Poolside news/docs studies exist, but this review did not retrieve an independently verified workflow/job/artifact for those specific push-triggered studies or latest Cloudflare settings readback.
- **Additional requested comparison:** `2a136e4a5f59f4ec0c3f520f9ce36c83fe13112c` submitted source-pinned, two-case GPT-OSS 20B v3 news evaluation through the existing WaterBoys public-synthetic workflow. A trigger commit is **not** proof of inference.
- **New source-only candidate:** PR [#2095](https://github.com/XoticHaze/research-compute-public-/pull/2095) adds strict scorecard integrity, cross-run aggregation, and contract/documentation. Public synthetic offline validation **124/124 passed** on run [41413302527](https://github.com/XoticHaze/research-compute-public-/actions/runs/41413302527). Those 124 are **Node tests**, not 124 NVIDIA model inferences. WaterBoys has not been re-pinned to this later source.

## Highest-value practical next sequence

1. Obtain exact completed public WaterBoys run ID, job, artifact SHA/source, model-id mapping, provider status, and post-run Cloudflare diagnostic disabled readback for each submitted v3 trigger. Do not infer completion from a commit or catalog listing.
2. Use only **same-source v3** independent paired counterfactual cases for first model-to-model comparisons. Apply `scripts/workforce_aggregate_results.mjs` only after externally verifying the run/job/artifact identities. No duplicate model+case credit.
3. Prioritize four meaningful roles before breadth sweeps: point-in-time news with changed facts, provenance-linked worker receipt triage, long-document release reconciliation, and read-only quote economics. Keep deterministic risk/arithmetic/tool gates authoritative.
4. Add a private-only reviewed-output path before evaluating writing quality. Public sanitized artifacts intentionally omit model prose and thus cannot establish blind human quality or human rework time; no production model promotion until verified human and economic benchmarks.

**Operator action now:** No new secrets, access keys, or account approvals requested by this source note. Pending acceptance belongs to existing WaterBoys/Cloudflare runtime proof and owning protected reviewer route. Preserve unchanged production authority.
