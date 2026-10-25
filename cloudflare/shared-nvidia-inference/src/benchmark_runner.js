// Fixed, synthetic-only role evaluation. The caller supplies an authenticated
// request function; this module never handles secrets or accepts user prompts.
import { TASKS, eligibleChatModel, modelId, request as makeTaskRequest, scored } from "./benchmark_fixtures.js";

export const SCHEMA = "commandcenter.nvidia_synthetic_roles.v1";
export const BATCH_SIZE = 2;
export const MAX_REQUESTS_PER_BATCH = 1 + BATCH_SIZE * TASKS.length;
const API = "https://integrate.api.nvidia.com";
const MAX_MODELS = 150;
const MAX_DURATION_MS = 120000;
// Fixed first-wave assistant challengers; after these, evaluate every other
// catalog-listed chat candidate in stable order. Never hardcode a winner.
const PRIORITY = [
  "openai/gpt-oss-20b",
  "nvidia/nemotron-3.5-lightning-30b-a3b",
  "nvidia/nemotron-3.5-bolt-e4b",
  "nvidia/nemotron-3-super-120b-a12b",
  "nvidia/nemotron-3-ultra-550b-a55b",
  "nvidia/llama-3.1-nemotron-ultra-253b-v1",
  "nvidia/nemotron-nano-3-30b-a3b",
  "mistralai/mistral-large-2-instruct",
  "meta/llama-3.3-70b-instruct"
];
function orderedCandidates(ids) {
 const chat=ids.filter(eligibleChatModel);
 return [
   ...PRIORITY.filter(id=>chat.includes(id)),
   ...chat.filter(id=>!PRIORITY.includes(id))
 ];
}


function httpStatus(n) { return Number.isInteger(n) && n >= 100 && n <= 599 ? n : null; }
function clock() { return Date.now(); }
function errorKind(error) {
  if (error?.name === "TimeoutError") return "timeout";
  if (error?.name === "AbortError") return "aborted";
  return "transport_error";
}
function safeReceipt(batch) {
  return { schema: SCHEMA, batch, catalog_http: null, catalog_count: null,
    catalog_model_ids: [], eligible_count: 0, eligible_model_ids: [],
    results: [], calls: 0, elapsed_ms: 0, status: "not_started",
    secret_exposed: false, prompt_exposed: false, response_exposed: false,
    household_data: false };
}

// Catalog IDs are public provider metadata and can be retained independently
// of model responses; trim to NVIDIA's bounded and verified format.
export function sanitizeModelCatalog(rows) {
  if (!Array.isArray(rows) || rows.length > 10000) throw Error("catalog_invalid");
  return [...new Set(rows.map(r => r?.id).filter(modelId))].sort().slice(0, MAX_MODELS);
}

export async function runSyntheticRoleBatch({batch, providerFetch, now=clock}) {
  if (!Number.isInteger(batch) || batch < -1 || batch > 99) throw Error("invalid_batch");
  if (typeof providerFetch !== "function") throw Error("missing_provider");
  const out = safeReceipt(batch);
  const start = now();
  try {
    out.calls++;
    const res = await providerFetch(API + "/v1/models", {method:"GET", redirect:"manual"});
    out.catalog_http = httpStatus(res?.status);
    if (out.catalog_http !== 200) { out.status = "catalog_http_error"; return out; }
    const parsed = await res.json();
    const ids = sanitizeModelCatalog(parsed?.data);
    out.catalog_count = ids.length;
    out.catalog_model_ids = ids;
    out.eligible_model_ids = orderedCandidates(ids);
    out.eligible_count = out.eligible_model_ids.length;
    if (batch === -1) { out.status = "catalog_only"; return out; }
    const chosen = out.eligible_model_ids.slice(batch * BATCH_SIZE, (batch+1) * BATCH_SIZE);
    if (!chosen.length) { out.status = "end_of_catalog"; return out; }
    for (const model of chosen) {
      const results = [];
      for (const task of TASKS) {
        if (out.calls >= MAX_REQUESTS_PER_BATCH || now()-start > MAX_DURATION_MS) {
          out.status = "limit_reached"; return out;
        }
        const begin = now();
        const row = {task, http_status:null, latency_ms:null,
                     format_valid:false, passed:false, error:null};
        try {
          out.calls++;
          const rsp = await providerFetch(API + "/v1/chat/completions", {
            method:"POST", redirect:"manual", body:JSON.stringify(makeTaskRequest(model,task))
          });
          row.latency_ms = Math.max(0,Math.min(120000,now()-begin));
          row.http_status = httpStatus(rsp?.status);
          if (row.http_status === 200) {
            const parsed = await rsp.json();
            const msg = parsed?.choices?.[0]?.message;
            row.format_valid = task === "tool_call" ?
              Array.isArray(msg?.tool_calls) : typeof msg?.content === "string";
            row.passed = scored(task,msg);
          }
        } catch(error) {
          row.error = errorKind(error);
          row.latency_ms = Math.max(0, Math.min(120000,now()-begin));
        }
        results.push(row);
        if (row.http_status === 401 || row.http_status === 429) {
          out.results.push({model, results});
          out.status = row.http_status === 401 ? "account_auth_rejected" : "rate_limited";
          return out;
        }
      }
      out.results.push({model,results});
    }
    out.status = "batch_complete";
    return out;
  } catch(error) {
    out.status = out.catalog_http === 200 ? "catalog_decode_error" : errorKind(error);
    return out;
  } finally {
    out.elapsed_ms = Math.max(0,Math.min(120000,now()-start));
  }
}
