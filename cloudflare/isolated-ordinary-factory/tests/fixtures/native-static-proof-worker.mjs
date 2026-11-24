// Synthetic native static asset proof. No private project data.
const HOST='cc-app-static-assets-proof.cc-ordinary-deployments.workers.dev';
const dec=new TextDecoder(), enc=new TextEncoder();
const deny=status=>new Response(null,{status,headers:{'cache-control':'private, no-store'}});
function b64(s){
  if(typeof s!=='string'||!s.length||!/^[-_A-Za-z0-9]+$/.test(s))throw Error('token');
  const b=s.replace(/-/g,'+').replace(/_/g,'/').padEnd(Math.ceil(s.length/4)*4,'=');
  return Uint8Array.from(atob(b),x=>x.charCodeAt(0));
}
export async function authorize(token,env,fetcher=fetch,now=Math.floor(Date.now()/1000)){
  if(typeof token!=='string'||token.length>16384)return false;
  const issuer=env.ACCESS_ISSUER;
  if(typeof issuer!=='string'||!/^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/.test(issuer))return false;
  if(typeof env.ACCESS_AUD!=='string'||! /^[a-f0-9]{64}$/i.test(env.ACCESS_AUD))return false;
  const allowed=JSON.parse(env.ACCESS_ALLOWED_EMAILS_JSON||'null');
  if(!Array.isArray(allowed)||allowed.length!==1||typeof allowed[0]!=='string')return false;
  const p=token.split('.');if(p.length!==3)return false;
  const h=JSON.parse(dec.decode(b64(p[0]))), c=JSON.parse(dec.decode(b64(p[1])));
  if(h.alg!=='RS256'||typeof h.kid!=='string'||!h.kid||h.kid.length>128)return false;
  if(c.iss!==issuer||!(Array.isArray(c.aud)?c.aud:[c.aud]).includes(env.ACCESS_AUD))return false;
  if(typeof c.email!=='string'||c.email.trim().toLowerCase()!==allowed[0])return false;
  if(!Number.isFinite(c.iat)||!Number.isFinite(c.exp)||c.exp<=now-30||c.iat>now+30||
    (c.nbf!==undefined&&(!Number.isFinite(c.nbf)||c.nbf>now+30)))return false;
  const r=await fetcher(issuer+'/cdn-cgi/access/certs',{redirect:'manual',headers:{accept:'application/json'}});
  if(!r.ok)return false;
  const data=await r.json();
  const k=Array.isArray(data.keys)&&data.keys.find(x=>x.kid===h.kid&&x.kty==='RSA'&&x.use!=='enc');
  if(!k)return false;
  const key=await crypto.subtle.importKey('jwk',k,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);
  return crypto.subtle.verify('RSASSA-PKCS1-v1_5',key,b64(p[2]),enc.encode(p[0]+'.'+p[1]));
}
export default {async fetch(request,env){
  const u=new URL(request.url);
  if(u.hostname!==HOST||!env.ASSETS)return deny(403);
  if(!['GET','HEAD'].includes(request.method))return deny(405);
  try{if(!await authorize(request.headers.get('Cf-Access-Jwt-Assertion'),env))return deny(403);}catch{return deny(403);}
  const path=u.pathname==='/'?'/index.html':u.pathname;
  if(!['/index.html','/proof.txt'].includes(path))return deny(404);
  const r=await env.ASSETS.fetch(new Request(new URL(path,u),{method:request.method}));
  if(!r.ok)return deny(404);
  const headers=new Headers(r.headers);headers.set('cache-control','private, no-store');
  headers.set('x-content-type-options','nosniff');headers.set('x-robots-tag','noindex, nofollow, noarchive');
  return new Response(request.method==='HEAD'?null:r.body,{status:r.status,headers});
}};
