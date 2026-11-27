// Independently administered neutral Worker permit. Git proposals cannot mint it.
const SHA = /^[0-9a-f]{40}$/;
const GEN = /^r[0-9a-f]{12}$/;
const ID = /^[0-9a-f]{32}$/;
const RID = /^ccpi2-([0-9a-f]{64})-[0-9a-f]{16}$/;
const UTC = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/;
const FIELDS = ['schema','permit_id','request_id','manifest_sha256','source_sha','expected_release','not_before','expires_at'];
function permitForRequest(env, request, p, now) {
  if (env.PI_OWNER_SCHEDULED_ROOT_ENABLED !== '1'
      || env.PI_OWNER_SIGNER_ENABLED !== '1'
      || env.PI_OWNER_NORMAL_RELEASE_ENABLED !== '1') throw Error('scheduled_root_not_admitted');
  if(!p||Array.isArray(p)||Object.keys(p).length!==FIELDS.length
      ||!FIELDS.every(k=>Object.hasOwn(p,k))
      ||p.schema!=='commandcenter.pi.scheduled_root_permit.v2'
      ||!FIELDS.every(k=>typeof p[k]==='string')
      ||!RID.test(p.request_id)||RID.exec(p.request_id)[1]!==p.manifest_sha256
      ||!ID.test(p.permit_id)||!SHA.test(p.source_sha)||!GEN.test(p.expected_release)
      ||!UTC.test(p.not_before)||!UTC.test(p.expires_at)) throw Error('scheduled_root_permit_invalid');
  const start=Date.parse(p.not_before), end=Date.parse(p.expires_at);
  if(!Number.isFinite(start)||!Number.isFinite(end)||start>now||end<=now
      ||new Date(start).toISOString()!==p.not_before.replace('Z','.000Z')
      ||new Date(end).toISOString()!==p.expires_at.replace('Z','.000Z')
      ||end-start>24*3600000) throw Error('scheduled_root_permit_not_fresh');
  const requestEnd=Date.parse(request?.expires_at);
  if(!Number.isFinite(requestEnd)||requestEnd<=now||requestEnd>end
      ||request?.schema!=='commandcenter.pi.release_request.v1'
      ||request.action!=='pi.release.apply'||request.node_id!=='cc-pi4'
      ||request.source_repo!=='XoticHaze/CommandCenter'||request.source_sha!==p.source_sha
      ||request.expected_release!==p.expected_release||request.request_id!==p.request_id)
    throw Error('scheduled_root_request_not_permitted');
  return p;
}

const DOMAIN = 'commandcenter.pi.independent_release_permit.v1\u0000';
const canonical = p => JSON.stringify(Object.fromEntries(Object.keys(p).sort().map(k=>[k,p[k]])))+'\n';
function decode(value, len) {
  if(typeof value!=='string'||value.length>256||!/^[A-Za-z0-9+/]+={0,2}$/.test(value)) throw Error('independent_permit_encoding');
  const bytes=Uint8Array.from(atob(value),c=>c.charCodeAt(0));
  if(bytes.length!==len||btoa(String.fromCharCode(...bytes))!==value) throw Error('independent_permit_encoding');
  return bytes;
}
export async function validateIndependentIssuerIdentity(spki_b64, fingerprint, rootFingerprint) {
  const spki=decode(spki_b64,44);
  const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',spki))]
    .map(x=>x.toString(16).padStart(2,'0')).join('');
  if(!/^[0-9a-f]{64}$/.test(String(rootFingerprint||''))||
     !/^[0-9a-f]{64}$/.test(String(fingerprint||''))||actual!==fingerprint||fingerprint===rootFingerprint)
    throw Error('independent_permit_issuer_not_admitted');
  return crypto.subtle.importKey('spki',spki,'Ed25519',false,['verify']);
}
// Independent release reviewer signs an exact permit in a distinct domain.
// A Git queue write supplies transport only; it never confers signing authority.
export async function scheduledRootPermit(env, request, envelope = null, now = Date.now()) {
  if (envelope === null) {
    const raw=env.PI_OWNER_SCHEDULED_ROOT_PERMIT;
    if(typeof raw!=='string'||raw.length>1024) throw Error('scheduled_root_permit_missing');
    return permitForRequest(env,request,JSON.parse(raw),now);
  }
  if(!envelope||Array.isArray(envelope)||Object.keys(envelope).length!==3
      ||envelope.schema!=='commandcenter.pi.independent_release_permit.v1'
      ||!Object.hasOwn(envelope,'permit')||!Object.hasOwn(envelope,'signature_b64'))
    throw Error('independent_permit_shape');
  const p=permitForRequest(env,request,envelope.permit,now);
  const key=await validateIndependentIssuerIdentity(env.PI_OWNER_RELEASE_ISSUER_SPKI_B64,
    env.PI_OWNER_RELEASE_ISSUER_SHA256,env.PI_OWNER_ENROLLED_PUB_SHA256);
  if(!await crypto.subtle.verify('Ed25519',key,decode(envelope.signature_b64,64),
      new TextEncoder().encode(DOMAIN+canonical(p)))) throw Error('independent_permit_signature_invalid');
  return p;
}
