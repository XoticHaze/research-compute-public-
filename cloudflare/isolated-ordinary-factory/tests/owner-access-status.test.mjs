import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from '../scripts/prepare.mjs';

// No real owner email, AUD, Cloudflare token, or API call. Exercise the actual
// pinned-derived factory fetch handler with synthetic ctx.access identity.
const ACCOUNT='ab'.repeat(16);
const AUD='9a'.repeat(32); // Access application audience tag, exactly 64 hex chars
const ALLOWED='owner@example.test';
const URL='https://cc-ordinary-worker-factory.example.test';
async function fixture(fn) {
  const dir=mkdtempSync(join(tmpdir(),'factory-access-contract-'));
  try {
    build(ACCOUNT,{outDir:dir});
    const mod=await import(pathToFileURL(join(dir,'src','index.js')).href);
    const env={
      FACTORY_ACCOUNT_ID:ACCOUNT,
      FACTORY_ACCESS_AUD:AUD,
      FACTORY_ALLOWED_EMAILS:ALLOWED,
      FACTORY_EXECUTOR_ENABLED:'0',FACTORY_CREATE_ENABLED:'0',
      FACTORY_INSPECT_ENABLED:'0',FACTORY_SCOPED_TOKEN_ENABLED:'0',
      FACTORY_STAGE_VERSION_ENABLED:'0',FACTORY_PROPOSAL_ONLY:'1',
      FACTORY_MACHINE_READONLY_ENABLED:'0',FACTORY_MACHINE_INSPECT_ENABLED:'0',
    };
    const identity=(aud=AUD,email=ALLOWED)=>({
      access:{aud,getIdentity:async()=>({email})}
    });
    const call=(pathname='/v1/status',ctx=identity(),overrides={},method='GET')=>
      mod.default.fetch(new Request(URL+pathname,{method}),{...env,...overrides},ctx);
    await fn({call,env,identity});
  } finally {rmSync(dir,{recursive:true,force:true});}
}
test('matching Cloudflare Access exact AUD and owner email grants status only, all operations off',async()=>{
  await fixture(async({call})=>{
    assert.match(AUD,/^[a-f0-9]{64}$/);
    const res=await call();
    assert.equal(res.status,200);
    assert.equal(res.headers.get('cache-control'),'private, no-store');
    const data=await res.json();
    assert.equal(data.schema,'commandcenter.cloudflare.factory_status.v1');
    assert.equal(data.admitted,false);
    assert.equal(data.ordinary_creation,false);
    assert.equal(data.proposal_only,true);
    assert.equal(data.token_values_returned,false);
    assert.ok(!JSON.stringify(data).includes(ALLOWED));
    assert.ok(!JSON.stringify(data).includes(AUD));
  });
});
test('missing ctx.access, incorrectly prefixed AUD and other email deny owner status',async()=>{
  await fixture(async({call,identity})=>{
    for (const ctx of [{},identity('aud-'+AUD,ALLOWED),
        identity(AUD,'other@example.test'),identity(AUD,'')]) {
      const res=await call('/v1/status',ctx);
      assert.equal(res.status,403);
      assert.equal((await res.json()).error,'denied_or_unavailable');
    }
  });
});
test('owner identity accepts case/whitespace normalization, still requires correct fixed account',async()=>{
  await fixture(async({call,identity})=>{
    assert.equal((await call('/v1/status',identity(AUD,' Owner@Example.Test '))).status,200);
    const wrong=await call('/v1/status',identity(),{FACTORY_ACCOUNT_ID:'cd'.repeat(16)});
    assert.equal(wrong.status,403);
  });
});
test('even authenticated owner cannot mutate while factory executor flag is disabled',async()=>{
  await fixture(async({call})=>{
    assert.equal((await call('/v1/execute',undefined,{},'POST')).status,403);
    assert.equal((await call('/v1/proposal')).status,403);
    assert.equal((await call('/v1/approve',undefined,{},'POST')).status,403);
  });
});
