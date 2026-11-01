// Account-conscious pacing for the pre-existing private NVIDIA Service Binding.
//
// One queue is shared by all three diagnostic routes within a Worker isolate.
// This controls this Worker's outbound requests, NOT other NVIDIA API consumers
// or independent Cloudflare isolates. Only fixed upstream NVIDIA endpoints work.
// Uses a deliberately conservative 2 requests/second ceiling (<= operator's
// provisional 3/second), serializes in-flight provider work, and holds locally
// after 429 without making further provider calls.
// No secrets, model prompts, provider response bodies, or freeform headers are logged.
export const MIN_PROVIDER_SPACING_MS = 500;
const MAX_HOLD_MS = 4 * 60 * 60 * 1000;
const BASE_429_HOLD_MS = 60 * 1000;
const API = "https://integrate.api.nvidia.com";
const ALLOWED = new Map([
  [API + "/v1/models", "GET"],
  [API + "/v1/chat/completions", "POST"],
]);

export function parsedRetryAfterMs(header, nowMs = Date.now()) {
  if (typeof header !== "string" || header.length > 96) return null;
  const value = header.trim();
  if (/^[0-9]{1,6}$/.test(value)) {
    return Math.min(MAX_HOLD_MS, Number(value) * 1000);
  }
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.min(MAX_HOLD_MS, Math.max(0, date - nowMs)) : null;
}

export class NvidiaProviderPacingQueue {
  constructor({providerFetch, now = () => Date.now(),
               sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
               minSpacingMs = MIN_PROVIDER_SPACING_MS} = {}) {
    if (typeof providerFetch !== "function" || typeof now !== "function" ||
        typeof sleep !== "function" || !Number.isInteger(minSpacingMs) ||
        minSpacingMs < MIN_PROVIDER_SPACING_MS) {
      throw Error("invalid_private_provider_pacer");
    }
    this.providerFetch = providerFetch;
    this.now = now;
    this.sleep = sleep;
    this.minSpacingMs = minSpacingMs;
    this.tail = Promise.resolve();
    this.nextEligibleMs = 0;
    this.holdUntilMs = 0;
    this.consecutive429 = 0;
  }
  async fetch(url, opts) {
    const method = opts?.method;
    if (ALLOWED.get(url) !== method || opts?.redirect !== "manual") {
      throw Error("private_provider_destination_or_method_rejected");
    }
    const operation = async () => {
      const before = this.now();
      if (before < this.holdUntilMs) {
        const remaining = Math.ceil((this.holdUntilMs - before) / 1000);
        // Synthetic local hold. This does not send a provider request.
        // Caller treats it as rate_limited; do not expose provider content.
        return new Response(null, {status:429, headers:{"Retry-After":String(remaining)}});
      }
      const delay = Math.max(0, this.nextEligibleMs - before);
      if (delay) await this.sleep(delay);
      // Claim spacing BEFORE the network attempt, including failures/timeouts.
      this.nextEligibleMs = this.now() + this.minSpacingMs;
      const response = await this.providerFetch(url, opts);
      if (response?.status === 429) {
        this.consecutive429 = Math.min(7, this.consecutive429 + 1);
        const server = parsedRetryAfterMs(response.headers?.get?.("Retry-After"), this.now()) ?? 0;
        const defaultHold = Math.min(MAX_HOLD_MS, BASE_429_HOLD_MS * 2 ** (this.consecutive429 - 1));
        this.holdUntilMs = Math.max(this.holdUntilMs, this.now() + Math.max(server, defaultHold));
      } else {
        this.consecutive429 = 0;
      }
      return response;
    };
    const pending = this.tail.then(operation, operation);
    this.tail = pending.then(() => undefined, () => undefined);
    return pending;
  }
}
