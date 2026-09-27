import { WorkerEntrypoint } from "cloudflare:workers";
const TARGET_WORKER = "reference-release-broker-v1";
const SOURCE_REPOSITORY = "XoticHaze/research-compute-public-";
const SOURCE_FILES = ["index.js", "intent.js", "ticket.js"];
const SOURCE_PREFIX = "cloudflare/reference-release-broker/src/";

function json(body, status=200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "content-security-policy": "default-src 'none'",
      "x-content-type-options": "nosniff",
    },
  });
}
function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).sort().map(k => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
  }
  return JSON.stringify(value);
}
async function sha256Hex(value) {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return [...digest].map(b => b.toString(16).padStart(2,"0")).join("");
}
async function verifyManifest(env, wrapper) {
  if (!env.MAINTENANCE_AUTHORITY) throw new Error("maintenance_authority_binding_unconfigured");
  const manifest = await env.MAINTENANCE_AUTHORITY.verifyManifest(wrapper);
  if (!manifest || typeof manifest !== "object") throw new Error("maintenance_manifest_rejected");
  return manifest;
}
async function cfFetch(env, token, path, init={}) {
  const headers = new Headers(init.headers || {});
  headers.set("authorization", "Bearer " + token);
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) headers.set("content-type","application/json");
  return fetch("https://api.cloudflare.com/client/v4/accounts/" + env.CLOUDFLARE_ACCOUNT_ID + path, {...init, headers});
}
async function activeVersion(env, token) {
  const response = await cfFetch(env, token, "/workers/scripts/" + TARGET_WORKER + "/deployments");
  if (!response.ok) throw new Error("deployment_list_http_" + response.status);
  const body = await response.json();
  const deployments = body?.result?.deployments || body?.result || [];
  if (!Array.isArray(deployments) || deployments.length < 1) throw new Error("deployment_list_empty");
  const deployment = deployments[0];
  if (!Array.isArray(deployment.versions) || deployment.versions.length !== 1 ||
      Number(deployment.versions[0].percentage) !== 100) throw new Error("deployment_not_single_version");
  return String(deployment.versions[0].version_id || "");
}
async function fetchCandidate(manifest) {
  const contents = {}, hashes = {};
  for (const name of SOURCE_FILES) {
    const url = "https://raw.githubusercontent.com/" + SOURCE_REPOSITORY + "/" +
      manifest.candidate_source_sha + "/" + SOURCE_PREFIX + name;
    const response = await fetch(url, {headers:{"user-agent":"reference-release-maintainer-v1"}});
    if (!response.ok) throw new Error("candidate_fetch_" + name + "_" + response.status);
    const text = await response.text();
    const digest = await sha256Hex(text);
    if (digest !== manifest.files[name]) throw new Error("candidate_file_hash_rejected_" + name);
    contents[name] = text; hashes[name] = digest;
  }
  if (await sha256Hex(canonical(hashes)) !== manifest.candidate_package_sha256) {
    throw new Error("candidate_package_hash_rejected");
  }
  return contents;
}
async function uploadVersion(env, token, manifest, contents) {
  const metadata = {
    main_module:"index.js",
    compatibility_date:"2026-09-25",
    annotations:{
      "workers/message":"reference broker maintenance " + manifest.maintenance_id,
      "workers/commit_sha":manifest.candidate_source_sha,
      "workers/repository_url":"https://github.com/" + SOURCE_REPOSITORY,
    },
    bindings:[
      "BROKER_SIGNING_PRIVATE_JWK","AUTHORITY_PUBLIC_B64","GRANT_LEDGER",
      "ALLOWED_JOB_WORKFLOW_REF","ALLOWED_JOB_WORKFLOW_SHA",
      "MAX_ADMISSION_SECONDS","MAX_INTENT_SECONDS"
    ].map(name => ({type:"inherit", name, version_id:manifest.expected_current_version})),
    exports:{GrantLedger:{type:"durable-object", storage:"sqlite", state:"created"}}
  };
  const form = new FormData();
  form.set("metadata", new Blob([JSON.stringify(metadata)], {type:"application/json"}));
  for (const name of SOURCE_FILES) form.set(name, new Blob([contents[name]], {type:"application/javascript+module"}), name);
  const response = await cfFetch(
    env, token, "/workers/scripts/" + TARGET_WORKER + "/versions?bindings_inherit=strict",
    {method:"POST", body:form}
  );
  const body = await response.json().catch(()=>({}));
  if (!response.ok || body?.success !== true || !body?.result?.id) throw new Error("version_upload_rejected_" + response.status);
  if (body.result.exports_reconciliation?.deleted?.length) throw new Error("version_export_delete_rejected");
  return String(body.result.id);
}
async function deployVersion(env, token, versionId, message) {
  const response = await cfFetch(env, token, "/workers/scripts/" + TARGET_WORKER + "/deployments", {
    method:"POST",
    body:JSON.stringify({
      strategy:"percentage",
      versions:[{percentage:100,version_id:versionId}],
      annotations:{"workers/message":message}
    }),
  });
  const body = await response.json().catch(()=>({}));
  if (!response.ok || body?.success !== true) throw new Error("deployment_create_rejected_" + response.status);
}
async function verifyLive(manifest) {
  const health = await fetch("https://reference-release-broker-v1.slenderiq.workers.dev/healthz", {headers:{"cache-control":"no-cache"}});
  if (!health.ok || (await health.json()).ok !== true) throw new Error("postdeploy_health_rejected");
  const key = await fetch("https://reference-release-broker-v1.slenderiq.workers.dev/v1/public-key", {headers:{"cache-control":"no-cache"}});
  if (!key.ok || (await key.json()).key_id !== manifest.expected_broker_key_id) throw new Error("postdeploy_key_mismatch");
}
export class MaintenanceLedger {
  constructor(state) { this.state = state; }
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/consume") return json({error:"not_found"},404);
    const body = await request.json().catch(()=>null);
    const id = String(body?.maintenance_id || "");
    if (!/^[A-Za-z0-9_-]{16,128}$/.test(id)) return json({error:"id_rejected"},400);
    const accepted = await this.state.storage.transaction(async txn => {
      if (await txn.get("consumed")) return false;
      await txn.put("consumed",{maintenance_id:id,consumed_at:Date.now()});
      return true;
    });
    return accepted ? json({ok:true}) : json({error:"already_consumed"},409);
  }
}
async function maintainManifest(wrapper, env) {
  if (!env.MAINTENANCE_LEDGER) throw new Error("maintenance_ledger_unconfigured");
  if (!env.MAINTENANCE_AUTHORITY) throw new Error("maintenance_authority_binding_unconfigured");
  if (!env.BROKER_EDITOR_TOKEN || typeof env.BROKER_EDITOR_TOKEN.get !== "function") throw new Error("broker_editor_binding_unconfigured");
  if (!env.CLOUDFLARE_ACCOUNT_ID) throw new Error("cloudflare_account_unconfigured");
  if (!wrapper || typeof wrapper !== "object") throw new Error("request_rejected");
  const manifest = await verifyManifest(env, wrapper);
  const id = env.MAINTENANCE_LEDGER.idFromName(manifest.maintenance_id);
  const consume = await env.MAINTENANCE_LEDGER.get(id).fetch("https://maintenance-ledger/consume", {
    method:"POST", headers:{"content-type":"application/json"},
    body:JSON.stringify({maintenance_id:manifest.maintenance_id})
  });
  if (!consume.ok) throw new Error("maintenance_replay_rejected");
  const token = await env.BROKER_EDITOR_TOKEN.get();
  if (!token) throw new Error("broker_editor_token_unavailable");
  const current = await activeVersion(env, token);
  if (current !== manifest.expected_current_version) throw new Error("current_version_mismatch");
  const contents = await fetchCandidate(manifest);
  let newVersion = null, promoted = false;
  try {
    newVersion = await uploadVersion(env, token, manifest, contents);
    await deployVersion(env, token, newVersion, "reference broker maintenance promote");
    promoted = true;
    await verifyLive(manifest);
    return json({
      ok:true, schema:"reference-release-maintenance-receipt-v1",
      maintenance_id:manifest.maintenance_id, source_sha:manifest.candidate_source_sha,
      previous_version:current, deployed_version:newVersion,
      rollback_performed:false, secret_material_included:false
    });
  } catch (error) {
    if (promoted) {
      try {
        await deployVersion(env, token, manifest.rollback_version, "reference broker automatic rollback");
        await verifyLive(manifest);
      } catch {
        throw new Error("maintenance_failed_and_rollback_failed");
      }
    }
    throw error;
  }
}
export default class ReferenceReleaseMaintainer extends WorkerEntrypoint {
  async fetch() {
    return json({error:"not_found"}, 404);
  }

  async health() {
    return {
      ok:true,
      service:"reference-release-maintainer-v1",
      target_worker:TARGET_WORKER,
      public_ingress:false,
      github_deploy_authority:false,
      host_dependency:false,
    };
  }

  async maintain(wrapper) {
    return maintainManifest(wrapper, this.env);
  }
}
