// Ephemeral operator-only caller. Never deploy. Run via wrangler dev bound to loopback.
// Only its explicit Cloudflare Service Binding can reach the private inference Worker.
import {sanitizeRolesReceipt} from "./roles_receipt.js";
const SOURCE_PATH = "/run-once";
const ROLES_PATH = "/roles-batch";
const DESTINATION = "https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia";
const CLASSIFICATIONS = new Set([
  "unattempted", "secrets_store_binding_missing", "secrets_store_read_unavailable",
  "secrets_store_value_unavailable", "catalog_transport_or_response_failure",
  "completion_transport_or_response_failure", "completion_http_200",
  "completion_response_invalid", "provider_access_rejected", "model_retired",
  "provider_rate_limited", "provider_http_error", "provider_response_unknown",
]);
const headers = { "Content-Type": "application/json", "Cache-Control": "no-store" };
function reply(code, payload) {
  return new Response(JSON.stringify(payload), { status: code, headers });
}
function status(n) { return Number.isInteger(n) && n >= 100 && n <= 599 ? n : null; }
function bounded(n, max) { return Number.isInteger(n) && n >= 0 && n <= max ? n : null; }
function bool(n) { return typeof n === "boolean" ? n : null; }

export function createCaller() {
  let invoked = false;
  return {
    async fetch(request, env) {
      const url = new URL(request.url);
      if (request.method !== "POST" || ![SOURCE_PATH, ROLES_PATH].includes(url.pathname) || url.search ||
          !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
        return reply(404, { classification: "local_route_unavailable" });
      }
      // Wrangler/workerd may represent a zero-byte POST as an empty stream.
      // Admit only a declared zero-length body; reject content-bearing posts.
      let roleBatch = null;
      if(url.pathname===ROLES_PATH) {
        const size=Number(request.headers.get("content-length"));
        if(!Number.isInteger(size)||size<1||size>30||
           request.headers.get("content-type")!=="application/json")
          return reply(400,{classification:"role_batch_selector_not_allowed"});
        let selector;
        try {selector=await request.json();}catch{return reply(400,{classification:"role_batch_selector_invalid"});}
        if(!selector||Object.keys(selector).length!==1||
          !Number.isInteger(selector.batch)||selector.batch< -1||selector.batch>99)
          return reply(400,{classification:"role_batch_selector_invalid"});
        roleBatch=selector.batch;
      } else if (request.body !== null && request.headers.get("content-length") !== "0") {
        return reply(400, { classification: "request_body_not_allowed" });
      }
      if (invoked) return reply(409, { classification: "caller_already_invoked" });
      if (typeof env?.NVIDIA_SERVICE?.fetch !== "function") {
        return reply(503, { classification: "remote_service_binding_missing" });
      }
      // One request per local dev session, even if upstream errors.
      invoked = true;
      try {
        const upstream = await env.NVIDIA_SERVICE.fetch(roleBatch===null
          ? new Request(DESTINATION, { method: "POST" })
          : new Request(DESTINATION.replace("/internal/diagnostics/nvidia",
              "/internal/diagnostics/nvidia-roles"), {
              method:"POST",headers:{"Content-Type":"application/json"},
              body:JSON.stringify({batch:roleBatch})
          }));
        const value = await upstream.json();
        if(roleBatch!==null) {
          const sanitized=sanitizeRolesReceipt(value);
          if(!sanitized||sanitized.batch!==roleBatch)
            return reply(502,{classification:"unexpected_synthetic_role_receipt"});
          return reply(upstream.ok ? 200:502,sanitized);
        }
        if (value?.schema !== "commandcenter.shared_nvidia_private_diagnostic.v1") {
          return reply(502, { classification: "unexpected_upstream_receipt" });
        }
        const sanitized = {
          schema: "commandcenter.shared_nvidia_private_diagnostic.v1",
          tested_model: "openai/gpt-oss-20b",
          catalog_http_status: status(value.catalog_http_status),
          completion_http_status: status(value.completion_http_status),
          catalog_includes_model: bool(value.catalog_includes_model),
          catalog_count: bounded(value.catalog_count, 100000),
          catalog_attempt_started: bool(value.catalog_attempt_started),
          catalog_failure_stage: ["outbound_fetch", "catalog_json"].includes(value.catalog_failure_stage)
            ? value.catalog_failure_stage : null,
          catalog_failure_kind: [
            "timeout", "aborted", "abort_api_unavailable", "redirect_rejected",
            "fetch_type_error", "runtime_type_error", "other_runtime_exception",
          ].includes(value.catalog_failure_kind) ? value.catalog_failure_kind : null,
          completion_response_valid: bool(value.completion_response_valid),
          exact_reply_observed: bool(value.exact_reply_observed),
          elapsed_ms: bounded(value.elapsed_ms, 60000),
          calls_made: bounded(value.calls_made, 2),
          classification: CLASSIFICATIONS.has(value.classification)
            ? value.classification : "unknown_provider_classification",
        };
        return reply(upstream.ok ? 200 : 502, sanitized);
      } catch {
        return reply(502, { classification: "service_binding_transport_or_receipt_failure" });
      }
    },
  };
}
export default createCaller();
