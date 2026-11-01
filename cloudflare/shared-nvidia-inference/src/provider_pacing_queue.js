// Account-conscious pacing for the pre-existing private NVIDIA Service Binding.
//
// One queue is shared by all three diagnostic routes within a Worker isolate.
// This controls this Worker's outbound requests, NOT other NVIDIA API consumers
// or independent Cloudflare isolates. Only fixed upstream NVIDIA endpoints work.
// Two independent limits: a strict <=3 start/second spacing ceiling and a
// configurable 40-requests/60s SOFT default. An initial token burst (max 3)
// allows responsive short work; a 40-RPM token bucket + a strict rolling
// 60-second window enforce sustained throughput before any provider 429.
// This protects only this Worker isolate. It is NOT an account-global quota,
// and model/provider capacity may still be lower. 429 opens a circuit hold.
// No secrets, model prompts, provider response bodies, or freeform headers are logged.
export const MIN_PROVIDER_SPACING_MS = 334;
export const RATE_LIMITED_SPACING_MS = 1500;
export const DEFAULT_SOFT_RPM = 40;
export const MAX_CONFIGURABLE_RPM = 180;
const WINDOW_MS = 60000;
const MAX_BURST_TOKENS = 3;
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
               minSpacingMs = MIN_PROVIDER_SPACING_MS,
               softRpm = DEFAULT_SOFT_RPM} = {}) {
    if (typeof providerFetch !== "function" || typeof now !== "function" ||
        typeof sleep !== "function" || !Number.isInteger(minSpacingMs) ||
        minSpacingMs < MIN_PROVIDER_SPACING_MS || !Number.isInteger(softRpm) ||
        softRpm < 1 || softRpm > MAX_CONFIGURABLE_RPM) {
      throw Error("invalid_private_provider_pacer");
    }
    this.providerFetch = providerFetch;
    this.now = now;
    this.sleep = sleep;
    this.minSpacingMs = minSpacingMs;
    this.softRpm = softRpm;
    this.requestStarts = [];
    this.tokens = Math.min(MAX_BURST_TOKENS, softRpm);
    this.lastRefillMs = this.now();
    this.effectiveSpacingMs = minSpacingMs;
    this.rateLimitObserved = false;
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
      // Pace BEFORE calling NVIDIA. A rolling window prevents exceeding the
      // configured per-minute count, while bucket tokens smooth bursts so
      // the first minute is not exhausted in 14 seconds at 3 RPS.
      let reserved = false;
      while (!reserved) {
        const t = this.now();
        if (t < this.holdUntilMs) {
          const left = Math.ceil((this.holdUntilMs - t) / 1000);
          return new Response(null, {status:429, headers:{"Retry-After":String(left)}});
        }
        this.requestStarts = this.requestStarts.filter(v => v > t - WINDOW_MS);
        const refill = Math.max(0, t - this.lastRefillMs) * this.softRpm / WINDOW_MS;
        this.tokens = Math.min(Math.min(MAX_BURST_TOKENS, this.softRpm), this.tokens + refill);
        this.lastRefillMs = t;
        const spacingWait = Math.max(0, this.nextEligibleMs - t);
        const rollingWait = this.requestStarts.length >= this.softRpm
          ? Math.max(1, this.requestStarts[0] + WINDOW_MS - t) : 0;
        const bucketWait = this.tokens < 1
          ? Math.max(1, Math.ceil((1 - this.tokens) * WINDOW_MS / this.softRpm)) : 0;
        const delay = Math.max(spacingWait, rollingWait, bucketWait);
        if (delay > 0) {
          await this.sleep(delay);
        } else {
          this.tokens -= 1;
          this.requestStarts.push(t); // count failed and 429 starts too
          this.nextEligibleMs = t + this.effectiveSpacingMs;
          reserved = true;
        }
      }
      const response = await this.providerFetch(url, opts);
      if (response?.status === 429) {
        this.consecutive429 = Math.min(7, this.consecutive429 + 1);
        // A 429 is hard evidence that 3 RPS alone did not satisfy upstream
        // admission. Retain slower pacing for this isolate, not just a retry sleep.
        this.rateLimitObserved = true;
        this.effectiveSpacingMs = Math.max(this.effectiveSpacingMs, RATE_LIMITED_SPACING_MS, Math.ceil(WINDOW_MS / this.softRpm));
        this.nextEligibleMs = Math.max(this.nextEligibleMs, this.now() + this.effectiveSpacingMs);
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
