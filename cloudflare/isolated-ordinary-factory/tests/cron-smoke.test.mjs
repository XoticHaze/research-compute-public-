import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from '../scripts/prepare.mjs';

const ACCOUNT='ab'.repeat(16);
const SHA='b'.repeat(40), ID='c'.repeat(32), RUN='a'.repeat(32);
const CRON='* * * * *';
const API='https://api.cloudflare.com/client/v4/accounts/'+ACCOUNT;
const ROOT='https://api.github.com/repos/XoticHaze/CommandCenter-gate-control/contents/';
async function withFixture(fn) {
  const dir=mkdtempSync(join(tmpdir(),'cc-cron-gate-'));
  try {
    const manifest=build(ACCOUNT,{outDir:dir});
    const cfg=JSON.parse(readFileSync(join(dir,'wrangler.jsonc'),'utf8'));
    const mod=await import(pathToFileURL(join(dir,'src','index.js')).href);
    await fn({mod,cfg,manifest});
  } finally {rmSync(dir,{recursive:true,force:true});}
}
function env(overrides={}) {
  return {
    FACTORY_ACCOUNT_ID:ACCOUNT,
    FACTORY_SCHEDULED_POLL_ENABLED:'0',
    FACTORY_EXECUTOR_ENABLED:'0',
    FACTORY_CREATE_ENABLED:'0',
    FACTORY_PROPOSAL_ONLY:'1',
    ...overrides,
  };
}
test('Cron exists but defaults completely disabled with zero Cloudflare calls',async()=>{
  await withFixture(async({mod,cfg})=>{
    assert.deepEqual(cfg.triggers.crons,[CRON]);
    assert.equal(cfg.vars.FACTORY_SCHEDULED_POLL_ENABLED,'0');
    assert.equal(cfg.vars.FACTORY_EXECUTOR_ENABLED,'0');
    assert.equal(cfg.vars.FACTORY_CREATE_ENABLED,'0');
    assert.equal(cfg.vars.FACTORY_PROPOSAL_ONLY,'1');
    assert.equal(typeof mod.default.scheduled,'function');
    const original=globalThis.fetch;
    globalThis.fetch=()=>{throw Error('network_called_while_disabled');};
    try {
      await mod.default.scheduled({cron:CRON},env(),{});
      await mod.default.scheduled({cron:'0 0 * * *'},env({
        FACTORY_SCHEDULED_POLL_ENABLED:'1',
        FACTORY_EXECUTOR_ENABLED:'1',FACTORY_CREATE_ENABLED:'1'}),{});
    }finally{globalThis.fetch=original;}
  });
});
test('rejects all non-scratch GitHub commands before touching Cloudflare',async()=>{
  await withFixture(async({mod})=>{
    let calls=[];
    const original=globalThis.fetch;
    globalThis.fetch=async(url,init)=>{
      calls.push(String(url));
      assert.ok(String(url).startsWith(ROOT));
      const req={schema:'commandcenter.cloudflare.factory_request.v1',
        operation:'ordinary_worker.create',request_id:RUN,
        worker_name:'ordinary-general-worker',expires_at:Math.floor(Date.now()/1000)+200};
      const raw=JSON.stringify(req);
      return new Response(JSON.stringify({
        path:'cloudflare-factory/proposal.json',type:'file',
        size:raw.length,sha:SHA,encoding:'base64',content:btoa(raw)
      }),{status:200});
    };
    try {
      await assert.rejects(mod.default.scheduled({cron:CRON},env({
        FACTORY_SCHEDULED_POLL_ENABLED:'1',FACTORY_EXECUTOR_ENABLED:'1',
        FACTORY_CREATE_ENABLED:'1', FACTORY_QUEUE_GITHUB_TOKEN:'fake-github-token'.repeat(4)
      }),{}),/cron_operation_not_admitted/);
      assert.equal(calls.length,1);
      assert.ok(calls.every(x=>x.startsWith(ROOT)));
    }finally{globalThis.fetch=original;}
  });
});
test('one fixed scratch create executes exactly once and writes private receipt without token',async()=>{
  await withFixture(async({mod})=>{
    const journal=new Map(),calls=[];
    const ledger={idFromName:x=>x,get:()=>({fetch:async request=>{
      const data=await request.json(),mode=new URL(request.url).pathname;
      if(mode==='/claim'){
        if(journal.has(data.request_id))return new Response('{}',{status:409});
        journal.set(data.request_id,'claimed');
      }else if(mode==='/finish'){
        if(journal.get(data.request_id)!=='claimed')return new Response('{}',{status:409});
        journal.set(data.request_id,'terminal');
      }else return new Response('{}',{status:404});
      return new Response('{}',{status:200});
    }})};
    const cloudToken='test-cloudflare-secret-'+ 'x'.repeat(22);
    const githubToken='test-github-secret-'+ 'y'.repeat(22);
    const proposal={schema:'commandcenter.cloudflare.factory_request.v1',
      operation:'ordinary_worker.create',request_id:RUN,worker_name:'cc-scratch-proof-a',
      expires_at:Math.floor(Date.now()/1000)+240};
    const original=globalThis.fetch;
    globalThis.fetch=async(url,init)=>{
      const target=String(url);calls.push({url:target,method:init.method||'GET'});
      if(target.startsWith(ROOT)){
        assert.equal(init.headers.authorization,'Bearer '+githubToken);
        if(init.method==='DELETE'){
          assert.equal(target,ROOT+'cloudflare-factory/proposal.json');
          const request=JSON.parse(init.body);
          assert.equal(request.sha,SHA);
          assert.equal(request.branch,'cloudflare-factory-inbox');
          return new Response(JSON.stringify({commit:{sha:SHA}}),{status:200});
        }
        if(init.method==='PUT'){
          const payload=JSON.parse(init.body);
          const receipt=JSON.parse(atob(payload.content));
          assert.equal(receipt.status,'created_inert');
          assert.equal(receipt.worker_name,'cc-scratch-proof-a');
          assert.equal(receipt.public_traffic_enabled,false);
          assert.ok(!JSON.stringify(receipt).includes(githubToken));
          assert.ok(!JSON.stringify(receipt).includes(cloudToken));
          return new Response(JSON.stringify({content:{sha:SHA,
            path:'cloudflare-factory/results/'+RUN+'.json'}}),{status:201});
        }
        const raw=JSON.stringify(proposal);
        return new Response(JSON.stringify({sha:SHA,type:'file',encoding:'base64',
          size:raw.length,path:'cloudflare-factory/proposal.json',content:btoa(raw)}),{status:200});
      }
      assert.equal(init.headers.authorization,'Bearer '+cloudToken);
      if(target===API+'/workers/workers'&&init.method==='POST'){
        assert.deepEqual(JSON.parse(init.body),{
          name:'cc-scratch-proof-a',subdomain:{enabled:false,previews_enabled:false}
        });
      }else assert.equal(target,API+'/workers/workers/'+ID);
      return new Response(JSON.stringify({success:true,result:{id:ID,name:'cc-scratch-proof-a'}}),{status:200});
    };
    try{
      const accepted=env({FACTORY_SCHEDULED_POLL_ENABLED:'1',
        FACTORY_EXECUTOR_ENABLED:'1',FACTORY_CREATE_ENABLED:'1',
        FACTORY_QUEUE_GITHUB_TOKEN:githubToken,FACTORY_WORKERS_ADMIN:cloudToken,
        FACTORY_LEDGER:ledger});
      await mod.default.scheduled({cron:CRON},accepted,{});
      assert.equal(journal.get(RUN),'terminal');
      assert.equal(calls.filter(x=>x.method==='POST').length,1);
      assert.equal(calls.filter(x=>x.method==='PUT').length,1);
      assert.equal(calls.filter(x=>x.method==='DELETE').length,1);
      const before=calls.filter(x=>x.method==='POST').length;
      await assert.rejects(mod.default.scheduled({cron:CRON},accepted,{}));
      assert.equal(calls.filter(x=>x.method==='POST').length,before);
    }finally{globalThis.fetch=original;}
  });
});
test('missing proposal 404 is idle only after authenticated fixed directory verification',async()=>{
  await withFixture(async({mod})=>{
    const original=globalThis.fetch;
    const ready=env({FACTORY_SCHEDULED_POLL_ENABLED:'1',FACTORY_EXECUTOR_ENABLED:'1',FACTORY_CREATE_ENABLED:'1',
      FACTORY_QUEUE_GITHUB_TOKEN:'synthetic-github-token-long-enough'});
    const proposal=ROOT+'cloudflare-factory/proposal.json?ref=cloudflare-factory-inbox';
    const directory=ROOT+'cloudflare-factory?ref=cloudflare-factory-inbox';
    const attempts={path:'cloudflare-factory/attempts',type:'dir'};
    try {
      const calls=[];
      globalThis.fetch=async(url,init)=>{
        calls.push(String(url));
        assert.equal(init.headers.authorization,'Bearer '+ready.FACTORY_QUEUE_GITHUB_TOKEN);
        assert.equal(init.redirect,'manual');
        return new Response(JSON.stringify(url===proposal?{}:[attempts]),{status:url===proposal?404:200});
      };
      await mod.default.scheduled({cron:CRON},ready,{});
      assert.deepEqual(calls,[proposal,directory]);
      globalThis.fetch=async()=>new Response('{}',{status:404});
      await assert.rejects(mod.default.scheduled({cron:CRON},ready,{}),/queue_repository_or_branch_unavailable/);
      globalThis.fetch=async(url)=>new Response(JSON.stringify(url===proposal?{}:[attempts,{path:'cloudflare-factory/proposal.json',type:'file'}]),{status:url===proposal?404:200});
      await assert.rejects(mod.default.scheduled({cron:CRON},ready,{}),/proposal_read_inconsistent/);
      globalThis.fetch=async(url)=>new Response(JSON.stringify(url===proposal?{}:[]),{status:url===proposal?404:200});
      await assert.rejects(mod.default.scheduled({cron:CRON},ready,{}),/queue_directory_identity_unverified/);
      globalThis.fetch=async()=>new Response('{}',{status:403});
      await assert.rejects(mod.default.scheduled({cron:CRON},ready,{}),/proposal_unavailable/);
    } finally {globalThis.fetch=original;}
  });
});
test('wrong account refuses cron before reading a private proposal',async()=>{
  await withFixture(async({mod})=>{
    const before=globalThis.fetch;
    globalThis.fetch=()=>{throw Error('network_should_not_reach');};
    try{
      await assert.rejects(mod.default.scheduled({cron:CRON},env({
        FACTORY_ACCOUNT_ID:'cd'.repeat(16),FACTORY_SCHEDULED_POLL_ENABLED:'1',
        FACTORY_EXECUTOR_ENABLED:'1',FACTORY_CREATE_ENABLED:'1'
      }),{}),/wrong_account/);
    }finally{globalThis.fetch=before;}
  });
});

test('terminal Cloudflare failure writes a private failure receipt and consumes only the exact proposal',async()=>{
  await withFixture(async({mod})=>{
    const calls=[],journal=new Map();
    const req={schema:'commandcenter.cloudflare.factory_request.v1',
      operation:'ordinary_worker.create',request_id:RUN,worker_name:'cc-scratch-proof-b',
      expires_at:Math.floor(Date.now()/1000)+240};
    const ledger={idFromName:x=>x,get:()=>({fetch:async request=>{
      const data=await request.json(),mode=new URL(request.url).pathname;
      if(mode==='/claim'){
        if(journal.has(data.request_id))return new Response('{}',{status:409});
        journal.set(data.request_id,'claimed');
      }else if(mode==='/finish'){
        if(journal.get(data.request_id)!=='claimed')return new Response('{}',{status:409});
        journal.set(data.request_id,'terminal');
      }else return new Response('{}',{status:404});
      return new Response('{}',{status:200});
    }})};
    const original=globalThis.fetch;
    globalThis.fetch=async(url,init)=>{
      const target=String(url);calls.push(init.method||'GET');
      if(target.startsWith(API))return new Response('{}',{status:403});
      assert.ok(target.startsWith(ROOT));
      if(init.method==='PUT'){
        const payload=JSON.parse(init.body),receipt=JSON.parse(atob(payload.content));
        assert.equal(receipt.status,'failed_or_indeterminate');
        assert.equal(receipt.retry_same_id,false);
        assert.equal(receipt.worker_name,req.worker_name);
        assert.equal(receipt.operation,req.operation);
        return new Response(JSON.stringify({content:{sha:SHA,path:'cloudflare-factory/results/'+RUN+'.json'}}),{status:201});
      }
      if(init.method==='DELETE'){
        assert.equal(JSON.parse(init.body).sha,SHA);
        return new Response(JSON.stringify({commit:{sha:SHA}}),{status:200});
      }
      const raw=JSON.stringify(req);
      return new Response(JSON.stringify({sha:SHA,type:'file',encoding:'base64',size:raw.length,path:'cloudflare-factory/proposal.json',content:btoa(raw)}),{status:200});
    };
    try{
      const ready=env({FACTORY_SCHEDULED_POLL_ENABLED:'1',FACTORY_EXECUTOR_ENABLED:'1',FACTORY_CREATE_ENABLED:'1',
        FACTORY_QUEUE_GITHUB_TOKEN:'synthetic-github-token-long-enough',
        FACTORY_WORKERS_ADMIN:'synthetic-cloudflare-token-long-enough',FACTORY_LEDGER:ledger});
      await mod.default.scheduled({cron:CRON},ready,{});
      assert.equal(journal.get(RUN),'terminal');
      assert.deepEqual(calls,['GET','POST','PUT','DELETE']);
      await assert.rejects(mod.default.scheduled({cron:CRON},ready,{}));
      assert.equal(calls.filter(x=>x==='POST').length,1);
    }finally{globalThis.fetch=original;}
  });
});
test('stage operation requires its own flag and never borrows create authority',async()=>{
  await withFixture(async({mod})=>{
    const original=globalThis.fetch;
    let calls=0;
    const req={schema:'commandcenter.cloudflare.factory_request.v1',
      operation:'existing_worker.scratch_version.stage',request_id:RUN,worker_name:'cc-scratch-proof-a',
      worker_id:ID,source_commit:SHA,source_sha256:'d'.repeat(64),
      expires_at:Math.floor(Date.now()/1000)+240};
    globalThis.fetch=async(url)=>{
      calls++;assert.ok(String(url).startsWith(ROOT));
      const raw=JSON.stringify(req);
      return new Response(JSON.stringify({sha:SHA,type:'file',encoding:'base64',size:raw.length,path:'cloudflare-factory/proposal.json',content:btoa(raw)}),{status:200});
    };
    try{
      await assert.rejects(mod.default.scheduled({cron:CRON},env({
        FACTORY_SCHEDULED_POLL_ENABLED:'1',FACTORY_EXECUTOR_ENABLED:'1',FACTORY_CREATE_ENABLED:'1',
        FACTORY_STAGE_VERSION_ENABLED:'0',FACTORY_QUEUE_GITHUB_TOKEN:'synthetic-github-token-long-enough'
      }),{}),/cron_operation_not_admitted/);
      assert.equal(calls,1);
    }finally{globalThis.fetch=original;}
  });
});

test('stage-only cron uploads a pinned scratch version with no deployment or create call',async()=>{
  await withFixture(async({mod})=>{
    const calls=[],journal=new Map();
    const source='export default {fetch(){return new Response("scratch B");}};';
    const bytes=new TextEncoder().encode(source);
    const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    const version='12345678-1234-1234-1234-123456789abc';
    const req={schema:'commandcenter.cloudflare.factory_request.v1',operation:'existing_worker.scratch_version.stage',
      request_id:RUN,worker_name:'cc-scratch-proof-b',worker_id:ID,source_commit:SHA,source_sha256:digest,
      expires_at:Math.floor(Date.now()/1000)+240};
    const ledger={idFromName:x=>x,get:()=>({fetch:async request=>{
      const data=await request.json(),mode=new URL(request.url).pathname;
      if(mode==='/claim'){
        if(journal.has(data.request_id))return new Response('{}',{status:409});
        journal.set(data.request_id,'claimed');
      }else if(mode==='/finish'){
        if(journal.get(data.request_id)!=='claimed')return new Response('{}',{status:409});
        journal.set(data.request_id,'terminal');
      }else return new Response('{}',{status:404});
      return new Response('{}',{status:200});
    }})};
    const original=globalThis.fetch;
    globalThis.fetch=async(url,init)=>{
      const target=String(url),method=init.method||'GET';calls.push({target,method});
      if(target.startsWith(ROOT)){
        if(method==='PUT'){
          const receipt=JSON.parse(atob(JSON.parse(init.body).content));
          assert.equal(receipt.status,'staged_off_traffic');
          assert.equal(receipt.version_id,version);
          assert.equal(receipt.source_sha256,digest);
          assert.equal(receipt.live_serving_verified,false);
          return new Response(JSON.stringify({content:{sha:SHA,path:'cloudflare-factory/results/'+RUN+'.json'}}),{status:201});
        }
        if(method==='DELETE')return new Response(JSON.stringify({commit:{sha:SHA}}),{status:200});
        const raw=JSON.stringify(req);
        return new Response(JSON.stringify({sha:SHA,type:'file',encoding:'base64',size:raw.length,path:'cloudflare-factory/proposal.json',content:btoa(raw)}),{status:200});
      }
      if(target==='https://raw.githubusercontent.com/XoticHaze/research-compute-public-/'+SHA+'/cloudflare/ordinary-scratch-releases/cc-scratch-proof-b/worker.mjs'){
        assert.equal(init.headers.authorization,undefined);
        return new Response(source,{status:200});
      }
      if(target===API+'/workers/workers/'+ID && method==='GET')
        return new Response(JSON.stringify({success:true,result:{id:ID,name:req.worker_name}}),{status:200});
      assert.equal(target,API+'/workers/scripts/cc-scratch-proof-b/versions');
      assert.equal(method,'POST');
      assert.equal(await init.body.get('worker.mjs').text(),source);
      return new Response(JSON.stringify({success:true,result:{id:version}}),{status:201});
    };
    try{
      await mod.default.scheduled({cron:CRON},env({
        FACTORY_SCHEDULED_POLL_ENABLED:'1',FACTORY_EXECUTOR_ENABLED:'1',FACTORY_CREATE_ENABLED:'0',
        FACTORY_STAGE_VERSION_ENABLED:'1',FACTORY_QUEUE_GITHUB_TOKEN:'synthetic-github-token-long-enough',
        FACTORY_WORKERS_ADMIN:'synthetic-cloudflare-token-long-enough',FACTORY_LEDGER:ledger}),{});
      assert.equal(journal.get(RUN),'terminal');
      assert.equal(calls.filter(x=>x.method==='POST').length,1);
      assert.equal(calls.filter(x=>x.target.includes('/deployments')).length,0);
      assert.equal(calls.filter(x=>x.method==='PUT').length,1);
    }finally{globalThis.fetch=original;}
  });
});

test('fixed read-only queue probe works with create and stage disabled, receipt contains no secrets',async()=>{
  await withFixture(async({mod})=>{
    const original=globalThis.fetch, calls=[], journal=new Map();
    const req={schema:'commandcenter.cloudflare.factory_request.v1',operation:'factory.queue_probe',
      request_id:RUN,worker_name:'cc-ordinary-worker-factory',worker_id:ID,expires_at:Math.floor(Date.now()/1000)+200};
    const github='synthetic-github-token-long-enough', cloud='synthetic-cloudflare-token-long-enough';
    const ledger={idFromName:x=>x,get:()=>({fetch:async request=>{
      const data=await request.json(),mode=new URL(request.url).pathname;
      if(mode==='/claim'){if(journal.has(data.request_id))return new Response('{}',{status:409});journal.set(data.request_id,'claimed');}
      else if(mode==='/finish'){if(journal.get(data.request_id)!=='claimed')return new Response('{}',{status:409});journal.set(data.request_id,'terminal');}
      else return new Response('{}',{status:404});
      return new Response('{}',{status:200});
    }})};
    let receipt, adminStatus=200;
    globalThis.fetch=async(url,init)=>{
      const target=String(url),method=init.method||'GET';calls.push({target,method});
      if(target.startsWith(API)){
        assert.equal(method,'GET');assert.equal(target,API+'/workers/workers/'+ID);
        assert.equal(init.headers.authorization,'Bearer '+cloud);
        return new Response(JSON.stringify({success:adminStatus===200,result:{id:ID,name:req.worker_name}}),{status:adminStatus});
      }
      assert.ok(target.startsWith(ROOT));assert.equal(init.headers.authorization,'Bearer '+github);
      if(method==='PUT'){receipt=JSON.parse(atob(JSON.parse(init.body).content));
        return new Response(JSON.stringify({content:{sha:SHA,path:'cloudflare-factory/results/'+RUN+'.json'}}),{status:201});}
      if(method==='DELETE')return new Response(JSON.stringify({commit:{sha:SHA}}),{status:200});
      const raw=JSON.stringify(req);return new Response(JSON.stringify({sha:SHA,type:'file',encoding:'base64',size:raw.length,path:'cloudflare-factory/proposal.json',content:btoa(raw)}),{status:200});
    };
    const ready=env({FACTORY_SCHEDULED_POLL_ENABLED:'1',FACTORY_EXECUTOR_ENABLED:'1',FACTORY_CREATE_ENABLED:'0',FACTORY_STAGE_VERSION_ENABLED:'0',
      FACTORY_QUEUE_GITHUB_TOKEN:{get:async()=>github},FACTORY_WORKERS_ADMIN:cloud,FACTORY_LEDGER:ledger});
    try{
      await mod.default.scheduled({cron:CRON},ready,{});
      assert.equal(receipt.status,'queue_probe_complete');assert.equal(receipt.github_queue_read_verified,true);
      assert.equal(receipt.cloudflare_admin_read_verified,true);assert.equal(receipt.cloudflare_mutations,0);
      assert.ok(!JSON.stringify(receipt).includes(github));assert.ok(!JSON.stringify(receipt).includes(cloud));
      assert.deepEqual(calls.map(x=>x.method),['GET','GET','PUT','DELETE']);
      await assert.rejects(mod.default.scheduled({cron:CRON},ready,{}));
      assert.equal(calls.filter(x=>x.target.startsWith(API)).length,1);
      journal.clear();calls.length=0;adminStatus=403;
      await mod.default.scheduled({cron:CRON},ready,{});
      assert.equal(receipt.status,'queue_probe_complete');assert.equal(receipt.cloudflare_admin_read_verified,false);
      assert.equal(receipt.cloudflare_mutations,0);
      journal.clear();calls.length=0;req.worker_name='wrong-worker';
      await assert.rejects(mod.default.scheduled({cron:CRON},ready,{}),/queue_probe_contract_rejected/);
      assert.equal(calls.length,1);
    }finally{globalThis.fetch=original;}
  });
});
