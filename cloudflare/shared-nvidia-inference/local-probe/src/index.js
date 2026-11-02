// Ephemeral operator-only caller. Never deploy. Run via wrangler dev bound to loopback.
// Only its explicit Cloudflare Service Binding can reach the private inference Worker.
import {sanitizeRolesReceipt} from "./roles_receipt.js";
import {sanitizeMicroReceipt} from "./micro_receipt.js";
import {sanitizeDraftReceipt} from "./draft_receipt.js";
import {sanitizeCodeReceipt} from "./code_receipt.js";
import {sanitizeCodeRoleReceipt} from "./code_role_receipt.js";
const SOURCE_PATH = "/run-once";
const ROLES_PATH = "/roles-batch";
const MICRO_PATH = "/micro-batch";
const DRAFT_PATH = "/draft-pilot";
const CODE_PATH = "/code-repair";
const ROLE_CODE_PATH = "/role-code-case";
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
  let smokeInvoked = false;
  let draftInvoked = false;
  let codeInvoked = false;
  let roleCodeInvoked = false;
  const roleBatchesInvoked = new Set();
  const microBatchesInvoked = new Set();
  return {
    async fetch(request, env) {
      const url = new URL(request.url);
      if (request.method !== "POST" || ![SOURCE_PATH, ROLES_PATH, MICRO_PATH, DRAFT_PATH, CODE_PATH, ROLE_CODE_PATH].includes(url.pathname) || url.search ||
          !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
        return reply(404, { classification: "local_route_unavailable" });
      }
      // Wrangler/workerd may represent a zero-byte POST as an empty stream.
      // Admit only a declared zero-length body; reject content-bearing posts.
      let roleBatch = null;
      let micro = null;
      let codeIndex = null;
      let roleCode = null;
      if(url.pathname===ROLE_CODE_PATH){
        const n=Number(request.headers.get("content-length"));
        if(!Number.isInteger(n)||n<1||n>65||
           request.headers.get("content-type")!=="application/json")
          return reply(400,{classification:"role_code_selector_rejected"});
        let v;
        try{v=await request.json();}catch{return reply(400,{classification:"role_code_selector_rejected"});}
        if(!v||typeof v!=="object"||Array.isArray(v)||
           Object.keys(v).sort().join(",")!=="model_index,task_index"||
           !Number.isInteger(v.model_index)||v.model_index<0||v.model_index>1||
           !Number.isInteger(v.task_index)||v.task_index<0||v.task_index>4)
          return reply(400,{classification:"role_code_selector_rejected"});
        roleCode=v;
      }else if(url.pathname===CODE_PATH){
        const size=Number(request.headers.get("content-length"));
        if(!Number.isInteger(size)||size<1||size>36||
           request.headers.get("content-type")!=="application/json")
          return reply(400,{classification:"fixed_code_selector_invalid"});
        let v;
        try{v=await request.json();}catch{return reply(400,{classification:"fixed_code_selector_invalid"});}
        if(!v||typeof v!=="object"||Array.isArray(v)||
           Object.keys(v).join(",")!=="model_index"||
           !Number.isInteger(v.model_index)||v.model_index<0||v.model_index>1)
          return reply(400,{classification:"fixed_code_selector_invalid"});
        codeIndex=v.model_index;
      }else if(url.pathname===MICRO_PATH){
        const size=Number(request.headers.get("content-length"));
        if(!Number.isInteger(size)||size<1||size>60||
           request.headers.get("content-type")!=="application/json")
          return reply(400,{classification:"micro_selector_invalid"});
        let candidate;
        try{candidate=await request.json();}catch{return reply(400,{classification:"micro_selector_invalid"});}
        if(!candidate||typeof candidate!=="object"||Array.isArray(candidate)||
           Object.keys(candidate).sort().join(",")!=="batch,model_index"||
           !Number.isInteger(candidate.batch)||candidate.batch<0||candidate.batch>5||
           !Number.isInteger(candidate.model_index)||candidate.model_index<0||candidate.model_index>1)
          return reply(400,{classification:"micro_selector_invalid"});
        micro=candidate;
      }else if(url.pathname===ROLES_PATH) {
        const size=Number(request.headers.get("content-length"));
        if(!Number.isInteger(size)||size<1||size>30||
           request.headers.get("content-type")!=="application/json")
          return reply(400,{classification:"role_batch_selector_not_allowed"});
        let selector;
        try {selector=await request.json();}catch{return reply(400,{classification:"role_batch_selector_invalid"});}
        if(!selector||Object.keys(selector).length!==1||
          !Number.isInteger(selector.batch)||selector.batch< -2||selector.batch>99)
          return reply(400,{classification:"role_batch_selector_invalid"});
        roleBatch=selector.batch;
      } else if (request.body !== null && request.headers.get("content-length") !== "0") {
        return reply(400, { classification: "request_body_not_allowed" });
      }
      if ((roleCode===null && codeIndex===null && micro===null && roleBatch === null && (smokeInvoked || draftInvoked || codeInvoked || roleCodeInvoked || roleBatchesInvoked.size || microBatchesInvoked.size)) ||
          (roleCode!==null&&(smokeInvoked||draftInvoked||codeInvoked||roleCodeInvoked||roleBatchesInvoked.size||microBatchesInvoked.size)) ||
          (codeIndex!==null && (smokeInvoked || draftInvoked || codeInvoked || roleBatchesInvoked.size || microBatchesInvoked.size)) ||
          (url.pathname===DRAFT_PATH && (smokeInvoked || draftInvoked || roleBatchesInvoked.size || microBatchesInvoked.size)) ||
          (micro!==null && (smokeInvoked || draftInvoked || roleBatchesInvoked.size ||
             microBatchesInvoked.has(micro.model_index+":"+micro.batch) ||
             microBatchesInvoked.size>=5)) ||
          (roleBatch !== null && (smokeInvoked || draftInvoked || microBatchesInvoked.size ||
             roleBatchesInvoked.has(roleBatch) || roleBatchesInvoked.size >= 5)))
        return reply(409, {classification:"caller_batch_limit_or_replay"});
      if (typeof env?.NVIDIA_SERVICE?.fetch !== "function") {
        return reply(503, { classification: "remote_service_binding_missing" });
      }
      // One request per local dev session, even if upstream errors.
      if(roleCode!==null)roleCodeInvoked=true;
      else if(codeIndex!==null)codeInvoked=true;
      else if(url.pathname===DRAFT_PATH)draftInvoked=true;
      else if(micro!==null)microBatchesInvoked.add(micro.model_index+":"+micro.batch);
      else if (roleBatch === null) smokeInvoked = true;
      else roleBatchesInvoked.add(roleBatch);
      try {
        const upstream = await env.NVIDIA_SERVICE.fetch(roleCode!==null
          ? new Request(DESTINATION.replace("/internal/diagnostics/nvidia",
                "/internal/diagnostics/nvidia-role-code"),{
              method:"POST",headers:{"Content-Type":"application/json"},
              body:JSON.stringify(roleCode)
            })
          : codeIndex!==null
          ? new Request(DESTINATION.replace("/internal/diagnostics/nvidia",
               "/internal/diagnostics/nvidia-code-repair"),{
              method:"POST",headers:{"Content-Type":"application/json"},
              body:JSON.stringify({model_index:codeIndex})
            })
          : url.pathname===DRAFT_PATH
          ? new Request(DESTINATION.replace("/internal/diagnostics/nvidia",
              "/internal/diagnostics/nvidia-draft-pilot"), {method:"POST"})
          : micro!==null
          ? new Request(DESTINATION.replace("/internal/diagnostics/nvidia",
              "/internal/diagnostics/nvidia-micro"), {
              method:"POST",headers:{"Content-Type":"application/json"},
              body:JSON.stringify(micro)
            })
          : roleBatch===null
          ? new Request(DESTINATION, { method: "POST" })
          : new Request(DESTINATION.replace("/internal/diagnostics/nvidia",
              "/internal/diagnostics/nvidia-roles"), {
              method:"POST",headers:{"Content-Type":"application/json"},
              body:JSON.stringify({batch:roleBatch})
          }));
        const value = await upstream.json();
        if(roleCode!==null){
          const safe=sanitizeCodeRoleReceipt(value);
          if(!safe||safe.model_index!==roleCode.model_index||
             safe.task_index!==roleCode.task_index)
            return reply(502,{classification:"untrusted_synthetic_role_code"});
          return reply(upstream.ok?200:502,safe);
        }
        if(codeIndex!==null){
          const sanitized=sanitizeCodeReceipt(value);
          if(!sanitized||sanitized.model_index!==codeIndex)
            return reply(502,{classification:"untrusted_fixed_code_receipt"});
          return reply(upstream.ok?200:502,sanitized);
        }
        if(url.pathname===DRAFT_PATH){
          const sanitized=sanitizeDraftReceipt(value);
          if(!sanitized)return reply(502,{classification:"invalid_fixed_draft_receipt"});
          return reply(upstream.ok?200:502,sanitized);
        }
        if(micro!==null){
          const sanitized=sanitizeMicroReceipt(value);
          if(!sanitized||sanitized.model_index!==micro.model_index||
             sanitized.batch!==micro.batch)
            return reply(502,{classification:"unexpected_micro_receipt"});
          return reply(upstream.ok?200:502,sanitized);
        }
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
