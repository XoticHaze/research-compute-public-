// Private service-binding only. No workers.dev URL, external route or arbitrary proxy.
// This Worker does not accept user prompts, model IDs, target URLs or camera content.
// `NVIDIA_API_KEY` must be a Cloudflare account Secrets Store binding, not a plain var.
import {runSyntheticRoleBatch} from "./benchmark_runner.js";
import {runMicroWorkerBatch} from "./micro_worker_benchmark.js";
import {NvidiaProviderPacingQueue} from "./provider_pacing_queue.js";
import {runFixedDraftPilot} from "./draft_pilot_runner.js";
import {runFixedCodeRepair} from "./fixed_code_repair_runner.js";
import {runCodeRoleCase} from "./code_role_suite_runner.js";
const ORIGIN = "https://integrate.api.nvidia.com";
const MODEL = "openai/gpt-oss-20b";
const RUN_PATH = "/internal/diagnostics/nvidia";
const HEADERS = Object.freeze({ "Content-Type": "application/json" });
// Common outbound gate for catalog, role, micro-worker and fixed smoke probes.
// All private diagnostic routes within this isolate use this one queue.
const sharedNvidiaPacer = new NvidiaProviderPacingQueue({
  providerFetch: (endpoint, opts) => fetch(endpoint, opts),
});
const pacedProviderFetch = (endpoint, opts) => sharedNvidiaPacer.fetch(endpoint, opts);

function json(status, record) {
  return new Response(JSON.stringify(record), {
    status,
    headers: { ...HEADERS, "Cache-Control": "no-store" },
  });
}

function boundedStatus(value) {
  return Number.isInteger(value) && value >= 100 && value <= 599 ? value : null;
}

// Only emit fixed classifications. Error names/messages from runtimes or
// providers can contain URLs, credentials, headers or sensitive payloads.
export function classifyCatalogException(error) {
  if (error && error.name === "TimeoutError") return "timeout";
  if (error && error.name === "AbortError") return "aborted";
  if (error && error.name === "TypeError") {
    const msg = typeof error.message === "string" ? error.message.toLowerCase() : "";
    if (msg.includes("abortsignal") || msg.includes("timeout is not a function"))
      return "abort_api_unavailable";
    if (msg.includes("redirect")) return "redirect_rejected";
    if (msg.includes("fetch")) return "fetch_type_error";
    return "runtime_type_error";
  }
  return "other_runtime_exception";
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
    catalog_attempt_started: false,
    catalog_failure_stage: null,
    catalog_failure_kind: null,
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
  // Cloudflare Workers does not implement redirect: "error": it throws before
  // sending the request. Use manual for BOTH API calls so Authorization is
  // never forwarded automatically to a different host. Any actual 3xx
  // remains a non-200 provider response, not followed.
  // Separate construction/transport failures from response JSON failures.
  // This removes unsupported AbortSignal.timeout from the critical path:
  // caller has its own bounded request timeout and this fixed probe has
  // no user-selected destination, URL, model, or request body.
  let catalogResponse;
  receipt.catalog_attempt_started = true;
  try {
    catalogResponse = await doFetch(ORIGIN + "/v1/models", {
      method: "GET", headers, redirect: "manual",
    });
    receipt.calls_made++;
    receipt.catalog_http_status = boundedStatus(catalogResponse.status);
  } catch (error) {
    receipt.catalog_failure_stage = "outbound_fetch";
    receipt.catalog_failure_kind = classifyCatalogException(error);
    receipt.classification = "catalog_transport_or_response_failure";
    receipt.elapsed_ms = Math.round(performance.now() - start);
    return receipt;
  }
  if (catalogResponse.ok) {
    try {
      const value = await catalogResponse.json();
      const rows = value && Array.isArray(value.data) ? value.data : [];
      receipt.catalog_count = Math.min(rows.length, 100000);
      receipt.catalog_includes_model = rows.some(r => r && r.id === MODEL);
    } catch (error) {
      receipt.catalog_failure_stage = "catalog_json";
      receipt.catalog_failure_kind = classifyCatalogException(error);
      receipt.classification = "catalog_transport_or_response_failure";
      receipt.elapsed_ms = Math.round(performance.now() - start);
      return receipt;
    }
  }
  try {
    const result = await doFetch(ORIGIN + "/v1/chat/completions", {
      method: "POST", headers, redirect: "manual",
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
      receipt.completion_response_valid =
        typeof msg?.content === "string" && msg.content.trim().length > 0;
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
    ? (receipt.completion_response_valid ? "completion_http_200" : "completion_response_invalid")
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
    // Existing Service Binding route only; public Worker and previews remain
    // disabled. No caller-authored prompts, tool execution, or target hosts.
    // Source-owned synthetic model-role work; exact (model,task) selectors.
    // No caller-supplied input, prompt, endpoint or artifact path.
    if(request.method==="POST"&&url.pathname==="/internal/diagnostics/nvidia-role-code"&&!url.search){
      if(env.CC_NVIDIA_DIAGNOSTIC_ENABLED!=="1")return json(503,{error:"diagnostic_not_admitted"});
      const length=Number(request.headers.get("content-length"));
      if(!Number.isInteger(length)||length<1||length>65||
         request.headers.get("content-type")!=="application/json")
        return json(400,{error:"invalid_fixed_role_selector"});
      let v;
      try{v=await request.json();}catch{return json(400,{error:"invalid_fixed_role_selector"});}
      if(!v||typeof v!=="object"||Array.isArray(v)||
         Object.keys(v).sort().join(",")!=="model_index,task_index"||
         !Number.isInteger(v.model_index)||v.model_index<0||v.model_index>1||
         !Number.isInteger(v.task_index)||v.task_index<0||v.task_index>4)
        return json(400,{error:"invalid_fixed_role_selector"});
      if(typeof env.NVIDIA_API_KEY?.get!=="function")return json(503,{error:"binding_unavailable"});
      let key;
      try{key=await env.NVIDIA_API_KEY.get();}catch{return json(503,{error:"secret_unavailable"});}
      if(typeof key!=="string"||key.length<8)return json(503,{error:"secret_unavailable"});
      const authFetch=async(endpoint,options)=>{
        const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),35000);
        try{return await pacedProviderFetch(endpoint,{...options,headers:{
          "Authorization":"Bearer "+key,"Content-Type":"application/json"
        },redirect:"manual",signal:controller.signal});}
        finally{clearTimeout(timer);}
      };
      const receipt=await runCodeRoleCase({modelIndex:v.model_index,taskIndex:v.task_index,providerFetch:authFetch});
      return json(receipt.status==="candidate_unexecuted"?200:503,receipt);
    }
    // A single fixed synthetic Python patch attempt. Restricted source bytes
    // may leave this Worker only to an AST-only validator on synthetic compute.
    // No private input, arbitrary prompt, provider model, or executable code.
    if(request.method==="POST"&&url.pathname==="/internal/diagnostics/nvidia-code-repair"&&!url.search){
      if(env.CC_NVIDIA_DIAGNOSTIC_ENABLED!=="1")return json(503,{error:"diagnostic_not_admitted"});
      const n=Number(request.headers.get("content-length"));
      if(!Number.isInteger(n)||n<1||n>36||request.headers.get("content-type")!=="application/json")
        return json(400,{error:"invalid_fixed_code_selector"});
      let args;
      try{args=await request.json();}catch{return json(400,{error:"invalid_fixed_code_selector"});}
      if(!args||typeof args!=="object"||Array.isArray(args)||
        Object.keys(args).join(",")!=="model_index"||
        !Number.isInteger(args.model_index)||args.model_index<0||args.model_index>1)
        return json(400,{error:"invalid_fixed_code_selector"});
      if(typeof env.NVIDIA_API_KEY?.get!=="function")return json(503,{error:"binding_unavailable"});
      let key;
      try{key=await env.NVIDIA_API_KEY.get();}catch{return json(503,{error:"secret_unavailable"});}
      if(typeof key!=="string"||key.length<8)return json(503,{error:"secret_unavailable"});
      const authFetch=async(endpoint,options)=>{
        const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),18000);
        try{return await pacedProviderFetch(endpoint,{...options,headers:{
          "Authorization":"Bearer "+key,"Content-Type":"application/json"
        },redirect:"manual",signal:controller.signal});}
        finally{clearTimeout(timer);}
      };
      const receipt=await runFixedCodeRepair({modelIndex:args.model_index,providerFetch:authFetch});
      return json(receipt.status==="candidate_unexecuted"?200:503,receipt);
    }
    // Four fixed fictional writing tasks, no user-authored prompt or model.
    // Synthetic model text is scored privately and is NEVER returned.
    if(request.method==="POST" && url.pathname==="/internal/diagnostics/nvidia-draft-pilot" && !url.search){
      if(env.CC_NVIDIA_DIAGNOSTIC_ENABLED!=="1")return json(503,{error:"diagnostic_not_admitted"});
      if(request.body!==null && request.headers.get("content-length")!=="0")
        return json(400,{error:"fixed_empty_body_required"});
      if(typeof env.NVIDIA_API_KEY?.get!=="function")return json(503,{error:"binding_unavailable"});
      let key;
      try{key=await env.NVIDIA_API_KEY.get();}catch{return json(503,{error:"secret_unavailable"});}
      if(typeof key!=="string" || key.length<8)return json(503,{error:"secret_unavailable"});
      const authFetch=async(endpoint,options)=>{
        const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),18000);
        try{return await pacedProviderFetch(endpoint,{...options,headers:{
          "Authorization":"Bearer "+key,"Content-Type":"application/json"
        },redirect:"manual",signal:controller.signal});}
        finally{clearTimeout(timer);}
      };
      const receipt=await runFixedDraftPilot({providerFetch:authFetch});
      return json(receipt.status==="completed_not_human_reviewed"?200:503,receipt);
    }
    // Fixed 24-case, two-model synthetic micro-worker benchmark. Private Service
    // Binding only, disabled by default. No caller-supplied model or prompt.
    if(request.method==="POST" && url.pathname==="/internal/diagnostics/nvidia-micro" && !url.search){
      if(env.CC_NVIDIA_DIAGNOSTIC_ENABLED!=="1")return json(503,{error:"diagnostic_not_admitted"});
      const n=Number(request.headers.get("content-length"));
      if(!Number.isInteger(n)||n<1||n>60||
         request.headers.get("content-type")!=="application/json")
        return json(400,{error:"unsupported_fixed_micro_selector"});
      let input;
      try{input=await request.json();}catch{return json(400,{error:"invalid_fixed_micro_selector"});}
      if(!input || typeof input!=="object" || Array.isArray(input) ||
         Object.keys(input).sort().join(",")!=="batch,model_index" ||
         !Number.isInteger(input.batch)||input.batch<0||input.batch>5 ||
         !Number.isInteger(input.model_index)||input.model_index<0||input.model_index>1)
        return json(400,{error:"invalid_fixed_micro_selector"});
      if(typeof env.NVIDIA_API_KEY?.get!=="function")return json(503,{error:"binding_unavailable"});
      let key;
      try{key=await env.NVIDIA_API_KEY.get();}catch{return json(503,{error:"secret_unavailable"});}
      if(typeof key!=="string" || key.length<8)return json(503,{error:"secret_unavailable"});
      const authFetch=async(endpoint,options)=>{
        const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),18000);
        try{return await pacedProviderFetch(endpoint,{...options,headers:{
          "Authorization":"Bearer "+key,"Content-Type":"application/json"
        },redirect:"manual",signal:controller.signal});}
        finally{clearTimeout(timer);}
      };
      const receipt=await runMicroWorkerBatch({
        modelIndex:input.model_index,batch:input.batch,providerFetch:authFetch
      });
      return json(receipt.status==="batch_complete"?200:503,receipt);
    }
    if (request.method === "POST" && url.pathname === "/internal/diagnostics/nvidia-roles" && !url.search) {
      if (env.CC_NVIDIA_DIAGNOSTIC_ENABLED !== "1") return json(503, {error:"diagnostic_not_admitted"});
      const n = Number(request.headers.get("content-length"));
      if (!Number.isInteger(n) || n < 1 || n > 30 || request.headers.get("content-type") !== "application/json")
        return json(400, {error:"unsupported_selector"});
      let selector;
      try { selector = await request.json(); } catch {return json(400,{error:"invalid_selector"});}
      if (!selector || Object.keys(selector).length !== 1 ||
          !Number.isInteger(selector.batch) || selector.batch < -2 || selector.batch > 99)
        return json(400,{error:"invalid_selector"});
      if (typeof env.NVIDIA_API_KEY?.get !== "function") return json(503,{error:"binding_unavailable"});
      let key;
      try { key = await env.NVIDIA_API_KEY.get(); } catch {return json(503,{error:"secret_unavailable"});}
      if (typeof key !== "string" || key.length < 8) return json(503,{error:"secret_unavailable"});
      // Cloudflare supports AbortController, not AbortSignal.timeout().
      // Limit each fixed synthetic request so one inaccessible/slow model
      // cannot monopolize a whole bounded batch. Never follow redirects.
      const authFetch = async (endpoint, options) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 18000);
        try {
          return await pacedProviderFetch(endpoint, {...options,
            headers: {"Authorization":"Bearer " + key, "Content-Type":"application/json"},
            redirect:"manual", signal:controller.signal});
        } finally {
          clearTimeout(timer);
        }
      };
      const receipt = await runSyntheticRoleBatch({batch:selector.batch,providerFetch:authFetch});
      return json(receipt.status === "batch_complete" || receipt.status === "catalog_only" ? 200 : 503, receipt);
    }
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
    const result = await probeNvidia(env, pacedProviderFetch);
    return json(result.classification === "completion_http_200" ? 200 : 503, result);
  },
};
