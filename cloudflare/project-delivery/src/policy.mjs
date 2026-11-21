// Product-neutral, fail-closed content gateway. No Cloudflare Admin APIs or token issuance.
export const SCHEMA = 'commandcenter.cloudflare.project_delivery.v1';
export const DELIVERY_ROOT = 'apps.lifelatelycounseling.com';
export const CONTROL_HOST = `release.${DELIVERY_ROOT}`;
export const STUDIO_HOST = 'studio.lifelatelycounseling.com';
const ID = /^[a-f0-9]{32}$/;
const SHA = /^[a-f0-9]{64}$/;
const PROJECT = /^[a-z][a-z0-9-]{1,38}[a-z0-9]$/;
const FILE = /^\/[a-zA-Z0-9][a-zA-Z0-9._/-]{0,220}$/;
const EXTS = new Set(['html','js','mjs','css','json','glb','gltf','stl','3mf','png','jpg','jpeg','svg','webp','woff2','txt','pdf','zip','wasm','ico','webmanifest']);
const RESERVED = new Set(['release','ha','gateway-ops','www','root','api','admin','reference-release-broker-v1','reference-release-maintainer-v1','reference-maintenance-authority-v1','research-compute-public','ccpi-owner-cloudflare-authority','pi-owner','ccpi-owner','access','cloudflare','operator']);
export const DEFAULT_HOST_POLICY=Object.freeze({roots:[DELIVERY_ROOT],exact:{[STUDIO_HOST]:'incomeengine-3d-studio'}});
export function hostPolicy(env){
  if(!env)return DEFAULT_HOST_POLICY; // pure local tests; production always supplies an env
  let roots,exact;
  try{roots=JSON.parse(env.ALLOWED_APP_ROOTS_JSON);exact=JSON.parse(env.EXACT_APP_HOSTS_JSON)}
  catch{throw Error('host_policy_missing')}
  if(!Array.isArray(roots)||roots.length<1||roots.length>6||!roots.every(r=>typeof r==='string'&&/^apps\.[a-z0-9-]+(\.[a-z0-9-]+){1,6}$/.test(r)))throw Error('host_roots_rejected');
  if(!roots.includes((env.CONTROL_HOSTNAME||'').replace(/^release\./,''))||env.CONTROL_HOSTNAME!=='release.'+ (env.CONTROL_HOSTNAME||'').replace(/^release\./,''))throw Error('controller_host_rejected');
  if(!exact||typeof exact!=='object'||Array.isArray(exact)||Object.keys(exact).length>15||
     !Object.entries(exact).every(([h,p])=>typeof h==='string'&&/^[a-z0-9-]+(\.[a-z0-9-]+){2,7}$/.test(h)&&PROJECT.test(p)&&!RESERVED.has(p)))throw Error('host_exceptions_rejected');
  return {roots:Object.freeze([...roots]),exact:Object.freeze({...exact})};
}
export function validProject(project){return typeof project==='string'&&PROJECT.test(project)&&!RESERVED.has(project)}
export function validHost(host,project,policy=DEFAULT_HOST_POLICY){
  if(typeof host!=='string'||!validProject(project))return false;
  return policy.exact?.[host]===project || policy.roots?.some(root=>host===`${project}.${root}`);
}
export function validHostSlot(host,policy=DEFAULT_HOST_POLICY){
  return typeof host==='string'&&(Object.hasOwn(policy.exact||{},host)||
    policy.roots?.some(root=>host.endsWith('.'+root)&&host.split('.').length===root.split('.').length+1));
}
export function validPath(path) {
  if (typeof path !== 'string' || !FILE.test(path) || path.includes('..') || path.includes('/./') || path.includes('//') || path.includes('\\') || path.includes('%')) return false;
  const ext=path.split('.').pop().toLowerCase();return EXTS.has(ext);
}
export function validateManifest(m, now = Math.floor(Date.now()/1000), policy=DEFAULT_HOST_POLICY) {
  if (!m || typeof m!=='object' || Array.isArray(m)) throw Error('manifest_missing');
  const keys=['schema','request_id','project_id','release_id','hostname','access_aud','expires_at','files'];
  if(Object.keys(m).sort().join(',')!==keys.sort().join(',') || m.schema!==SCHEMA ||
     !ID.test(m.request_id) || !ID.test(m.release_id) || !validHost(m.hostname,m.project_id,policy) ||
     typeof m.access_aud !== 'string' || m.access_aud.length < 8 || m.access_aud.length > 256 ||
     !Number.isInteger(m.expires_at)||m.expires_at<now||m.expires_at>now+300)throw Error('manifest_header_rejected');
  if(!Array.isArray(m.files)||m.files.length<1||m.files.length>128)throw Error('manifest_files_rejected');
  let sum=0;const paths=new Set();
  for(const f of m.files){
    if(!f || typeof f!=='object' || Object.keys(f).sort().join(',')!=='bytes,path,sha256' ||
       !validPath(f.path) || paths.has(f.path) || !SHA.test(f.sha256) ||
       !Number.isInteger(f.bytes) || f.bytes<1 || f.bytes>20_000_000)throw Error('manifest_file_rejected');
    paths.add(f.path);sum+=f.bytes;
  }
  if(sum>120_000_000)throw Error('manifest_oversized');
  return Object.freeze({...m,files:m.files.map(f=>Object.freeze({...f}))});
}
export function validateActivation(a, now = Math.floor(Date.now()/1000),policy=DEFAULT_HOST_POLICY){
  if(!a || typeof a!=='object' || Array.isArray(a) ||
     Object.keys(a).sort().join(',')!=='expected_previous,expires_at,hostname,project_id,release_id,request_id,schema' ||
     a.schema!==SCHEMA || !ID.test(a.request_id)||!ID.test(a.release_id)||
     !validHost(a.hostname,a.project_id,policy)||
     !(a.expected_previous===null||ID.test(a.expected_previous))||
     !Number.isInteger(a.expires_at)||a.expires_at<now||a.expires_at>now+300)
    throw Error('activation_rejected');
  return a;
}
export const isId=x=>typeof x==='string'&&ID.test(x);
export const isSha=x=>typeof x==='string'&&SHA.test(x);
export function contentType(path){
 const s=path.split('.').pop().toLowerCase();
 return ({html:'text/html; charset=utf-8',js:'text/javascript; charset=utf-8',mjs:'text/javascript; charset=utf-8',css:'text/css; charset=utf-8',json:'application/json',glb:'model/gltf-binary',gltf:'model/gltf+json',stl:'model/stl','3mf':'model/3mf',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',svg:'image/svg+xml',webp:'image/webp',woff2:'font/woff2',txt:'text/plain; charset=utf-8',pdf:'application/pdf',zip:'application/zip',wasm:'application/wasm',ico:'image/x-icon',webmanifest:'application/manifest+json'})[s]||'application/octet-stream';
}
