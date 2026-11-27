// An inert, exact one-release PVE7 capability INSIDE the existing maintenance authority.
// No new Worker, signing key, service, ingress, or approval delegation. The existing
// independent Cloudflare owner must separately review any cross-domain key use and
// turn on a single pinned request. All defaults are disabled. Not a deployment grant.
export const PVE7_DOMAIN = 'commandcenter.pve7.release.apply.v1\0';
export const PVE7_SCHEMA = 'commandcenter.pve7.scoped_release_grant.v1';
export const PVE7_ENVELOPE = 'commandcenter.pve7.existing_authority_envelope.v1';
export const PVE7_SCOPE = 'pve7.release.apply.v1';
export const PVE7_SOURCE = '662acaf0b0568d9692a969c970634f6a4d129e47';
export const PVE7_FILES = Object.freeze({
  'pve-host-rescue-executor.py': Object.freeze({
    sha256: 'd2fe72e9c570c22e0817477a8ef6aed471269f3c89261177d88bd223694bb0fe',
    predecessor_sha256: 'd2fe72e9c570c22e0817477a8ef6aed471269f3c89261177d88bd223694bb0fe',
  }),
  'pve-host-rescue-mailbox.py': Object.freeze({
    sha256: 'b8371da266f98eb59760598a9d4b78b9bae37196e250b7ebc9523e18db929891',
    predecessor_sha256: '45e8726628eba7fe794a84653ecdc61349b9732d247a58d993df2f6e74bcff57',
  }),
});
const SIG_FORMAT = 'ecdsa-p256-sha256-p1363';
const id = s => typeof s === 'string' && /^[A-Za-z0-9-]{1,48}$/.test(s);
const hex = (s,n) => typeof s === 'string' && s.length === n && /^[a-f0-9]+$/.test(s);
const exact = (o,k) => o!==null && typeof o==='object' && !Array.isArray(o) &&
  Object.keys(o).length===k.length && k.every(x=>Object.hasOwn(o,x));
const fail = what => {throw new Error(what)};
const need = (yes,what) => {if(!yes)fail(what)};
const UTC = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/;

export function canonicalPve7(v) {
  if (Array.isArray(v)) return '['+v.map(canonicalPve7).join(',')+']';
  if (v && typeof v === 'object') return '{'+Object.keys(v).sort()
    .map(k=>JSON.stringify(k)+':'+canonicalPve7(v[k])).join(',')+'}';
  return JSON.stringify(v);
}

export function validatePve7Grant(g, nowMs=Date.now()) {
  need(exact(g,['schema','node_id','operation','release_id','request_id',
     'source_sha','not_before','expires_at','approval_sha256','files']), 'grant_shape');
  need(g.schema===PVE7_SCHEMA && g.node_id==='pve7' && g.operation===PVE7_SCOPE
    && g.source_sha===PVE7_SOURCE && id(g.release_id) && id(g.request_id), 'grant_scope');
  need(hex(g.approval_sha256,64), 'approval_pin');
  need(typeof g.not_before==='string' && UTC.test(g.not_before)
    && typeof g.expires_at==='string' && UTC.test(g.expires_at), 'grant_time_format');
  const start=Date.parse(g.not_before), end=Date.parse(g.expires_at);
  need([start,end,nowMs].every(Number.isFinite) && start<=nowMs && nowMs<end
    && end<=nowMs+1200000 && end-start>0 && end-start<=1200000
    && start>=nowMs-1200000, 'grant_window');
  const names=Object.keys(PVE7_FILES);
  need(exact(g.files,names), 'grant_files');
  for(const name of names){
    const part=g.files[name],p=PVE7_FILES[name];
    need(exact(part,['sha256','predecessor_sha256']) && part.sha256===p.sha256
      && part.predecessor_sha256===p.predecessor_sha256,'grant_digest');
  }
  return g;
}

// Source of approved values is ONLY the protected account-owner Worker config,
// never caller-supplied Git payload, HTTP body, deployment request or file path.
export function buildOwnerApprovedPve7Grant(env, nowMs=Date.now()) {
  need(env && env.PVE7_RELEASE_SIGNING_ENABLED==='1', 'pve7_signing_disabled');
  need(env.PVE7_APPROVED_SOURCE_SHA===PVE7_SOURCE, 'pve7_source_not_owner_pinned');
  need(hex(env.PVE7_OWNER_APPROVAL_SHA256,64), 'owner_approval_absent');
  need(typeof env.PVE7_EXPECTED_AUTHORITY_KEY_ID==='string'
    && /^sha256:[a-f0-9]{64}$/.test(env.PVE7_EXPECTED_AUTHORITY_KEY_ID), 'owner_signer_pin_absent');
  const grant={schema:PVE7_SCHEMA,node_id:'pve7',operation:PVE7_SCOPE,
    release_id:env.PVE7_RELEASE_ID,request_id:env.PVE7_REQUEST_ID,
    source_sha:PVE7_SOURCE,not_before:env.PVE7_NOT_BEFORE,
    expires_at:env.PVE7_EXPIRES_AT,approval_sha256:env.PVE7_OWNER_APPROVAL_SHA256,
    files:Object.fromEntries(Object.entries(PVE7_FILES).map(([name,p])=>[name,{...p}]))};
  validatePve7Grant(grant,nowMs);
  return {grant,signer_key_id:env.PVE7_EXPECTED_AUTHORITY_KEY_ID};
}

export function validatePve7SigningRequest(request,env,nowMs=Date.now()) {
  need(exact(request,['grant','signer_key_id']), 'pve7_signing_request_shape');
  const owner=buildOwnerApprovedPve7Grant(env,nowMs);
  need(canonicalPve7(request)===canonicalPve7(owner), 'owner_pinned_request_mismatch');
  return owner;
}

export function pve7Payload(grant,nowMs=Date.now()) {
  validatePve7Grant(grant,nowMs);
  return new TextEncoder().encode(PVE7_DOMAIN+canonicalPve7(grant));
}
// Defense-in-depth at the service-binding boundary. The root materializer
// still independently verifies the P-256 signature and exact trust policy.
// A valid-looking response from a Durable Object must never widen the
// owner-pinned request identity, scope, source or file set.
export function validatePve7IssuedEnvelope(envelope, approved) {
  need(exact(envelope,['schema','grant','signer_key_id','signature_format','signature_b64']),
       'pve7_issued_envelope_shape');
  need(envelope.schema===PVE7_ENVELOPE && envelope.signature_format===SIG_FORMAT
       && envelope.signer_key_id===approved.signer_key_id,
       'pve7_issued_envelope_identity');
  need(canonicalPve7(envelope.grant)===canonicalPve7(approved.grant),
       'pve7_issued_envelope_grant_mismatch');
  need(typeof envelope.signature_b64==='string' &&
       /^[A-Za-z0-9+/]{86}==$/.test(envelope.signature_b64),
       'pve7_issued_signature_shape');
  return envelope;
}

export {SIG_FORMAT as PVE7_SIG_FORMAT};
