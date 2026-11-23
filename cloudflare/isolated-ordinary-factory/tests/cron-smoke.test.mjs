import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from '../scripts/prepare.mjs';

const ACCOUNT='ab'.repeat(16);
const SHA='b'.repeat(40), ID='c'.repeat(32), RUN='a'.repeat(32);
const CRON='*/5 * * * *';
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
      await mod.default.scheduled({cron:'* * * * *'},env({
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
      const before=calls.filter(x=>x.method==='POST').length;
      await assert.rejects(mod.default.scheduled({cron:CRON},accepted,{}));
      assert.equal(calls.filter(x=>x.method==='POST').length,before);
    }finally{globalThis.fetch=original;}
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
