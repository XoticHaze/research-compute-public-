# AI Lab V1 — pinned product target (proposal for operator review)

**Status:** Visual and product target attached to the existing source-only PR #2123. **Not production-admitted, not deployed, and not a model response.**
**Visual proof:** \`docs/ai-lab/ai-lab-v1-preview.html\` (self-contained interactive mockup with explicitly fictional examples). Treat this preview as the V1 layout acceptance target **after operator review**; do not assert automatic approval by attaching it.

## What the human should see

A single **AI Lab** workspace at the existing Cloudflare Access-locked operator site, under \`/ai-lab\`. This is not a second domain or authentication stack.

- **Center:** chat-first thread, clearly identified model, examples, response/receipt status, message composer, reliable error states.
- **Left:** new conversation, conversations, tasks, memory, experiments, schedules, runs and receipts.
- **Right:** exact model and provider status, current task focus, allowed capabilities and trust boundaries.
- **Responsive:** desktop three-column layout collapses sensibly on a phone.
- **No fake proof:** sample conversations are explicitly labeled as sample; absent provider, private work, stored history or auth is never represented as working.
- **Operator success:** the human can actually use the browser UI, not merely inspect a PR or a contract report.

## Ordered acceptance gates

| Gate | Demonstrable acceptance criterion | State when pinned |
|---|---|---|
| P0 | Layout target agreed in preview, no unsupported permissions/capabilities shown | Draft proposal |
| P1 | Existing Access identity gets AI Lab at \`/ai-lab\`, isolated operator-owned storage, refresh survives browser restart, no regression to \`/bot-console\`, two browser widths | Not deployed |
| P2 | Existing NVIDIA private binding gets a **separately reviewed**, bounded interactive inference contract with explicit input/output privacy, rate limits and cost/terms gate; genuine provider response visible and recorded | Not implemented |
| P3 | Conversational user + model turns persist, replay/duplicate protection, distinct threads, output attribution and honest statuses | Not implemented |
| P4 | Read-only experimental tools and admitted public-encrypted compute produce independent receipts. No private GH Actions compute, broker, trading or HAOS authority; generic A1 route must pass its existing admission | Not implemented |
| P5 | Operator can manage memory, schedules and completed work with auditability, privacy review, retention and deletion | Not implemented |

## Explicit non-goals

Do not add a second Worker, another UI host, new tunnel or agent fleet just to demonstrate V1. Do not enable NVIDIA diagnostics as a user-chat proxy. Do not claim the preview's fictional messages are real. Do not solicit real personal notes before a privacy review. Do not bypass the existing deployment, Access, OIDC, device, broker, compute or protected-release boundaries.

## Existing implementation relative to this target

The existing M0 source in \`cloudflare/operator-console/src/ai_lab_sandbox.js\` already provides a simple opt-in notes page and per-operator durable storage, with contract tests. It **does not implement this full visual target, model conversation, tasks, or schedules.** Close this gap in the same owning feature and existing UI source, ideally preserving M0 functionality rather than creating a second app.
