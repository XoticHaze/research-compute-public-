import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {prepareAssetManifest,uploadAssetSet,staticVersionMetadata,staticReceipt,createStaticVersion} from '../src/native-static-assets.mjs';
const sha=x=>createHash('sha256').update(x).digest('hex');
const target={account_id:'de1c728bdb163060d946122c857f3653',worker_name:'cc-app-static-assets-proof',worker_id:'a'.repeat(32),identity_verified:true,factory_managed:true,ingress_disabled:true,previews_disabled:true};
const bytes=new TextEncoder().encode('<html>static fixture</html>');
const entries=[{path:'/index.html',bytes:bytes.length,sha256:sha(bytes)}];
const read=async()=>bytes;
const admin='fixture-admin-not-a-real-token',upload='fixture.upload.token',done='fixture.completion.token';
const resp=(status,result)=>new Response(JSON.stringify({success:true,result}),{status});
const hash=sha(Buffer.from(bytes).toString('base64')+'html').slice(0,32);
test('manifest uses documented extension-sensitive content ID and independent digest',async()=>{
  const x=await prepareAssetManifest(target,entries,read);
  assert.deepEqual(x.manifest['/index.html'],{hash,size:bytes.length});
  assert.equal(x.total,bytes.length);
});
test('wrong account, worker or unverified ingress is denied before read',async()=>{
  for(const patch of [{account_id:'b'.repeat(32)},{worker_name:'cc-app-agent-fabric'},{ingress_disabled:false},{factory_managed:false}])
    await assert.rejects(prepareAssetManifest({...target,...patch},entries,()=>assert.fail('unexpected read')),/static_asset_target/);
});
test('bad path, digest and duplicate rejected before API',async()=>{
  for(const es of [[{...entries[0],path:'/../index.html'}],[{...entries[0],sha256:'b'.repeat(64)}],[entries[0],entries[0]]])
    await assert.rejects(uploadAssetSet(target,es,read,admin,()=>assert.fail('unexpected fetch')));
});
test('empty bucket uses completion token and receipts omit credentials',async()=>{
  const x=await uploadAssetSet(target,entries,read,admin,async(url,req)=>{
    assert.ok(url.endsWith('/workers/scripts/cc-app-static-assets-proof/assets-upload-session'));
    assert.equal(req.headers.authorization,'Bearer '+admin);
    assert.equal(req.redirect,'manual');
    return resp(200,{jwt:done,buckets:[]});
  });
  assert.equal(x.completion,done);
  assert.equal(x.uploaded_hash_count,0);
  assert.ok(!JSON.stringify(staticReceipt(x)).includes(done));
});
test('unknown, duplicate and malformed buckets fail before uploading bytes',async()=>{
  for(const buckets of [[['b'.repeat(32)]],[[hash],[hash]],[[]]]){
    let n=0;
    await assert.rejects(uploadAssetSet(target,entries,read,admin,async()=>{n++;return resp(200,{jwt:upload,buckets});}),/asset_bucket/);
    assert.equal(n,1);
  }
});
test('uploads base64 multipart using session bearer, requires final 201',async()=>{
  let n=0;
  const x=await uploadAssetSet(target,entries,read,admin,async(url,req)=>{
    n++;
    if(n===1)return resp(200,{jwt:upload,buckets:[[hash]]});
    assert.ok(url.endsWith('/workers/assets/upload?base64=true'));
    assert.equal(req.headers.authorization,'Bearer '+upload);
    const f=req.body.get(hash);
    assert.equal(await f.text(),Buffer.from(bytes).toString('base64'));
    assert.equal(f.type,'text/html; charset=utf-8');
    return resp(201,{jwt:done});
  });
  assert.equal(n,2);assert.equal(x.completion,done);
});
test('redirect and missing completion fail closed',async()=>{
  await assert.rejects(uploadAssetSet(target,entries,read,admin,async()=>new Response('',{status:302})),/asset_api_http_302/);
  let n=0;await assert.rejects(uploadAssetSet(target,entries,read,admin,async()=>++n===1?resp(200,{jwt:upload,buckets:[[hash]]}):resp(200,{})),/asset_completion_missing/);
});
test('off-traffic version only, Worker-first asset config and no bearer in receipt',async()=>{
  const code=new TextEncoder().encode('export default {fetch(){return new Response(null,{status:403})}}');
  const up={completion:done,asset_count:1,asset_bytes:bytes.length,uploaded_hash_count:1};
  const id='11111111-2222-4333-8444-555555555555';
  const receipt=await createStaticVersion(target,up,code,sha(code),'c'.repeat(64),admin,async(url,req)=>{
    assert.ok(url.endsWith('/workers/workers/'+target.worker_id+'/versions?deploy=false'));
    const p=JSON.parse(req.body);
    assert.equal(p.assets.jwt,done);assert.equal(p.assets.config.run_worker_first,true);
    assert.deepEqual(p.bindings,[{type:'assets',name:'ASSETS'}]);
    assert.equal(p.annotations['workers/tag'],'cc-static-'+'c'.repeat(64));
    assert.equal(p.modules[0].content_base64,Buffer.from(code).toString('base64'));
    return resp(201,{id});
  });
  assert.equal(receipt.version_id,id);assert.equal(receipt.production_promoted,false);
  assert.equal(receipt.version_readback_verified,false);
  assert.ok(!JSON.stringify(receipt).includes(done));
});
