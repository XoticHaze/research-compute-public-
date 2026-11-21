import test from 'node:test';
import assert from 'node:assert/strict';
import {verifyFactoryMachineOidc,FACTORY_MACHINE_IDENTITY} from '../src/machine_oidc.js';
import factory from '../src/index.js';

const RUN='44999999999';
const base={
  iss:'https://token.actions.githubusercontent.com',
  aud:FACTORY_MACHINE_IDENTITY.expected_audience,
  sub:'repo:'+FACTORY_MACHINE_IDENTITY.expected_repository+':ref:refs/heads/main',
  repository:FACTORY_MACHINE_IDENTITY.expected_repository,
  repository_visibility:'public', runner_environment:'github-hosted',
  ref:FACTORY_MACHINE_IDENTITY.expected_ref,
  workflow_ref:FACTORY_MACHINE_IDENTITY.expected_workflow_ref,
  workflow_sha:'b'.repeat(40),sha:'a'.repeat(40),
  event_name:'workflow_dispatch',run_id:RUN,run_attempt:'1',
};
const toB64u=bytes=>Buffer.from(bytes).toString('base64url');
async function makeIdentity() {
  const keys=await crypto.subtle.generateKey(
    {name:'RSASSA-PKCS1-v1_5',modulusLength:2048,
     publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},
    true,['sign','verify']);
  const jwk=await crypto.subtle.exportKey('jwk',keys.publicKey);
  const sign=async(overrides={})=>{
    const now=Math.floor(Date.now()/1000);
    const claims={...base,iat:now-10,nbf:now-10,exp:now+120,...overrides};
    const head=toB64u(JSON.stringify({alg:'RS256',typ:'JWT',kid:'test-only-key'}));
    const body=toB64u(JSON.stringify(claims));
    const input=head+'.'+body;
    const signature=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',keys.privateKey,
      new TextEncoder().encode(input));
    return input+'.'+toB64u(new Uint8Array(signature));
  };
  return {jwk,sign};
}
async function withJwks(key,callback) {
  const original=globalThis.fetch;
  let count=0;
  globalThis.fetch=async(url,init)=>{
    assert.equal(url,'https://token.actions.githubusercontent.com/.well-known/jwks');
    assert.equal(init.redirect,'error');
    count++;
    return new Response(JSON.stringify({keys:[{...key,kid:'test-only-key'}]}),
      {status:200,headers:{'content-type':'application/json'}});
  };
  try {const result=await callback();return {result,jwks_calls:count};}
  finally {globalThis.fetch=original;}
}
test('valid signed exact public GitHub workflow authenticates without credentials',async()=>{
  const {jwk,sign}=await makeIdentity(),jwt=await sign();
  const {result,jwks_calls}=await withJwks(jwk,()=>verifyFactoryMachineOidc(jwt,RUN));
  assert.equal(jwks_calls,1);
  assert.equal(result.identity_verified,true);
  assert.equal(result.run_id,RUN);
  assert.equal(result.source_sha,'a'.repeat(40));
  assert.equal(JSON.stringify(result).includes(jwt),false);
});
test('signature, issuer, audience, event, ref, workflow and run ID are all exact',async()=>{
  const {jwk,sign}=await makeIdentity();
  const overrides=[
    {aud:'wrong'}, {iss:'https://attacker.invalid'},
    {repository:'AnotherOwner/another-repo'},
    {ref:'refs/heads/feature'},{event_name:'pull_request'},
    {workflow_ref:'XoticHaze/research-compute-public-/.github/workflows/evil.yml@refs/heads/main'},
    {sub:'repo:AnotherOwner/another-repo:ref:refs/heads/main'},
    {repository_visibility:'private'},
    {runner_environment:'self-hosted'}, {run_attempt:'bad'},
    {exp:Math.floor(Date.now()/1000)-120},
  ];
  for(const changes of overrides) {
    const token=await sign(changes);
    await withJwks(jwk,async()=>assert.rejects(
      verifyFactoryMachineOidc(token,RUN)));
  }
  const jwt=await sign();
  await withJwks(jwk,async()=>assert.rejects(
    verifyFactoryMachineOidc(jwt,'12345678999')));
  const tampered=jwt.slice(0,-2)+(jwt.at(-2)==='A'?'B':'A')+jwt.at(-1);
  await withJwks(jwk,async()=>assert.rejects(
    verifyFactoryMachineOidc(tampered,RUN)));
});
test('machine readiness requires independent flag, no owner impersonation or Cloudflare calls',async()=>{
  const {jwk,sign}=await makeIdentity(),jwt=await sign();
  const url='https://factory.example/v1/machine/readiness';
  const req=(token=jwt)=>new Request(url,{method:'POST',
    headers:{authorization:'Bearer '+token,'x-cc-github-run-id':RUN}});
  const baseEnv={
    FACTORY_ACCOUNT_ID:'ce43cd7b917d98a4bb4866d30eed99c0',
    FACTORY_EXECUTOR_ENABLED:'0',
    FACTORY_MACHINE_READONLY_ENABLED:'0',
    FACTORY_MACHINE_INSPECT_ENABLED:'0'
  };
  const denied=await factory.fetch(req(),baseEnv,{});
  assert.equal(denied.status,403);
  const enabled={...baseEnv,FACTORY_MACHINE_READONLY_ENABLED:'1'};
  const {result,jwks_calls}=await withJwks(jwk,()=>factory.fetch(req(),enabled,{}));
  assert.equal(jwks_calls,1);
  assert.equal(result.status,200);
  const data=await result.json();
  assert.equal(data.identity_verified,true);
  assert.equal(data.generic_executor_admitted,false);
  assert.equal(data.machine_creation_admitted,false);
  assert.equal(data.credentials_or_private_keys_returned,false);
  assert.equal(data.cloudflare_mutations,0);
  const forged=await factory.fetch(req('a.b.c'),enabled,{});
  assert.equal(forged.status,401);
  const wrongAccount=await factory.fetch(req(),{
    ...enabled,FACTORY_ACCOUNT_ID:'b'.repeat(32)},{});
  assert.equal(wrongAccount.status,403);
});
test('machine inspect rejects any mutation even with identity gate enabled',async()=>{
  const {jwk,sign}=await makeIdentity(),jwt=await sign();
  const body={
    schema:'commandcenter.cloudflare.factory_request.v1',
    operation:'ordinary_worker.create',request_id:'a'.repeat(32),
    worker_name:'some-ordinary-worker',expires_at:Math.floor(Date.now()/1000)+120
  };
  const env={
    FACTORY_ACCOUNT_ID:'ce43cd7b917d98a4bb4866d30eed99c0',
    FACTORY_EXECUTOR_ENABLED:'1',FACTORY_INSPECT_ENABLED:'1',
    FACTORY_MACHINE_READONLY_ENABLED:'1',
    FACTORY_MACHINE_INSPECT_ENABLED:'1',
  };
  const req=new Request('https://factory.example/v1/machine/inspect',{
    method:'POST',headers:{authorization:'Bearer '+jwt,
      'x-cc-github-run-id':RUN,
      'content-type':'application/json'},body:JSON.stringify(body)});
  const {result,jwks_calls}=await withJwks(jwk,()=>factory.fetch(req,env,{}));
  assert.equal(jwks_calls,1);
  assert.equal(result.status,403);
  assert.equal((await result.json()).error,'machine_operation_not_admitted');
});


test('machine exact-ID inspection uses original-account GET and shared one-use replay ledger',async()=>{
  const {jwk,sign}=await makeIdentity(),jwt=await sign();
  const workerId='b'.repeat(32), requestId='c'.repeat(32);
  const name='ordinary-existing-worker';
  const calls=[],claims=new Map();
  const durable={
    idFromName:()=> 'fixed-ledger',
    get:()=>({fetch:async request=>{
      const body=await request.json(),path=new URL(request.url).pathname;
      if(path==='/claim') {
        if(claims.has(body.request_id)) return new Response('{}',{status:409});
        claims.set(body.request_id,'claimed');
      } else if(path==='/finish') {
        if(claims.get(body.request_id)!=='claimed') return new Response('{}',{status:409});
        claims.set(body.request_id,'terminal');
      } else return new Response('{}',{status:404});
      return new Response('{}',{status:200});
    }})
  };
  const env={
    FACTORY_ACCOUNT_ID:'ce43cd7b917d98a4bb4866d30eed99c0',
    FACTORY_EXECUTOR_ENABLED:'1',FACTORY_INSPECT_ENABLED:'1',
    FACTORY_MACHINE_READONLY_ENABLED:'1',
    FACTORY_MACHINE_INSPECT_ENABLED:'1',
    FACTORY_WORKERS_ADMIN:{get:async()=> 'synthetic-nonsecret-placeholder'},
    FACTORY_LEDGER:durable
  };
  const body={
    schema:'commandcenter.cloudflare.factory_request.v1',
    operation:'existing_worker.inspect',
    request_id:requestId,worker_id:workerId,worker_name:name,
    expires_at:Math.floor(Date.now()/1000)+120,
  };
  const req=()=>new Request('https://factory.example/v1/machine/inspect',{
    method:'POST',headers:{authorization:'Bearer '+jwt,
      'x-cc-github-run-id':RUN,'content-type':'application/json'},
    body:JSON.stringify(body)});
  const original=globalThis.fetch;
  globalThis.fetch=async (url,init)=>{
    const u=String(url);
    if(u==='https://token.actions.githubusercontent.com/.well-known/jwks')
      return new Response(JSON.stringify({keys:[{...jwk,kid:'test-only-key'}]}),{
        status:200,headers:{'content-type':'application/json'}});
    calls.push({url:u,method:init.method});
    assert.equal(init.method,'GET');
    assert.equal(u,'https://api.cloudflare.com/client/v4/accounts/'+
      'ce43cd7b917d98a4bb4866d30eed99c0/workers/workers/'+workerId);
    return new Response(JSON.stringify({success:true,result:{id:workerId,name}}),{
      status:200,headers:{'content-type':'application/json'}});
  };
  try {
    const first=await factory.fetch(req(),env,{});
    assert.equal(first.status,200);
    const receipt=await first.json();
    assert.equal(receipt.status,'existing_worker_identity_verified');
    assert.equal(receipt.machine_path,true);
    assert.equal(receipt.identity_verified,true);
    assert.equal(receipt.github_run_id,RUN);
    assert.equal(receipt.cloudflare_mutations,0);
    assert.equal(receipt.bearer_returned,false);
    assert.equal(calls.length,1);
    const replay=await factory.fetch(req(),env,{});
    assert.equal(replay.status,403);
    assert.equal(calls.length,1);
    assert.equal(claims.get(requestId),'terminal');
  } finally { globalThis.fetch=original; }
});
