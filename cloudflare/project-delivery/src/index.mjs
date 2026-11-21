// One reusable private asset delivery Worker. No Cloudflare management APIs, no credentials, no dynamic Worker creation.
import {SCHEMA,CONTROL_HOST,STUDIO_HOST,DELIVERY_ROOT,isId,isSha,validHost,validPath,validateManifest,validateActivation,contentType} from './policy.mjs';
import {verifiedOwner} from './auth.mjs';
const MAX_META=90000;
const RHEAD={'cache-control':'private, no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer','x-robots-tag':'noindex, nofollow, noarchive','cross-origin-resource-policy':'same-origin'};
function reply(obj,status=200){return new Response(JSON.stringify(obj),{status,headers:{...RHEAD,'content-type':'application/json; charset=utf-8'}})}
function no(status){return new Response(null,{status,headers:RHEAD})}
function ledger(env,host){const ns=env.RELEASE_LEDGER;if(!ns?.get||!ns?.idFromName)throw Error('ledger_missing');return ns.get(ns.idFromName('host:'+host))}
async function route(env,host,operation,body){const target=ledger(env,host);const r=await target.fetch(new Request('https://ledger.local/'+operation,{method:operation==='current'?'GET':'POST',headers:{'content-type':'application/json'},body:body?JSON.stringify(body):undefined}));if(!r.ok)throw Error('route_'+r.status);return r.json()}
async function data(r,max){const b=await r.arrayBuffer();if(b.byteLength>max)throw Error('too_large');return b}
const hex=b=>[...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('');
async function sha256(b){return hex(await crypto.subtle.digest('SHA-256',b))}
async function jsonBody(req){const raw=await data(req,MAX_META);return JSON.parse(new TextDecoder().decode(raw))}
async function controllerAuth(req,env,fetcher){
 if(!env?.CONTENT||!env.RELEASE_LEDGER||env.RELEASE_ENABLED!=='1'||!env.CONTROL_ACCESS_AUD)throw Error('controller_held');
 return verifiedOwner(req.headers.get('Cf-Access-Jwt-Assertion'),env,env.CONTROL_ACCESS_AUD,fetcher);
}
async function siteAuth(req,env,aud,fetcher){return verifiedOwner(req.headers.get('Cf-Access-Jwt-Assertion'),env,aud,fetcher)}
function jsonSameOrigin(req,u){return req.headers.get('origin')===u.origin&&req.headers.get('sec-fetch-site')==='same-origin'&&req.headers.get('content-type')==='application/json'}
async function prepare(req,env){
 const manifest=validateManifest(await jsonBody(req));
 await route(env,manifest.hostname,'claim',{request_id:manifest.request_id});
 const key='pending/'+manifest.project_id+'/'+manifest.release_id+'.json';
 if(await env.CONTENT.head(key))throw Error('release_already_exists');
 await env.CONTENT.put(key,JSON.stringify(manifest));
 return reply({schema:SCHEMA,state:'PREPARED',project_id:manifest.project_id,release_id:manifest.release_id,files:manifest.files.length,bytes:manifest.files.reduce((a,x)=>a+x.bytes,0),bearer_exposed:false});
}
async function upload(req,env,u){
 const parts=u.pathname.split('/').slice(3);const [project,releaseId,digest]=parts;
 if(parts.length!==3||!isId(releaseId)||!isSha(digest)||!validHost(project+'.'+DELIVERY_ROOT,project)&&!(project==='incomeengine-3d-studio'))throw Error('bad_upload_target');
 const pending=await env.CONTENT.get('pending/'+project+'/'+releaseId+'.json');if(!pending)throw Error('no_prepared_release');
 const manifest=JSON.parse(await pending.text());const expected=manifest.files.find(f=>f.sha256===digest);if(!expected)throw Error('file_not_manifested');
 if(manifest.expires_at<Math.floor(Date.now()/1000)-1800)throw Error('expired_pending_release');
 const length=Number(req.headers.get('content-length')||0);if(length>expected.bytes)throw Error('bad_size');
 const bytes=await data(req,expected.bytes);if(bytes.byteLength!==expected.bytes||await sha256(bytes)!==digest)throw Error('hash_mismatch');
 const key='blobs/'+digest;
 if(!(await env.CONTENT.head(key)))await env.CONTENT.put(key,bytes);
 return reply({schema:SCHEMA,state:'BLOB_VERIFIED',sha256:digest,bytes:expected.bytes});
}
async function activate(req,env){
 const a=validateActivation(await jsonBody(req));
 const key='pending/'+a.project_id+'/'+a.release_id+'.json';const obj=await env.CONTENT.get(key);if(!obj)throw Error('not_prepared');
 const manifest=JSON.parse(await obj.text());if(manifest.hostname!==a.hostname||manifest.project_id!==a.project_id||manifest.release_id!==a.release_id)throw Error('identity_mismatch');
 for(const f of manifest.files){const blob=await env.CONTENT.head('blobs/'+f.sha256);if(!blob||blob.size!==f.bytes)throw Error('file_missing');}
 const activated=await route(env,a.hostname,'activate',{request_id:a.request_id,expected_previous:a.expected_previous,project_id:a.project_id,hostname:a.hostname,release_id:a.release_id,access_aud:manifest.access_aud});
 return reply({schema:SCHEMA,state:'ACTIVE',project_id:a.project_id,release_id:a.release_id,previous:activated.previous,private_assets_preserved:true});
}
async function serve(req,env,u,fetcher){
 const host=u.hostname;
 if(host===CONTROL_HOST||!env?.CONTENT||!env?.RELEASE_LEDGER)return no(404);
 if(host!==STUDIO_HOST && !/^[a-z][a-z0-9-]{2,39}\.apps\.lifelatelycounseling\.com$/.test(host))return no(404);
 let active;try{active=await route(env,host,'current')}catch{return no(404)}
 if(!active?.project_id||!validHost(host,active.project_id)||!isId(active.release_id))return no(404);
 try{await siteAuth(req,env,active.access_aud,fetcher)}catch{return no(403)}
 let path;try{path=decodeURI(u.pathname)}catch{return no(400)}
 if(path==='/')path='/index.html';if(!validPath(path))return no(404);
 const stored=await env.CONTENT.get('pending/'+active.project_id+'/'+active.release_id+'.json');if(!stored)return no(503);
 const manifest=JSON.parse(await stored.text());const entry=manifest.files.find(f=>f.path===path);
 if(!entry)return no(404);
 const object=await env.CONTENT.get('blobs/'+entry.sha256);if(!object||object.size!==entry.bytes)return no(503);
 const headers=new Headers({...RHEAD,'content-type':contentType(path)});
 headers.set('content-security-policy',"default-src 'self'; img-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'");
 return new Response(req.method==='HEAD'?null:object.body,{status:200,headers});
}
export async function handleRequest(req,env,fetcher=fetch){
 let u;try{u=new URL(req.url)}catch{return no(400)}
 if(u.hostname===CONTROL_HOST){
  if(!['POST','PUT'].includes(req.method))return no(405);
  try{await controllerAuth(req,env,fetcher)}catch{return no(403)}
  try{
   if(req.method==='POST' && !jsonSameOrigin(req,u))return no(403);
   if(req.method==='POST'&&u.pathname==='/v1/prepare')return await prepare(req,env);
   if(req.method==='POST'&&u.pathname==='/v1/activate')return await activate(req,env);
   if(req.method==='PUT'&&u.pathname.startsWith('/v1/upload/')){
     if(req.headers.get('origin')!==u.origin||req.headers.get('sec-fetch-site')!=='same-origin')return no(403);
     return await upload(req,env,u);
   }
   return no(404);
  }catch{return no(409)}
 }
 if(req.method!=='GET'&&req.method!=='HEAD')return no(405);
 return serve(req,env,u,fetcher);
}
export default{async fetch(req,env){return handleRequest(req,env)}};
export class ReleaseLedger{
 constructor(state){this.state=state}
 async fetch(req){
  const path=new URL(req.url).pathname;
  if(path==='/current'&&req.method==='GET'){
   const val=await this.state.storage.get('active');return val?reply(val):no(404);
  }
  if(req.method!=='POST'||!['/claim','/activate'].includes(path))return no(404);
  let obj;try{obj=await req.json()}catch{return no(400)}
  if(!isId(obj?.request_id))return no(400);
  try{
   const result=await this.state.storage.transaction(async txn=>{
    if(await txn.get('used:'+obj.request_id))throw Error('replay');
    if(path==='/claim'){await txn.put('used:'+obj.request_id,true);return {claimed:true}}
    const previous=await txn.get('active');
    if((previous?.release_id||null)!==obj.expected_previous||!isId(obj.release_id)||
      !validHost(obj.hostname,obj.project_id)||typeof obj.access_aud!=='string'||obj.access_aud.length<8)throw Error('stale_or_invalid');
    await txn.put('used:'+obj.request_id,true);
    await txn.put('active',{project_id:obj.project_id,hostname:obj.hostname,release_id:obj.release_id,access_aud:obj.access_aud});
    return {previous:previous?.release_id||null};
   });return reply(result);
  }catch{return no(409)}
 }
}
