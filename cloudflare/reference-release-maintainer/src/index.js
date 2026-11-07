import { WorkerEntrypoint } from "cloudflare:workers";
const TARGET_WORKER = "reference-release-broker-v1";
const EXPECTED_NEUTRAL_ACCOUNT_ID = "b33595eb85f346b0d1bf201810b4499a";
// The protected Cloudflare account is a public resource identifier, NOT a
// credential. A broker-only Editor token or stale original-account binding
// must never switch this maintainer to another account by config accident.
const SOURCE_REPOSITORY = "XoticHaze/research-compute-public-";
const SOURCE_FILES = ["index.js", "intent.js", "ticket.js", "placement.js", "signer_vault.js"];
const SOURCE_PREFIX = "cloudflare/reference-release-broker/src/";

function brokerOrigin(env) {
  const value = String(env?.BROKER_PUBLIC_ORIGIN || "");
  let url;
  try { url = new URL(value); } catch { throw new Error("broker_origin_unconfigured"); }
  if (
    url.protocol !== "https:" || url.port || url.username || url.password
    || url.pathname !== "/" || url.search || url.hash
    || url.hostname !== 'reference-release-broker-v1.shared-compute-neutral-authorization.workers.dev'
  ) throw new Error("broker_origin_rejected");
  return url.origin;
}


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
// Never accept a label-only broker signer proof during independent maintenance.
// The complete uncompressed on-curve P-256 public point must produce the pinned
// key fingerprint. No secret, worker response body, or raw key is logged.
async function verifiedBrokerKeyId(node) {
  try {
    const encoded = node?.public_b64;
    if (typeof encoded !== 'string' || encoded.length > 128) throw new Error('key_shape');
    const raw = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
    if (raw.length !== 65 || raw[0] !== 4) throw new Error('key_point');
    if (btoa(String.fromCharCode(...raw)) !== encoded) throw new Error('key_encoding');
    await crypto.subtle.importKey('raw', raw, {name:'ECDSA', namedCurve:'P-256'}, false, ['verify']);
    const digest = 'sha256:' + await sha256Hex(raw);
    if (node.key_id !== digest) throw new Error('key_fingerprint');
    return digest;
  } catch {
    throw new Error('broker_public_key_mismatch');
  }
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
// Script upload endpoints accept only version_id='latest' for inherited bindings.
// A reviewed release MUST inherit from the exact 100%-deployed version, NOT a
// possibly newer unpublished upload. Use the documented Workers version API.
async function brokerWorkerIdentity(env, token) {
  const response = await cfFetch(env, token, "/workers/workers/" + TARGET_WORKER);
  const node = await response.json().catch(()=>({}));
  const worker = node?.result;
  if (!response.ok || node?.success !== true
      || worker?.name !== TARGET_WORKER
      || !/^[0-9a-f]{32}$/.test(String(worker?.id || ""))) {
    throw new Error("broker_worker_identity_unverified");
  }
  return worker.id;
}
function utf8Base64(value) {
  const raw = new TextEncoder().encode(value);
  let text = "";
  for (let i=0; i<raw.length; i+=0x8000) {
    text += String.fromCharCode(...raw.subarray(i,i+0x8000));
  }
  return btoa(text);
}
// Maintenance may inherit ONLY exact, independently attested bindings from
// the currently 100%-deployed broker version. Do not drop the new signer DO,
// silently revert to legacy JWK, or carry an initial-issue approval forever.
async function approvedBrokerBindings(env, token, workerId, current) {
  const response = await cfFetch(env, token,
    "/workers/workers/" + workerId + "/versions/" + current);
  const body = await response.json().catch(()=>({}));
  const info = body?.result;
  if (!response.ok || body?.success !== true || info?.id !== current) {
    throw new Error("active_broker_version_readback_rejected");
  }
  const rows = Array.isArray(info.bindings) ? info.bindings : info.resources?.bindings;
  if (!Array.isArray(rows)) throw new Error("active_broker_bindings_unavailable");
  const map = new Map();
  for (const row of rows) {
    if (!row || typeof row.name !== "string" || map.has(row.name)) {
      throw new Error("active_broker_bindings_invalid");
    }
    map.set(row.name, row);
  }
  const required = [
    "AUTHORITY_PUBLIC_B64", "GRANT_LEDGER", "ALLOWED_JOB_WORKFLOW_REF",
    "ALLOWED_JOB_WORKFLOW_SHA", "MAX_ADMISSION_SECONDS",
    "MAX_INTENT_SECONDS",
  ];
  for (const name of required) {
    if (!map.has(name)) throw new Error("active_broker_required_binding_missing");
  }
  if (map.get("GRANT_LEDGER")?.class_name !== "GrantLedger") {
    throw new Error("grant_ledger_identity_unverified");
  }
  // Only one release-signing mode. A changed source cannot activate signer
  // vault on a version that was previously JWK-based or vice versa.
  const vault = map.has("BROKER_SIGNER_VAULT");
  const legacy = map.has("BROKER_SIGNING_PRIVATE_JWK");
  if (vault === legacy) throw new Error("active_broker_signer_ambiguous");
  if (map.has("BROKER_FIRST_SEAL_APPROVAL_ID")
      || map.has("BROKER_FIRST_SEAL_APPROVAL_NOT_AFTER")) {
    throw new Error("first_issue_approval_not_retired");
  }
  if (vault) {
    if (map.get("BROKER_SIGNER_VAULT")?.class_name !== "BrokerSignerVault"
        || map.get("BROKER_SIGNER_MODE")?.text !== "vault-v1") {
      throw new Error("vault_binding_identity_unverified");
    }
    required.push("BROKER_SIGNER_VAULT", "BROKER_SIGNER_MODE");
  } else {
    required.push("BROKER_SIGNING_PRIVATE_JWK");
    if (map.has("BROKER_SIGNER_MODE")) {
      if (map.get("BROKER_SIGNER_MODE")?.text !== "legacy-jwk-v1") {
        throw new Error("legacy_signer_mode_mismatch");
      }
      required.push("BROKER_SIGNER_MODE");
    }
  }
  return {
    vault,
    inherited:required.map(name => ({
      type:"inherit", name, version_id:current,
    })),
  };
}

async function uploadVersion(env, token, manifest, contents, workerId, bindingPlan) {
  if (!/^[0-9a-f]{32}$/.test(String(workerId || ""))) {
    throw new Error("broker_worker_identity_unverified");
  }
  const metadata = {
    main_module:"index.js",
    compatibility_date:"2026-09-25",
    annotations:{
      "workers/message":"reference broker maintenance " + manifest.maintenance_id,
      "workers/tag":manifest.candidate_source_sha,
    },
    bindings:bindingPlan.inherited,
    modules:SOURCE_FILES.map(name=>({
      name,content_type:"application/javascript+module",
      content_base64:utf8Base64(contents[name]),
    })),
    exports:{
      GrantLedger:{type:"durable-object",storage:"sqlite",state:"created"},
      ...(bindingPlan.vault ? {BrokerSignerVault:{
        type:"durable-object",storage:"sqlite",state:"created",
      }} : {}),
    }
  };
  // deploy=false is explicit: uploading source never promotes it. The separately
  // signed exact-version deployment below remains the only promotion point.
  const response = await cfFetch(
    env, token, "/workers/workers/" + workerId + "/versions?deploy=false",
    {method:"POST",body:JSON.stringify(metadata)}
  );
  const body = await response.json().catch(()=>({}));
  if (!response.ok || body?.success !== true || !/^[0-9a-f-]{8,64}$/.test(String(body?.result?.id || ""))) {
    throw new Error("version_upload_rejected_" + response.status);
  }
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
async function verifyLive(env, manifest) {
  const health = await fetch(brokerOrigin(env) + "/healthz", {headers:{"cache-control":"no-cache"}});
  if (!health.ok || (await health.json()).ok !== true) throw new Error("postdeploy_health_rejected");
  const key = await fetch(brokerOrigin(env) + "/v1/public-key", {headers:{"cache-control":"no-cache"}});
  if (!key.ok) throw new Error("postdeploy_key_mismatch");
  let observed;
  try { observed = await verifiedBrokerKeyId(await key.json()); }
  catch { throw new Error("postdeploy_key_mismatch"); }
  if (observed !== manifest.expected_broker_key_id) throw new Error("postdeploy_key_mismatch");
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
  if (String(env.CLOUDFLARE_ACCOUNT_ID) !== EXPECTED_NEUTRAL_ACCOUNT_ID) {
    throw new Error("neutral_cloudflare_account_mismatch");
  }
  if (!wrapper || typeof wrapper !== "object") throw new Error("request_rejected");
  const manifest = await verifyManifest(env, wrapper);
  // Resolve every non-mutating precondition BEFORE consuming the unique
  // independently signed manifest. A stale version, missing token, or bad
  // immutable source must not burn authorization without any deployment.
  const token = await env.BROKER_EDITOR_TOKEN.get();
  if (!token) throw new Error("broker_editor_token_unavailable");
  const current = await activeVersion(env, token);
  if (current !== manifest.expected_current_version) throw new Error("current_version_mismatch");
  const workerId = await brokerWorkerIdentity(env, token);
  const bindingPlan = await approvedBrokerBindings(env, token, workerId, current);
  const contents = await fetchCandidate(manifest);

  // The only authoritative mutation boundary begins here. Consume the
  // one-shot manifest before version upload; retries after this point require
  // a NEW signed approval, never reusing stale authorization.
  const id = env.MAINTENANCE_LEDGER.idFromName(manifest.maintenance_id);
  const consume = await env.MAINTENANCE_LEDGER.get(id).fetch("https://maintenance-ledger/consume", {
    method:"POST", headers:{"content-type":"application/json"},
    body:JSON.stringify({maintenance_id:manifest.maintenance_id})
  });
  if (!consume.ok) throw new Error("maintenance_replay_rejected");

  let newVersion = null, promotionAttempted = false;
  try {
    // Separate authorized changes can race a candidate fetch or upload.
    // Refuse to overwrite an unexpectedly active version. These checks
    // are after one-time consumption, so a race requires fresh approval.
    if (await activeVersion(env, token) !== current) {
      throw new Error("preupload_version_mismatch");
    }
    newVersion = await uploadVersion(env, token, manifest, contents, workerId, bindingPlan);
    if (await activeVersion(env, token) !== current) {
      throw new Error("prepromotion_version_mismatch");
    }
    // Important: the HTTP POST can mutate Cloudflare successfully and THEN
    // return an error/timeout. Mark the attempt BEFORE calling it.
    promotionAttempted = true;
    await deployVersion(env, token, newVersion, "reference broker maintenance promote");
    if (await activeVersion(env, token) !== newVersion) {
      throw new Error("postdeploy_version_mismatch");
    }
    await verifyLive(env, manifest);
    return json({
      ok:true, schema:"reference-release-maintenance-receipt-v1",
      maintenance_id:manifest.maintenance_id, source_sha:manifest.candidate_source_sha,
      previous_version:current, deployed_version:newVersion,
      rollback_performed:false, secret_material_included:false
    });
  } catch (error) {
    if (promotionAttempted) {
      // Reconcile ambiguous deploy POST outcomes before attempting rollback.
      // Never clobber a third-party/unexpected version via stale approval.
      let observed;
      try { observed = await activeVersion(env, token); }
      catch { throw new Error("maintenance_rollback_state_unavailable"); }
      if (observed !== current && observed !== newVersion) {
        throw new Error("maintenance_unexpected_active_version");
      }
      if (observed === newVersion) {
        try {
          await deployVersion(env, token, manifest.rollback_version, "reference broker automatic rollback");
          if (await activeVersion(env, token) !== current) {
            throw new Error("rollback_version_mismatch");
          }
        } catch {
          throw new Error("maintenance_failed_and_rollback_failed");
        }
      }
      // Restoring the EXACT deployed version can be proved independently
      // even if the prior broker was PRESEAL (no healthy signer yet).
      // Never misreport rollback as a successfully sealed live broker.
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

  async brokerState() {
    if (!this.env.BROKER_EDITOR_TOKEN || typeof this.env.BROKER_EDITOR_TOKEN.get !== "function") {
      throw new Error("broker_editor_binding_unconfigured");
    }
    if (!this.env.CLOUDFLARE_ACCOUNT_ID) throw new Error("cloudflare_account_unconfigured");
    if (String(this.env.CLOUDFLARE_ACCOUNT_ID) !== EXPECTED_NEUTRAL_ACCOUNT_ID) {
      throw new Error("neutral_cloudflare_account_mismatch");
    }
    const token = await this.env.BROKER_EDITOR_TOKEN.get();
    if (!token) throw new Error("broker_editor_token_unavailable");
    return {
      ok: true,
      target_worker: TARGET_WORKER,
      version_id: await activeVersion(this.env, token),
      secret_material_included: false,
    };
  }

  async maintain(wrapper) {
    return maintainManifest(wrapper, this.env);
  }
}
