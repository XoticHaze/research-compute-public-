import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {build,validateAccount,PROTECTED_ACCOUNT_IDS,FACTORY_NAME,
        SOURCE_PINS} from '../scripts/prepare.mjs';

const ID='ab'.repeat(16);
const SECOND='cd'.repeat(16);
const sha=s=>createHash('sha256').update(s).digest('hex');
function withTemp(callback){
  const root=mkdtempSync(join(tmpdir(),'cc-isolated-factory-'));
  try{return callback(root);} finally{rmSync(root,{recursive:true,force:true});}
}
test('never admit SlenderIQ, protected neutral or malformed account ID',()=>{
  for(const id of [...PROTECTED_ACCOUNT_IDS,'','0'.repeat(31),
      'g'.repeat(32),'A'.repeat(32),null,undefined]){
    assert.throws(()=>validateAccount(id),/ACCOUNT_NOT_ADMITTED/);
  }
  assert.equal(validateAccount(ID),ID);
});
test('pinned modules compile into exact account and explicit fail-closed flags',()=>{
  withTemp(dir=>{
    const manifest=build(ID,{outDir:dir});
    const cfg=JSON.parse(readFileSync(join(dir,'wrangler.jsonc'),'utf8'));
    assert.equal(cfg.name,FACTORY_NAME);
    assert.equal(cfg.account_id,ID);
    assert.equal(cfg.vars.FACTORY_ACCOUNT_ID,ID);
    assert.equal(cfg.vars.FACTORY_INSTALLATION_ROLE,'CC_ISOLATED_ORDINARY_ONLY');
    assert.equal(cfg.vars.FACTORY_ACCESS_AUD,undefined);
    assert.equal(cfg.vars.FACTORY_ALLOWED_EMAILS,undefined);
    for(const key of Object.keys(cfg.vars).filter(x=>x.endsWith('_ENABLED')))
      assert.equal(cfg.vars[key],'0',key);
    assert.equal(cfg.vars.FACTORY_PROPOSAL_ONLY,'1');
    assert.equal(cfg.preview_urls,false);
    assert.equal(cfg.workers_dev,true);
    assert.equal(cfg.exports.FactoryLedger.storage,'sqlite');
    assert.equal(manifest.credentials_in_output,false);
    assert.equal(manifest.cloudflare_mutations,0);
    assert.deepEqual(manifest.source_blob_pins,SOURCE_PINS);
    const ix=readFileSync(join(dir,'src','index.js'),'utf8');
    const st=readFileSync(join(dir,'src','scratch_stage.js'),'utf8');
    const po=readFileSync(join(dir,'src','policy.js'),'utf8');
    const qu=readFileSync(join(dir,'src','queue.js'),'utf8');
    for(const s of [ix,st,po,qu]){
      assert.ok(!s.includes(PROTECTED_ACCOUNT_IDS[0]));
      assert.ok(!s.includes(PROTECTED_ACCOUNT_IDS[1]));
      assert.ok(!s.includes('ORIGINAL_SLENDERIQ_ORDINARY_ONLY'));
    }
    assert.match(ix,/ctx\.access/);
    assert.match(ix,/env\.FACTORY_ACCESS_AUD/);
    assert.match(ix,/env\.FACTORY_ALLOWED_EMAILS/);
    assert.ok(!readFileSync(join(dir,'wrangler.jsonc'),'utf8').includes('"FACTORY_ACCESS_AUD"'));
    assert.ok(!readFileSync(join(dir,'wrangler.jsonc'),'utf8').includes('"FACTORY_ALLOWED_EMAILS"'));
    assert.match(ix,RegExp(ID));
    assert.match(st,RegExp(ID));
    assert.match(po,/cc-ordinary-worker-factory/);
    assert.match(ix,/typeof binding==='string'/);
    assert.match(st,/typeof binding==='string'/);
    assert.match(qu,/typeof env.FACTORY_QUEUE_GITHUB_TOKEN==='string'/);
    assert.doesNotMatch(ix,/wrangler deploy/);
    assert.doesNotMatch(ix,/FACTORY_CREATE_ENABLED:'1'/);
    execFileSync(process.execPath,['--check',join(dir,'src','index.js')]);
    execFileSync(process.execPath,['--check',join(dir,'src','scratch_stage.js')]);
    for(const [name,s] of Object.entries(manifest.source_sha256))
      assert.equal(sha(readFileSync(join(dir,'src',name))),s);
  });
});
test('refuses to overwrite generated source for a different account',()=>{
  withTemp(dir=>{
    build(ID,{outDir:dir});
    assert.throws(()=>build(SECOND,{outDir:dir}),/ACCOUNT_MISMATCH_REFUSE_OVERWRITE/);
    const cfg=JSON.parse(readFileSync(join(dir,'wrangler.jsonc'),'utf8'));
    assert.equal(cfg.account_id,ID);
  });
});
test('same account build is deterministic, reproducible and includes no credential',()=>{
  withTemp(dir=>{
    const first=build(ID,{outDir:dir});
    const second=build(ID,{outDir:dir});
    assert.deepEqual(first,second);
    const payload=readFileSync(join(dir,'manifest.json'),'utf8');
    assert.ok(!payload.includes('Bearer '));
    assert.ok(!payload.includes('CLOUDFLARE_API_TOKEN'));
    assert.ok(!payload.includes('PRIVATE KEY'));
  });
});
