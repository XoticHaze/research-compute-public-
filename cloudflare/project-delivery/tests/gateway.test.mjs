import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { validateManifest,validateActivation,validHost,hostPolicy,validPath,SCHEMA } from '../src/policy.mjs';
import { handleRequest, ReleaseLedger } from '../src/index.mjs';
const cryptoApi=globalThis.crypto||webcrypto;
const b64=x=>Buffer.from(x).toString('base64url');
const NOW=Math.floor(Date.now()/1000);
const control='https://release.apps.lifelatelycounseling.com';
const host='sample-site.apps.lifelatelycounseling.com';
const project='sample-site';
const rid='0123456789abcdef0123456789abcdef';
const release='abcdef0123456789abcdef0123456789';
const aud='app-access-audience-000001';
const controllerAud='controller-audience-000001';
const manifest={schema:SCHEMA,request_id:rid,project_id:project,release_id:release,hostname:host,access_aud:aud,expires_at:NOW+240,files:[{path:'/index.html',sha256:'2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',bytes:5}]};
const activation={schema:SCHEMA,request_id:'11111111111111111111111111111111',project_id:project,release_id:release,hostname:host,expected_previous:null,expires_at:NOW+240};
const pair=await cryptoApi.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
const jwk=await cryptoApi.subtle.exportKey('jwk',pair.publicKey);Object.assign(jwk,{kid:'key1',use:'sig'});
const mockFetch=async()=>new Response(JSON.stringify({keys:[jwk]}),{status:200});
async function token(a=controllerAud,claims={}){
 const head=b64(JSON.stringify({alg:'RS256',kid:'key1'}));
 const payload=b64(JSON.stringify({iss:'https://releasetest.cloudflareaccess.com',aud:[a],email:'owner@example.test',iat:NOW-4,exp:NOW+1800,...claims}));
 const raw=head+'.'+payload;
 return raw+'.'+b64(await cryptoApi.subtle.sign('RSASSA-PKCS1-v1_5',pair.privateKey,new TextEncoder().encode(raw)));
}
class MockR2{
 constructor(){this.map=new Map()}
 async get(k){const value=this.map.get(k);return value===undefined?null:{size:value.length,body:value,text:async()=>Buffer.from(value).toString('utf8')}}
 async head(k){const val=this.map.get(k);return val===undefined?null:{size:val.length}}
 async put(k,v){const value=typeof v==='string'?Buffer.from(v):Buffer.from(v);this.map.set(k,value);return {size:value.length}}
}
class MockStorage{
 constructor(){this.map=new Map()}
 async get(k){return this.map.get(k)}
 async put(k,v){this.map.set(k,v)}
 async transaction(fn){return fn(this)}
}
const objects=new Map();
const namespace={idFromName:k=>k,get:k=>{if(!objects.has(k))objects.set(k,new ReleaseLedger({storage:new MockStorage()},env));return objects.get(k)}};
const r2=new MockR2();
const env={CONTENT:r2,RELEASE_LEDGER:namespace,RELEASE_ENABLED:'1',ACCESS_ISSUER:'https://releasetest.cloudflareaccess.com/',ACCESS_ALLOWED_EMAILS_JSON:'["owner@example.test"]',CONTROL_ACCESS_AUD:controllerAud,ALLOWED_APP_ROOTS_JSON:'[\"apps.lifelatelycounseling.com\",\"apps.otherventure.example\"]',EXACT_APP_HOSTS_JSON:'{\"studio.lifelatelycounseling.com\":\"incomeengine-3d-studio\"}',CONTROL_HOSTNAME:'release.apps.lifelatelycounseling.com'};
async function post(endpoint,body,jwt=null,extra={}){jwt ??= await token();return handleRequest(new Request(control+endpoint,{method:'POST',headers:{origin:control,'sec-fetch-site':'same-origin','content-type':'application/json','Cf-Access-Jwt-Assertion':jwt,...extra},body:JSON.stringify(body)}),env,mockFetch)}
async function put(bytes,jwt=null){jwt ??= await token();return handleRequest(new Request(control+'/v1/upload/'+project+'/'+release+'/'+manifest.files[0].sha256,{method:'PUT',headers:{origin:control,'sec-fetch-site':'same-origin','Cf-Access-Jwt-Assertion':jwt},body:bytes}),env,mockFetch)}
const siteReq=(jwt)=>handleRequest(new Request('https://'+host+'/',{headers:jwt?{'Cf-Access-Jwt-Assertion':jwt}:{}}),env,mockFetch);
test('strict project hostname prevents replacing HA, gateway-ops, broker and arbitrary domains',()=>{
 assert.equal(validHost('ha.lifelatelycounseling.com','ha'),false);
 assert.equal(validHost('gateway-ops.lifelatelycounseling.com','gateway-ops'),false);
 assert.equal(validHost('reference-release-broker-v1.apps.lifelatelycounseling.com','reference-release-broker-v1'),false);
 assert.equal(validHost('sample-site.apps.lifelatelycounseling.com','sample-site'),true);
 assert.equal(validHost('studio.lifelatelycounseling.com','incomeengine-3d-studio'),true);
 assert.equal(validHost('studio.lifelatelycounseling.com','sample-site'),false);
 assert.equal(validHost('sample-site.apps.otherventure.example','sample-site',hostPolicy(env)),true);
 assert.equal(validHost('sample-site.apps.thirdventure.example','sample-site',hostPolicy(env)),false);
 assert.throws(()=>hostPolicy({...env,CONTROL_HOSTNAME:'ha.lifelatelycounseling.com'}));
});
test('rejects traversal, oversized unpinned assets, invented fields and expired intents',()=>{
 for(const path of ['/../index.html','/a//index.html','/secret.txt%2f..','/a\\b.js'])assert.equal(validPath(path),false,path);
 assert.throws(()=>validateManifest({...manifest,hostname:'ha.lifelatelycounseling.com'}));
 assert.throws(()=>validateManifest({...manifest,files:[{...manifest.files[0],bytes:20_000_001}]}));
 assert.throws(()=>validateManifest({...manifest,expires_at:NOW-1}));
 assert.throws(()=>validateManifest({...manifest,extra:'ignored'}));
 assert.throws(()=>validateActivation({...activation,expires_at:NOW+10000}));
});
test('anonymous and forged JWT cannot publish or view content; release defaults off',async()=>{
 assert.equal((await post('/v1/prepare',manifest,'bad')).status,403);
 assert.equal((await siteReq()).status,404);
 const held={...env,RELEASE_ENABLED:'0'};
 assert.equal((await handleRequest(new Request(control+'/v1/prepare',{method:'POST',headers:{origin:control,'sec-fetch-site':'same-origin','content-type':'application/json','Cf-Access-Jwt-Assertion':await token()},body:JSON.stringify(manifest)}),held,mockFetch)).status,403);
 assert.equal((await post('/v1/prepare',manifest,await token('wrong-aud'))).status,403);
});
test('same-origin state transition enforced and prepared immutable manifest accepted once',async()=>{
 const wrong=await post('/v1/prepare',manifest,await token(),{'origin':'https://evil.example'});
 assert.equal(wrong.status,403);
 const good=await post('/v1/prepare',manifest);assert.equal(good.status,200);assert.equal((await good.json()).state,'PREPARED');
 assert.equal((await post('/v1/prepare',manifest)).status,409);
});
test('blob uploads enforce exact expected SHA-256 and byte count',async()=>{
 assert.equal((await put('hallo')).status,409);
 const uploaded=await put('hello');assert.equal(uploaded.status,200);assert.equal((await uploaded.json()).sha256,manifest.files[0].sha256);
 assert.equal((await r2.head('blobs/'+manifest.files[0].sha256)).size,5);
});
test('exact prior release CAS activates once, owner JWT serves bytes, same release replay denied',async()=>{
 assert.equal((await siteReq()).status,404);
 const activated=await post('/v1/activate',activation);assert.equal(activated.status,200);assert.equal((await activated.json()).state,'ACTIVE');
 assert.equal((await post('/v1/activate',activation)).status,409);
 assert.equal((await post('/v1/activate',{...activation,request_id:'22222222222222222222222222222222',expected_previous:'ffffffffffffffffffffffffffffffff'})).status,409);
 assert.equal((await siteReq()).status,403);
 assert.equal((await siteReq(await token('other-audience'))).status,403);
 const res=await siteReq(await token(aud));assert.equal(res.status,200);assert.equal(await res.text(),'hello');
 assert.equal(res.headers.get('cache-control'),'private, no-store');
});
test('no Cloudflare Admin bearer, worker create, issuer capability or arbitrary API host',()=>{
 assert.equal(Object.keys(env).some(k=>/TOKEN|ADMIN|SECRET|KEY/.test(k)),false);
 assert.equal(validHost('malicious.com',project),false);
 assert.equal(validHost('pi-owner.apps.lifelatelycounseling.com','pi-owner'),false);
 assert.equal(validPath('/ok.glb'),true);
});
