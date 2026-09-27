import { WorkerEntrypoint } from "cloudflare:workers";
const TARGET_WORKER = "reference-release-broker-v1";
const SOURCE_REPOSITORY = "XoticHaze/research-compute-public-";
const SOURCE_PREFIX = "cloudflare/reference-release-broker/src/";
const SOURCE_FILES = ["index.js", "intent.js", "ticket.js"];
const SCHEMA = "reference-release-maintenance-v1";
const ISSUER = "private-maintenance-authority-v1";
const SIGNATURE_FORMAT = "ecdsa-p256-sha256-p1363";

function json(body, status=200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type":"application/json; charset=utf-8",
      "cache-control":"no-store",
      "content-security-policy":"default-src 'none'",
      "x-content-type-options":"nosniff",
    },
  });
}

function bytesToB64(bytes) {
  let out = "";
  for (let i=0; i<bytes.length; i+=0x8000) out += String.fromCharCode(...bytes.subarray(i, i+0x8000));
  return btoa(out);
}
function b64ToBytes(value) {
  const raw = atob(String(value || ""));
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}
function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).sort().map(k => JSON.stringify(k)+":"+canonical(value[k])).join(",") + "}";
  }
  return JSON.stringify(value);
}
async function sha256Hex(value) {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return [...digest].map(b => b.toString(16).padStart(2,"0")).join("");
}
function validateSourceSha(value) {
  const text = String(value || "");
  if (!/^[0-9a-f]{40}$/.test(text)) throw new Error("candidate_source_sha_rejected");
  return text;
}
function validateVersion(value, field) {
  const text = String(value || "");
  if (!/^[0-9a-f-]{36}$/.test(text)) throw new Error(field + "_rejected");
  return text;
}
function validateBrokerKey(value) {
  const text = String(value || "");
  if (!/^sha256:[0-9a-f]{64}$/.test(text)) throw new Error("expected_broker_key_id_rejected");
  return text;
}

async function fetchCandidateHashes(sourceSha) {
  const hashes = {};
  for (const name of SOURCE_FILES) {
    const url = "https://raw.githubusercontent.com/" + SOURCE_REPOSITORY + "/" +
      sourceSha + "/" + SOURCE_PREFIX + name;
    const response = await fetch(url, {headers:{"user-agent":"reference-maintenance-authority-v1"}});
    if (!response.ok) throw new Error("candidate_fetch_" + name + "_" + response.status);
    hashes[name] = await sha256Hex(await response.text());
  }
  return {
    files: hashes,
    package_sha256: await sha256Hex(canonical(hashes)),
  };
}

export class AuthorityState {
  constructor(state) {
    this.state = state;
    this.ready = state.blockConcurrencyWhile(async () => {
      let key = await state.storage.get("signing_key");
      if (!key) {
        const pair = await crypto.subtle.generateKey(
          {name:"ECDSA", namedCurve:"P-256"},
          true,
          ["sign","verify"]
        );
        const privateJwk = await crypto.subtle.exportKey("jwk", pair.privateKey);
        const publicRaw = new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey));
        key = {
          private_jwk: privateJwk,
          public_b64: bytesToB64(publicRaw),
          key_id: "sha256:" + await sha256Hex(publicRaw),
          created_at: new Date().toISOString(),
        };
        await state.storage.put("signing_key", key);
      }
      this.key = key;
    });
  }

  async importPrivate() {
    await this.ready;
    return crypto.subtle.importKey(
      "jwk", this.key.private_jwk,
      {name:"ECDSA", namedCurve:"P-256"},
      false,
      ["sign"]
    );
  }

  async importPublic() {
    await this.ready;
    return crypto.subtle.importKey(
      "raw", b64ToBytes(this.key.public_b64),
      {name:"ECDSA", namedCurve:"P-256"},
      false,
      ["verify"]
    );
  }

  async fetch(request) {
    await this.ready;
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/public-key") {
      return json({public_b64:this.key.public_b64, key_id:this.key.key_id});
    }
    if (request.method === "POST" && url.pathname === "/sign") {
      const claims = await request.json().catch(()=>null);
      validateClaims(claims);
      const payload = new TextEncoder().encode(canonical(claims));
      const privateKey = await this.importPrivate();
      const signature = new Uint8Array(await crypto.subtle.sign(
        {name:"ECDSA", hash:"SHA-256"}, privateKey, payload
      ));
      if (signature.length !== 64) throw new Error("signature_format_unexpected");
      return json({
        payload_b64: bytesToB64(payload),
        signature_b64: bytesToB64(signature),
        signer_key_id: this.key.key_id,
        signature_format: SIGNATURE_FORMAT,
      });
    }
    if (request.method === "POST" && url.pathname === "/verify") {
      const wrapper = await request.json().catch(()=>null);
      const verified = await verifyWrapper(wrapper, await this.importPublic(), this.key.key_id);
      return json({ok:true, manifest:verified, key_id:this.key.key_id});
    }
    return json({error:"not_found"},404);
  }
}

function validateClaims(node) {
  const fields = new Set([
    "schema","issuer","maintenance_id","target_worker","candidate_source_sha",
    "files","candidate_package_sha256","expected_current_version","rollback_version",
    "expected_broker_key_id","not_before","expires_at"
  ]);
  if (!node || Object.keys(node).length !== fields.size ||
      Object.keys(node).some(k => !fields.has(k))) throw new Error("maintenance_fields_rejected");
  if (node.schema !== SCHEMA || node.issuer !== ISSUER) throw new Error("maintenance_schema_rejected");
  if (node.target_worker !== TARGET_WORKER) throw new Error("maintenance_target_rejected");
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(String(node.maintenance_id || ""))) {
    throw new Error("maintenance_id_rejected");
  }
  validateSourceSha(node.candidate_source_sha);
  validateVersion(node.expected_current_version, "expected_current_version");
  validateVersion(node.rollback_version, "rollback_version");
  if (node.rollback_version !== node.expected_current_version) throw new Error("rollback_version_rejected");
  validateBrokerKey(node.expected_broker_key_id);
  if (!node.files || Object.keys(node.files).sort().join(",") !== [...SOURCE_FILES].sort().join(",")) {
    throw new Error("maintenance_files_rejected");
  }
  for (const name of SOURCE_FILES) {
    if (!/^[0-9a-f]{64}$/.test(String(node.files[name] || ""))) throw new Error("maintenance_file_hash_rejected");
  }
  if (!/^[0-9a-f]{64}$/.test(String(node.candidate_package_sha256 || ""))) {
    throw new Error("maintenance_package_sha_rejected");
  }
  const now = Math.floor(Date.now()/1000);
  const notBefore = Number(node.not_before), expires = Number(node.expires_at);
  if (!Number.isInteger(notBefore) || !Number.isInteger(expires) ||
      now < notBefore || expires <= now || expires - notBefore > 900) {
    throw new Error("maintenance_time_rejected");
  }
}

async function verifyWrapper(wrapper, publicKey, expectedKeyId) {
  const fields = new Set(["payload_b64","signature_b64","signer_key_id","signature_format"]);
  if (!wrapper || Object.keys(wrapper).length !== fields.size ||
      Object.keys(wrapper).some(k => !fields.has(k))) throw new Error("maintenance_wrapper_rejected");
  if (wrapper.signature_format !== SIGNATURE_FORMAT || wrapper.signer_key_id !== expectedKeyId) {
    throw new Error("maintenance_signer_rejected");
  }
  const payload = b64ToBytes(wrapper.payload_b64);
  const signature = b64ToBytes(wrapper.signature_b64);
  if (signature.length !== 64) throw new Error("maintenance_signature_rejected");
  const ok = await crypto.subtle.verify(
    {name:"ECDSA", hash:"SHA-256"}, publicKey, signature, payload
  );
  if (!ok) throw new Error("maintenance_signature_rejected");
  const text = new TextDecoder().decode(payload);
  const node = JSON.parse(text);
  if (canonical(node) !== text) throw new Error("maintenance_canonicalization_rejected");
  validateClaims(node);
  return node;
}

async function stateStub(env) {
  if (!env.AUTHORITY_STATE) throw new Error("authority_state_unconfigured");
  return env.AUTHORITY_STATE.get(env.AUTHORITY_STATE.idFromName("root"));
}

async function authorize(request, env) {
  const body = await request.json().catch(()=>null);
  if (!body || Object.keys(body).sort().join(",") !==
      ["candidate_source_sha","expected_broker_key_id","expected_current_version"].sort().join(",")) {
    throw new Error("authorize_request_rejected");
  }
  const sourceSha = validateSourceSha(body.candidate_source_sha);
  const current = validateVersion(body.expected_current_version, "expected_current_version");
  const brokerKey = validateBrokerKey(body.expected_broker_key_id);

  const liveKey = await fetch("https://reference-release-broker-v1.slenderiq.workers.dev/v1/public-key", {
    headers:{"cache-control":"no-cache"}
  });
  if (!liveKey.ok) throw new Error("broker_public_key_unavailable");
  const liveKeyNode = await liveKey.json();
  if (liveKeyNode.key_id !== brokerKey) throw new Error("broker_public_key_mismatch");

  const hashes = await fetchCandidateHashes(sourceSha);
  const now = Math.floor(Date.now()/1000);
  const claims = {
    schema: SCHEMA,
    issuer: ISSUER,
    maintenance_id: "m_" + crypto.randomUUID().replaceAll("-",""),
    target_worker: TARGET_WORKER,
    candidate_source_sha: sourceSha,
    files: hashes.files,
    candidate_package_sha256: hashes.package_sha256,
    expected_current_version: current,
    rollback_version: current,
    expected_broker_key_id: brokerKey,
    not_before: now - 5,
    expires_at: now + 300,
  };
  const stub = await stateStub(env);
  const signed = await stub.fetch("https://authority-state/sign", {
    method:"POST",
    headers:{"content-type":"application/json"},
    body:JSON.stringify(claims),
  });
  if (!signed.ok) throw new Error("authority_sign_rejected");
  return signed.json();
}

async function apply(request, env) {
  if (!env.MAINTAINER) throw new Error("maintainer_binding_unconfigured");
  const signed = await authorize(request, env);
  const response = await env.MAINTAINER.fetch(new Request("https://maintainer/v1/maintain", {
    method:"POST",
    headers:{"content-type":"application/json"},
    body:JSON.stringify({manifest:signed}),
  }));
  const text = await response.text();
  return new Response(text, {status:response.status, headers:{"content-type":"application/json","cache-control":"no-store"}});
}

export default class ReferenceMaintenanceAuthority extends WorkerEntrypoint {
  async fetch() {
    return json({error:"not_found"}, 404);
  }

  async health() {
    const stub = await stateStub(this.env);
    const key = await stub.fetch("https://authority-state/public-key");
    if (!key.ok) throw new Error("authority_key_unavailable");
    const node = await key.json();
    return {
      ok:true,
      service:"reference-maintenance-authority-v1",
      key_id:node.key_id,
      public_ingress:false,
      github_deploy_authority:false,
      host_dependency:false,
    };
  }

  async publicKey() {
    const stub = await stateStub(this.env);
    const response = await stub.fetch("https://authority-state/public-key");
    if (!response.ok) throw new Error("authority_key_unavailable");
    return response.json();
  }

  async verifyManifest(wrapper) {
    const stub = await stateStub(this.env);
    const response = await stub.fetch("https://authority-state/verify", {
      method:"POST",
      headers:{"content-type":"application/json"},
      body:JSON.stringify(wrapper),
    });
    const body = await response.json();
    if (!response.ok || body?.ok !== true || !body?.manifest) {
      throw new Error("maintenance_manifest_rejected");
    }
    return body.manifest;
  }

  async authorize(input) {
    const request = new Request("https://authority/authorize", {
      method:"POST",
      headers:{"content-type":"application/json"},
      body:JSON.stringify(input),
    });
    return authorize(request, this.env);
  }

  async apply(input) {
    if (!this.env.MAINTAINER) throw new Error("maintainer_binding_unconfigured");
    const signed = await this.authorize(input);
    return this.env.MAINTAINER.maintain(signed);
  }
}
