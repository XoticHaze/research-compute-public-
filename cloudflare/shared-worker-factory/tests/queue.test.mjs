import test from 'node:test';
import assert from 'node:assert/strict';
import {readProposal,writeReceipt} from '../src/queue.js';
import {SCHEMA} from '../src/policy.js';

const secret={FACTORY_QUEUE_GITHUB_TOKEN:{get:async()=> 'q'.repeat(32)}};
const path='cloudflare-factory/proposal.json';
const req=()=>({schema:SCHEMA,operation:'ordinary_worker.create',
  request_id:'a'.repeat(32),worker_name:'ordinary-example-worker',
  expires_at:Math.floor(Date.now()/1000)+120});
function gitFile(request,override={}){
  const content=JSON.stringify(request);
  return {sha:'b'.repeat(40),path,type:'file',
    encoding:'base64',size:content.length,
    content:btoa(content),...override};
}
test('queue reads only fixed private branch and validates exact proposal',async()=>{
  const save=globalThis.fetch;
  let called='';
  globalThis.fetch=async(url,init)=>{
    called=String(url);
    assert.equal(init.headers.authorization,'Bearer '+'q'.repeat(32));
    return new Response(JSON.stringify(gitFile(req())),{status:200});
  };
  try{
    const got=await readProposal(secret);
    assert.equal(got.blob_sha,'b'.repeat(40));
    assert.equal(got.request.worker_name,'ordinary-example-worker');
    assert.equal(called,'https://api.github.com/repos/XoticHaze/CommandCenter-gate-control/contents/cloudflare-factory/proposal.json?ref=cloudflare-factory-inbox');
  }finally{globalThis.fetch=save;}
});
test('queue fails closed on modified path or reserved Worker',async()=>{
  const save=globalThis.fetch;
  try{
    globalThis.fetch=async()=>new Response(
      JSON.stringify(gitFile(req(),{path:'arbitrary-command.json'})),{status:200});
    await assert.rejects(readProposal(secret));
    globalThis.fetch=async()=>new Response(
      JSON.stringify(gitFile({...req(),worker_name:'ccpi-owner-cloudflare-authority'})),{status:200});
    await assert.rejects(readProposal(secret));
  }finally{globalThis.fetch=save;}
});
test('terminal receipt writes fixed private path without overwrite or token disclosure',async()=>{
  const save=globalThis.fetch;
  let payload;
  globalThis.fetch=async(url,init)=>{
    assert.equal(init.method,'PUT');
    assert.ok(String(url).endsWith('/cloudflare-factory/results/'+'a'.repeat(32)+'.json'));
    payload=JSON.parse(init.body);
    assert.equal(payload.sha,undefined);
    const written=atob(payload.content);
    assert.equal(JSON.parse(written).status,'created_inert');
    assert.equal(written.includes('q'.repeat(32)),false);
    return new Response(JSON.stringify({content:{
      sha:'c'.repeat(40),path:'cloudflare-factory/results/'+'a'.repeat(32)+'.json'}}),{status:201});
  };
  try{
    const result=await writeReceipt(secret,{request_id:'a'.repeat(32),
      status:'created_inert'});
    assert.equal(result.blob_sha,'c'.repeat(40));
    assert.equal(payload.branch,'cloudflare-factory-inbox');
  }finally{globalThis.fetch=save;}
});
