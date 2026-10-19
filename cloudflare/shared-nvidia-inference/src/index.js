// Private service-binding only. No workers.dev URL, external route or arbitrary proxy.
// This Worker does not accept user prompts, model IDs, target URLs or camera content.
// `NVIDIA_API_KEY` must be a Cloudflare account Secrets Store binding, not a plain var.
const ORIGIN = "https://integrate.api.nvidia.com";
const MODEL = "openai/gpt-oss-20b";
const RUN_PATH = "/internal/diagnostics/nvidia";
const HEADERS = Object.freeze({ "Content-Type": "application/json" });

function json(status, record) {
  return new Response(JSON.stringify(record), {
    status,
    headers: { ...HEADERS, "Cache-Control": "no-store" },
  });
}

function boundedStatus(value) {
  return Number.isInteger(value) && value >= 100 && value <= 599 ? value : null;
}

export async function probeNvidia(env, doFetch = fetch) {
  const receipt = {
    schema: "commandcenter.shared_nvidia_private_diagnostic.v1",
    provider: "nvidia_developer_api_shared",
    tested_model: MODEL,
    catalog_http_status: null,
    completion_http_status: null,
    catalog_includes_model: null,
    catalog_count: null,
    completion_response_valid: false,
    exact_reply_observed: false,
    elapsed_ms: null,
    classification: "unattempted",
    model_changed: false,
    home_actions: 0,
    raw_responses_exported: false,
    key_exported: false,
    user_prompt_data_used: false,
    calls_made: 0,
  };
  if (!env || typeof env.NVIDIA_API_KEY?.get !== "function") {
    receipt.classification = "secrets_store_binding_missing";
    return receipt;
  }
  let key;
  try {
    key = await env.NVIDIA_API_KEY.get();
  } catch {
    receipt.classification = "secrets_store_read_unavailable";
    return receipt;
  }
  if (typeof key !== "string" || key.length < 8) {
    receipt.classification = "secrets_store_value_unavailable";
    return receipt;
  }
  const start = performance.now();
  const headers = { "Authorization": "Bearer " + key, "Content-Type": "application/json" };
  try {
    const result = await doFetch(ORIGIN + "/v1/models", {
      method: "GET", headers, redirect: "error", signal: AbortSignal.timeout(12000),
    });
    receipt.calls_made++;
    receipt.catalog_http_status = boundedStatus(result.status);
    if (result.ok) {
      // Read ID strings from a bounded JSON catalog; never publish descriptions.
      const value = await result.json();
      const rows = value && Array.isArray(value.data) ? value.data : [];
      receipt.catalog_count = Math.min(rows.length, 100000);
      receipt.catalog_includes_model = rows.some(r => r && r.id === MODEL);
    }
  } catch {
    receipt.classification = "catalog_transport_or_response_failure";
    receipt.elapsed_ms = Math.round(performance.now() - start);
    return receipt;
  }
  try {
    const result = await doFetch(ORIGIN + "/v1/chat/completions", {
      method: "POST", headers, redirect: "error", signal: AbortSignal.timeout(15000),
      body: JSON.stringify({
        model: MODEL,
        messages: [{ role: "user", content: "Reply with PING_OK. This is a synthetic connection check." }],
        max_tokens: 64,
      }),
    });
    receipt.calls_made++;
    receipt.completion_http_status = boundedStatus(result.status);
    if (result.ok) {
      const data = await result.json();
      const msg = data && Array.isArray(data.choices) && data.choices.length
        ? data.choices[0]?.message : null;
      receipt.completion_response_valid = typeof msg?.content === "string";
      receipt.exact_reply_observed = receipt.completion_response_valid &&
        msg.content.trim() === "PING_OK";
    }
  } catch {
    receipt.classification = "completion_transport_or_response_failure";
    receipt.elapsed_ms = Math.round(performance.now() - start);
    return receipt;
  }
  const status = receipt.completion_http_status;
  receipt.classification = status === 200
    ? "completion_http_200"
    : status === 401 || status === 403
      ? "provider_access_rejected"
      : status === 410 ? "model_retired"
      : status === 429 ? "provider_rate_limited"
      : status >= 400 ? "provider_http_error" : "provider_response_unknown";
  receipt.elapsed_ms = Math.round(performance.now() - start);
  return receipt;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== RUN_PATH || url.search) {
      return json(404, { error: "unavailable" });
    }
    // Explicit deployment guard. In addition, wrangler disables all public routes.
    if (env.CC_NVIDIA_DIAGNOSTIC_ENABLED !== "1") {
      return json(503, { error: "diagnostic_not_admitted" });
    }
    if (request.headers.get("content-length") !== null &&
        request.headers.get("content-length") !== "0") {
      return json(400, { error: "request_body_not_supported" });
    }
    const result = await probeNvidia(env);
    return json(result.classification === "completion_http_200" ? 200 : 503, result);
  },
};
