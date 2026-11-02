# Cross-domain NVIDIA workforce qualification (source candidate, 2026-11-02)

## Purpose

Find where smaller NVIDIA-accessible language models produce genuine net utility as *shadow* assistants for existing applications. Compare against rule-based reducers, ordinary stronger workers, and human editing. Do not treat passing two synthetic tasks as general model qualification. No live finance orders, home/device actions, customer contact, private input, arbitrary shell, secret transfer or runtime promotion is authorized by this source.

## Source and test contracts

- `src/workforce_domain_suite.js`: 32 fictional cases across 16 domain families. Paired counterfactuals flip meaningful facts; some document/incident/news tasks add long, structured provenance archives so identity and evidence matter. The case set is **public fictional research data only**, not private repository fixtures or credentials.
- `src/workforce_provider_runner.js`: selects model from an *authenticated* catalog sorted locally, with no caller-provided model ID or arbitrary prompt. Every case receives one actual completion attempt after one catalog check. Models can be unavailable, finish by length, attempt unsupported tools, or return invalid data; preserve those outcomes rather than rewriting them as incorrect answers.
- `local-probe/src/workforce_receipt.js`: only validated result metadata crosses the private Service Binding. No raw completions, model reasoning, arbitrary error strings, source text, credentials, URLs or tool arguments.
- `scripts/workforce_campaign_cli.mjs`: fixed localhost caller, immutable source identity, safe per-case checkpoint, provider-hold history and repeatable, no-lifetime-ceiling model-index slices. A transport hold does **not** consume an unfinished scored case; a replayed completed case is rejected.
- `src/workforce_role_selector.js`: separates per-role first-pass quality, missing coverage, provider outages, human-review needs, observed inference latency, and measured end-to-end labor savings. There is *no price inference*: missing provider prices remain unknown. Promotion is always false.

## Actual domains

News causal publication-time joins; direct versus indirect/duplicate issuer news; Trader Ops advisory freshness; market-data lineage/dedupe; portfolio gross-exposure and unfilled orders; dashboard build/endpoint freshness; worker receipt/origin reconciliation; incident/authorization evidence; Income-style cleaning quote economics; commerce capture/refund/replay truth; supplier CSV exceptions; home voice intents; protected typed tool planning; research study arithmetic/holdout claims; long multi-document release-evidence reconciliation; and operator digests requiring blind human review.

These are first-wave **skills** and business workflows, not a 16-model shortlist. The model catalog determines actual candidate count dynamically. Per-session request budgets and transport timeouts are safety/operations constraints, not declarations of lifetime model capability.

## Honest experiment ladder

1. Verify the exact reviewed source, source-owned test cases, and private Worker disabled/public-route configuration.
2. Obtain authorized private-Worker source deployment that preserves the account Secrets Store reference. Worker diagnostic `CC_NVIDIA_DIAGNOSTIC_ENABLED` remains disabled outside a bounded admitted run. **Source commits/PRs are not deployment receipts.**
3. Use the already-established authenticated Cloudflare Service Binding and loopback caller. First run one per-model provider admission/smoke case; capture catalog ID and source SHA; only then schedule 32-case role trials per admitted model. Stop on 429 or auth rejection and record exact provider status.
4. Collect *first pass* case results independently of retries. Use changed-fact paired holdouts. Attribute all receipts to the actual public execution run/job/commit and exact source version; no borrowed historical model scores.
5. For each promising or failing role, measure actual task quality on authorized **encrypted private** packets after transport/consumer admission. Do not copy private logs, household images or investor data into a public repository. Human review of writing and messy intelligence is necessary; the static grader is not its substitute.
6. Measure the deterministic/stronger-worker baseline and total cost of inference + verification + retries + editing. Track p50/p95 latency, unknown prices, output truncation, 403/404/410 access errors, 429 availability, provenance omissions, hallucinations and safety violations separately. Promote only when the owning consumer's real acceptance is signed off.

## Reusable role-fit output

Every result row identifies model, role, case coverage, first-pass objective correctness, availability failures, p50/p95 latency, human-review backlog and actually measured labor/time comparison. The row can recommend `compare_against_baseline`, `bounded_helper_with_verifier`, `needs_blind_human_review`, `investigate_provider_reliability`, `deterministic_or_fleet_preferred`, or a **promising shadow candidate**. It never claims deployment approval.

High-priority offload candidates to investigate are news evidence normalization and summarization, provenance-aware issue/receipt analysis, Trader Ops dashboard digest drafting, supplier document analysis, read-only income-opportunity research, and patch **proposals** verified by independent checks. Data ingestion, timestamps, arithmetic limits, ledger capture states, trade/risk gates and execution approval remain deterministic authority unless actual comparative evidence justifies another architecture.

## Historical evidence is not a result of this campaign

Earlier catalog/synthetic sweeps compared elementary math/logic/JSON/tool-calling across dozens of model IDs. Earlier five-fixture code-repair experiments produced positive Poolside and partial MiniMax evidence. They do not establish multi-domain, production-quality capability. The 32-case suite in this source has **no accepted NVIDIA provider outcomes until a source-pinned admitted live campaign has been executed and its provider receipt consumed.**

## Admission and current state

Source-only PR. Private GitHub Actions compute is prohibited. Public synthetic/offline tests on the existing research repository are permitted. The deployed production Worker source and diagnostic admission have not been changed in this PR. Do not run new provider workload by assuming the source branch is already deployed. No token or model must be copied into public code or workflow artifacts.


## Cross-run evidence assembly (offline and non-promoting)

One synthetic workflow dispatch evaluates at most eight fixed cases, and a process-local checkpoint cannot claim results from another workflow. To compare independent public workflow receipts, download each completed `nvidia-workforce-shadow-receipts` artifact **from its observed run/job**; extract only its `campaign_progress.json` in a trusted analyst context; verify actual GitHub run, event, job, completed status, artifact ID, immutable source and returned model ID before aggregation. A numeric `github-<run>` field is a self-reported identity, **not cryptographic proof of GitHub execution**.

Use the source-owned, metadata-only aggregation command from the exact candidate revision:

```sh
node scripts/workforce_aggregate_results.mjs --source <exact-source-SHA-40-hex> case1/campaign_progress.json case2/campaign_progress.json
```

It applies the same strict sanitizer as the local caller, rejects mixed oracle source SHA, duplicate run IDs and duplicate model+case observations, and uses the authenticated model name rather than an unstable numerical catalog position for identity. It reports per-role objective scores, provider holds, p50/p95 inference latency and missing human/financial measurement without promoting anything. It will intentionally reject older v1/v2 records if mixed with v3; historical scores must remain separately versioned.

A fully trustworthy comparison needs **both** the source-owned offline validation and independent owning public workflow/job/artifact readback. Merely updating a trigger text file, merging a PR, having a successful mock provider test, or seeing a `github-`-shaped string is insufficient to claim a new provider result. Do not infer provider availability from a catalog ID alone.

## Blind human review is an unimplemented private acceptance route

The public campaign artifacts contain only field-level booleans and metadata, **never model prose**. That is the intended privacy boundary, but it means they cannot support blind review of subjective drafts or real private-document analysis. `human_review_required` currently denotes a pending review, not a satisfactory writing result. Do not treat a schema-valid message as human quality or report labor savings from synthetic templates.

Before qualifying writing/summarization workers, the owning private reviewer must implement an authenticated, read-only **private-only** output viewing/review route with exact case/source/model/run identity, bounded redaction and retention, independent human correctness/safety rubric, double-blind alternatives, and immutable reviewer receipt. Do not pipe raw responses through public GitHub Actions artifacts or introduce a public Worker endpoint. The current synthetic workflow and diagnostic binding remain unchanged until separate authorization and exact binding admission. Subjective review results and actual analyst edit time must be consumed as separately sourced inputs, never inferred from a template or a model self-score.
