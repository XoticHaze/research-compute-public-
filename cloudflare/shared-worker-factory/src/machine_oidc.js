// Reuse the existing Cloudflare fleet-authority GitHub OIDC signature pattern.
// Fixed public issuer/JWKS, repo+workflow+ref+event+run verification only.
// This is an identity check, NEVER sufficient for mutating factory operations.
const ISSUER = 'https://token.actions.githubusercontent.com';
const JWKS = ISSUER+'/.well-known/jwks';
const AUD = 'commandcenter-cloudflare-factory-readonly-v1';
const REPO = 'XoticHaze/research-compute-public-';
const REF = 'refs/heads/main';
const WORKFLOW = REPO+'/.github/workflows/cc-factory-machine-readonly-r1.yml@'+REF;
const RUN = /^[0-9]{4,20}$/;
const SHA40 = /^[a-f0-9]{40}$/;

function decodeB64url(text) {
  if (!/^[A-Za-z0-9_-]+$/.test(text) || text.length > 12000)
    throw Error('oidc_encoding_rejected');
  const raw=atob(text.replace(/-/g,'+').replace(/_/g,'/')
    .padEnd(Math.ceil(text.length/4)*4,'='));
  return Uint8Array.from(raw,c=>c.charCodeAt(0));
}
function parseJson(part) {
  const result=JSON.parse(new TextDecoder().decode(decodeB64url(part)));
  if (!result || typeof result!=='object' || Array.isArray(result))
    throw Error('oidc_json_rejected');
  return result;
}
export async function verifyFactoryMachineOidc(jwt, requestedRunId) {
  if (typeof jwt!=='string' || jwt.length < 100 || jwt.length > 16000 ||
      !RUN.test(String(requestedRunId))) throw Error('oidc_request_rejected');
  const parts=jwt.split('.');
  if(parts.length!==3) throw Error('oidc_compact_invalid');
  let header,claims;
  try {header=parseJson(parts[0]);claims=parseJson(parts[1]);}
  catch {throw Error('oidc_jwt_invalid');}
  if(header.alg!=='RS256' || typeof header.kid!=='string' ||
     !/^[A-Za-z0-9._:-]{1,160}$/.test(header.kid) ||
     header.typ && header.typ!=='JWT') throw Error('oidc_header_rejected');
  if(claims.iss!==ISSUER) throw Error('oidc_issuer_rejected');
  const audience=Array.isArray(claims.aud)?claims.aud:[claims.aud];
  if(audience.length!==1 || audience[0]!==AUD)
    throw Error('oidc_audience_rejected');
  if(claims.repository!==REPO || claims.ref!==REF ||
     claims.workflow_ref!==WORKFLOW ||
     claims.sub!=='repo:'+REPO+':ref:'+REF ||
     claims.event_name!=='workflow_dispatch' ||
     claims.repository_visibility!=='public' ||
     claims.runner_environment!=='github-hosted' ||
     String(claims.run_id)!==String(requestedRunId) ||
     !SHA40.test(String(claims.sha||'')) ||
     !SHA40.test(String(claims.workflow_sha||'')) ||
     !RUN.test(String(claims.run_attempt||''))) throw Error('oidc_claims_rejected');
  const now=Math.floor(Date.now()/1000),exp=Number(claims.exp),
    iat=Number(claims.iat),nbf=claims.nbf===undefined?iat:Number(claims.nbf);
  if(![exp,iat,nbf].every(Number.isInteger) ||
     exp<now-30 || nbf>now+30 || iat>now+30 ||
     iat<now-600 || exp-iat>600 || exp<=iat)
    throw Error('oidc_time_rejected');
  const reply=await fetch(JWKS,{headers:{accept:'application/json'},
    redirect:'error',cf:{cacheTtl:300,cacheEverything:true}});
  if(!reply.ok) throw Error('oidc_jwks_unavailable');
  const keys=await reply.json();
  const jwk=Array.isArray(keys?.keys)?keys.keys.find(k=>
    k?.kid===header.kid && k.kty==='RSA' &&
    (!k.alg || k.alg==='RS256') && (!k.use || k.use==='sig')):null;
  if(!jwk) throw Error('oidc_jwk_rejected');
  let key;
  try {key=await crypto.subtle.importKey('jwk',jwk,
    {name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);}
  catch {throw Error('oidc_key_import_rejected');}
  const signature=decodeB64url(parts[2]);
  const bytes=new TextEncoder().encode(parts[0]+'.'+parts[1]);
  const verified=await crypto.subtle.verify('RSASSA-PKCS1-v1_5',key,signature,bytes);
  if(!verified) throw Error('oidc_signature_rejected');
  return {repository:REPO,ref:REF,workflow_ref:WORKFLOW,run_id:String(requestedRunId),
    run_attempt:String(claims.run_attempt),source_sha:claims.sha,
    workflow_sha:claims.workflow_sha,identity_verified:true};
}
export const FACTORY_MACHINE_IDENTITY={
  expected_repository:REPO,expected_ref:REF,expected_workflow_ref:WORKFLOW,
  expected_audience:AUD,default_trust:'IDENTITY_ONLY_NO_MUTATION_AUTHORITY'
};
