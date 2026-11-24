// Source-only native Static Assets transport for the existing factory.
// No public/private source retrieval, queue dispatch, token issuance or promotion.
// First admission is an isolated managed canary, NOT the neutral Studio account.
// The caller must provide verified target identity, immutable manifest and bytes.
const ACCOUNT='de1c728bdb163060d946122c857f3653';
const API='https://api.cloudflare.com/client/v4/accounts/'+ACCOUNT;
const HEX32=/^[a-f0-9]{32}$/;
const HEX64=/^[a-f0-9]{64}$/;
const TARGET='cc-app-static-assets-proof';
const MAX_FILE=2*1024*1024,MAX_TOTAL=4*1024*1024,MAX_FILES=12;
const MIME=Object.freeze({html:'text/html; charset=utf-8',css:'text/css; charset=utf-8',js:'application/javascript; charset=utf-8',json:'application/json',png:'image/png',glb:'model/gltf-binary',txt:'text/plain; charset=utf-8'});
const enc=new TextEncoder();
function requireThat(x,code){if(!x)throw Error(code);}
function safePath(p){return typeof p==='string'&&p.length<=180&&/^\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$/.test(p)&&!p.includes('..');}
function extension(p){return p.split('.').at(-1).toLowerCase();}
function base64(bytes){let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s);}
async function digest(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');}
function target(t){
  requireThat(t?.account_id===ACCOUNT&&t.worker_name===TARGET&&HEX32.test(t.worker_id),'static_asset_target_denied');
  requireThat(t.identity_verified===true&&t.factory_managed===true&&t.ingress_disabled===true&&t.previews_disabled===true,'static_asset_target_preflight_required');
}
export async function prepareAssetManifest(t,entries,readBytes){
  target(t);
  requireThat(Array.isArray(entries)&&entries.length>0&&entries.length<=MAX_FILES,'asset_count_limit');
  requireThat(typeof readBytes==='function','asset_reader_missing');
  let total=0;const manifest=Object.create(null),parts=new Map();
  for(const e of entries){
    requireThat(e&&Object.keys(e).sort().join(',')==='bytes,path,sha256'&&safePath(e.path)&&Object.hasOwn(MIME,extension(e.path))&&HEX64.test(e.sha256)&&Number.isInteger(e.bytes)&&e.bytes>0&&e.bytes<=MAX_FILE,'invalid_asset_manifest_entry');
    requireThat(!Object.hasOwn(manifest,e.path),'duplicate_asset_path');
    total+=e.bytes;requireThat(total<=MAX_TOTAL,'asset_total_limit');
    const bytes=await readBytes(e.path,e.bytes);
    requireThat(bytes instanceof Uint8Array&&bytes.length===e.bytes&&await digest(bytes)===e.sha256,'asset_sha256_mismatch');
    // Cloudflare's documented content ID: SHA256(base64(bytes) + extension), 32 hex.
    const data=base64(bytes),hash=(await digest(enc.encode(data+extension(e.path)))).slice(0,32);
    manifest[e.path]={hash,size:e.bytes};
    const prior=parts.get(hash);
    requireThat(!prior||prior.sha256===e.sha256&&prior.mime===MIME[extension(e.path)],'asset_content_id_collision');
    parts.set(hash,{data,mime:MIME[extension(e.path)],sha256:e.sha256});
  }
  requireThat(Object.hasOwn(manifest,'/index.html'),'asset_index_required');
  return {manifest,parts,total};
}
function jwtLike(x){return typeof x==='string'&&x.length<=16384&&/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(x);}
async function request(fetcher,path,token,body,allowed){
  // Credentials only go to this fixed account's two Cloudflare endpoints.
  requireThat(typeof token==='string'&&token.length>=20,'asset_credential_unavailable');
  const headers={authorization:'Bearer '+token,accept:'application/json'};
  if(!(body instanceof FormData))headers['content-type']='application/json';
  const res=await fetcher(API+path,{method:'POST',redirect:'manual',headers,body:body instanceof FormData?body:JSON.stringify(body)});
  requireThat(allowed.includes(res.status),'asset_api_http_'+res.status);
  // Do not include raw API error bodies or upload JWTs in diagnostics.
  const raw=await res.text();requireThat(raw.length<=65536,'asset_api_response_limit');
  let j;try{j=JSON.parse(raw);}catch{throw Error('asset_api_json_invalid');}
  requireThat(j?.success===true&&j.result&&typeof j.result==='object','asset_api_result_invalid');
  return {status:res.status,result:j.result};
}
export async function uploadAssetSet(t,entries,readBytes,admin,fetcher=fetch){
  const {manifest,parts,total}=await prepareAssetManifest(t,entries,readBytes);
  const init=await request(fetcher,'/workers/scripts/'+TARGET+'/assets-upload-session',admin,{manifest},[200,201]);
  const {jwt,buckets}=init.result;
  requireThat(jwtLike(jwt)&&Array.isArray(buckets)&&buckets.length<=MAX_FILES,'asset_upload_session_invalid');
  const seen=new Set();
  // Validate the entire provider plan before sending any asset bytes.
  for(const bucket of buckets){
    requireThat(Array.isArray(bucket)&&bucket.length>0&&bucket.length<=MAX_FILES,'asset_bucket_invalid');
    for(const h of bucket){requireThat(HEX32.test(h)&&parts.has(h)&&!seen.has(h),'asset_bucket_unknown_or_duplicate');seen.add(h);}
  }
  let completion=buckets.length===0?jwt:null;
  for(let i=0;i<buckets.length;i++){
    const form=new FormData();
    for(const h of buckets[i]){
      const x=parts.get(h);form.append(h,new Blob([x.data],{type:x.mime}),h);
    }
    const r=await request(fetcher,'/workers/assets/upload?base64=true',jwt,form,[200,201]);
    if(i===buckets.length-1){requireThat(r.status===201&&jwtLike(r.result.jwt),'asset_completion_missing');completion=r.result.jwt;}
    else requireThat(r.status===200,'asset_completion_early');
  }
  requireThat(jwtLike(completion),'asset_completion_invalid');
  // Returned only to same runtime caller. Never serialize this object in a receipt.
  return {completion,asset_count:entries.length,asset_bytes:total,uploaded_hash_count:seen.size};
}
export function staticVersionMetadata(completion,sourceDigest){
  requireThat(jwtLike(completion)&&HEX64.test(sourceDigest),'static_version_metadata_invalid');
  // Mandatory Worker-first authorization. No public ingress or deployment here.
  return {main_module:'worker.mjs',compatibility_date:'2026-11-18',bindings:[{type:'assets',name:'ASSETS'}],assets:{jwt:completion,config:{run_worker_first:true,not_found_handling:'404-page',html_handling:'none'}},annotations:{'workers/tag':'cc-static-'+sourceDigest}};
}
export function staticReceipt(result){
  requireThat(result&&Number.isInteger(result.asset_count)&&Number.isInteger(result.asset_bytes)&&Number.isInteger(result.uploaded_hash_count),'static_receipt_invalid');
  return {asset_count:result.asset_count,asset_bytes:result.asset_bytes,uploaded_hash_count:result.uploaded_hash_count,asset_upload_completed:true,version_staged:false,production_promoted:false,bearer_returned:false};
}
