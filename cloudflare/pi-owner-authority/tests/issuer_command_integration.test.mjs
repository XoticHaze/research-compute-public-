// Public, synthetic-only integration check of the actual fixed issuer publisher.
// All keys, GitHub responses and filesystem data exist only in a disposable test dir.
// No actual gh credential, private repository access, Cloudflare admin or Pi mutation.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash,createPublicKey,generateKeyPairSync} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {chmodSync,copyFileSync,existsSync,mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const HERE=dirname(fileURLToPath(import.meta.url));
const SRC=join(HERE,'..','src');
const SCHEMA='commandcenter.pi.release_request.v1';
const iso=t=>new Date(t).toISOString().replace(/\.\d{3}Z$/,'Z');
const hex=b=>createHash('sha256').update(b).digest('hex');
const gitHash=b=>createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex');
const ORIGIN='repos/XoticHaze/CommandCenter-gate-control/contents/';
const FAKE_GH=String.raw\`#!/usr/bin/env node
const fs=require('node:fs'), crypto=require('node:crypto');
const args=process.argv.slice(2);
const target=args.find(s=>s.startsWith('repos/XoticHaze/CommandCenter-gate-control/contents/'));
if(args[0]!=='api'||!target){process.stderr.write('invalid mock gh args');process.exit(2);}
const rest=target.slice('repos/XoticHaze/CommandCenter-gate-control/contents/'.length);
const p=rest.split('?')[0], ref=(new URL('https://synthetic.invalid/?'+(rest.split('?')[1]||''))).searchParams.get('ref')||'pi-node-inbox';
const db=JSON.parse(fs.readFileSync(process.env.MOCK_GH_DB,'utf8'));
const key=ref+'/'+p, old=db[key];
const gitHash=b=>crypto.createHash('sha1').update('blob '+b.length+'\\0').update(b).digest('hex');
if(!args.includes('PUT')) {
 if(!old){process.stderr.write('gh: Not Found (HTTP 404)');process.exit(1);}
 const raw=Buffer.from(old,'base64');
 process.stdout.write(JSON.stringify({encoding:'base64',content:raw.toString('base64'),size:raw.length,sha:gitHash(raw)}));
} else {
 const input=JSON.parse(fs.readFileSync(0,'utf8'));
 if(input.branch!=='pi-node-inbox'||!input.content||ref!=='pi-node-inbox')process.exit(3);
 if(old&&input.sha!==gitHash(Buffer.from(old,'base64')))process.exit(4);
 if(!old&&input.sha)process.exit(5);
 const raw=Buffer.from(input.content,'base64');
 db[key]=raw.toString('base64');
 fs.writeFileSync(process.env.MOCK_GH_DB,JSON.stringify(db));
 process.stdout.write(JSON.stringify({content:{sha:gitHash(raw)}}));
}
\`;
test('actual fixed Linux publisher: local review, one-use journal, private Git mock, exact recovery and denial',()=>{
  const dir=mkdtempSync(join(tmpdir(),'ccpi-issuer-synthetic-'));
  try {
    const root=join(dir,'issuer-root'),bin=join(dir,'bin'),local=join(dir,'modules');
    for(const d of [root,bin,local,join(root,'reviews'),join(root,'manifest-reviews'),join(root,'review-bindings')])
      mkdirSync(d,{recursive:true,mode:0o700});
    const {privateKey:key}=generateKeyPairSync('ed25519');
    const {publicKey:rootPub}=generateKeyPairSync('ed25519');
    const identity=hex(createPublicKey(key).export({format:'der',type:'spki'}));
    const rootFingerprint=hex(rootPub.export({format:'der',type:'spki'}));
    assert.notEqual(identity,rootFingerprint);
    const privatePem=key.export({format:'pem',type:'pkcs8'});
    writeFileSync(join(root,'issuer-key.pem'),privatePem,{mode:0o600});
    writeFileSync(join(root,'pi-root-fingerprint'),rootFingerprint+'\n',{mode:0o600});
    const source=readFileSync(join(SRC,'independent_release_issuer_command.mjs'),'utf8');
    const anchored="const ROOT='/var/lib/commandcenter/pi-release-issuer';";
    assert.equal(source.split(anchored).length,2,'production path anchor must be unique');
    const command=join(local,'independent_release_issuer_command.mjs');
    writeFileSync(command,source.replace(anchored,'const ROOT='+JSON.stringify(root)+';'),{mode:0o600});
    copyFileSync(join(SRC,'independent_release_issuer.mjs'),join(local,'independent_release_issuer.mjs'));
    const mock=join(bin,'gh');
    writeFileSync(mock,FAKE_GH,{mode:0o700});chmodSync(mock,0o700);
    const dbPath=join(dir,'synthetic-private-queue.json');
    const now=Date.now(),generation='r'+'a'.repeat(12),sourceSha='a'.repeat(40),priorSha='b'.repeat(40);
    const manifest=Buffer.from(JSON.stringify({schema:'commandcenter.pi.release_artifact.v1',
      source_repo:'XoticHaze/CommandCenter',source_sha:sourceSha,source_ref:'main',expected_release:generation,
      file_count:23,files:Object.fromEntries(Array.from({length:23},(_,i)=>['file'+i,'d'.repeat(40)]))}));
    const digest=hex(manifest);
    const request={schema:SCHEMA,node_id:'cc-pi4',action:'pi.release.apply',
      source_repo:'XoticHaze/CommandCenter',source_sha:sourceSha,expected_release:generation,
      request_id:'ccpi2-'+digest+'-'+'1'.repeat(16),created_at:iso(now-2000),expires_at:iso(now+300000)};
    const review={schema:'commandcenter.pi.independent_release_review.v1',review_id:'1'.repeat(32),
      request_id:request.request_id,source_sha:sourceSha,manifest_sha256:digest,expected_release:generation,
      not_before:iso(now-3000),expires_at:iso(now+600000)};
    const predecessor='r'+'c'.repeat(12);
    const oldRequest={schema:SCHEMA,node_id:'cc-pi4',action:'pi.release.apply',
      source_repo:request.source_repo,request_id:'prior-request-1',source_sha:priorSha,expected_release:predecessor};
    const priorReceipt={schema:'commandcenter.pi.release_result.v1',node_id:'cc-pi4',action:'pi.release.apply',
      request_id:oldRequest.request_id,source_sha:priorSha,predecessor,status:'passed',replay_allowed:false,
      message:'exact main source accepted; new generation '+generation};
    const q={};
    function put(ref,path,bytes){q[ref+'/'+path]=Buffer.from(bytes).toString('base64');}
    put('pi-node-inbox','pi-node/root-release-proposal.json',JSON.stringify(request));
    put('pi-node-inbox','pi-node/release-request.json',JSON.stringify(oldRequest));
    put('pi-node-outbox','pi-node/release-results/'+oldRequest.request_id+'.json',JSON.stringify(priorReceipt));
    put('pi-node-release-artifacts','pi-node/artifacts/ccpi-update-'+sourceSha.slice(0,12)+'/manifest.json',manifest);
    writeFileSync(dbPath,JSON.stringify(q),{mode:0o600});
    writeFileSync(join(root,'reviews',request.request_id+'.json'),JSON.stringify(review),{mode:0o600});
    const env={...process.env,PATH:bin+':'+dirname(process.execPath)+':/usr/bin:/bin',
      MOCK_GH_DB:dbPath,CI:'',GITHUB_ACTIONS:'',GH_TOKEN:'',GITHUB_TOKEN:''};
    const run=flag=>spawnSync(process.execPath,[command,flag],{env,encoding:'utf8',timeout:8000});
    const ident=run('--public-identity');
    assert.equal(ident.status,0,ident.stderr);assert.equal(JSON.parse(ident.stdout).sha256,identity);
    const first=run('--poll');
    assert.equal(first.status,0,first.stderr);
    const receipt=JSON.parse(first.stdout);
    assert.equal(receipt.root_dispatch_claimed,false);
    assert.equal(receipt.issuer_sha256,identity);
    assert.equal(receipt.request_id,request.request_id);
    const published=JSON.parse(readFileSync(dbPath,'utf8'));
    const item=published['pi-node-inbox/pi-node/root-release-permit.json'];
    assert.ok(item,'fixed Git transport must publish permit');
    const envelope=JSON.parse(Buffer.from(item,'base64').toString('utf8'));
    assert.equal(envelope.permit.request_id,request.request_id);
    assert.equal(envelope.permit.permit_id,review.review_id);
    assert.equal(receipt.permit_blob,gitHash(Buffer.from(item,'base64')));
    const binding=join(root,'review-bindings',review.review_id+'.json');
    assert.ok(existsSync(binding),'protected durable review-ID binding required');
    assert.equal(JSON.parse(readFileSync(binding,'utf8')).request_id,request.request_id);
    const second=run('--poll');
    assert.equal(second.status,0,second.stderr);
    assert.match(second.stdout,/EXACT_PERMIT_ALREADY_PUBLISHED/);
    assert.equal(JSON.parse(readFileSync(dbPath,'utf8'))['pi-node-inbox/pi-node/root-release-permit.json'],item);
    const newProposal={...request,request_id:'ccpi2-'+digest+'-'+'2'.repeat(16)};
    const changed=JSON.parse(readFileSync(dbPath,'utf8'));
    changed['pi-node-inbox/pi-node/root-release-proposal.json']=Buffer.from(JSON.stringify(newProposal)).toString('base64');
    writeFileSync(dbPath,JSON.stringify(changed));
    const missingReview=run('--poll');
    assert.equal(missingReview.status,0,missingReview.stderr);
    assert.match(missingReview.stdout,/NO_INDEPENDENT_REVIEW/);
    assert.equal(JSON.parse(readFileSync(dbPath,'utf8'))['pi-node-inbox/pi-node/root-release-permit.json'],item);
    assert.equal(existsSync(join(root,'reviews',newProposal.request_id+'.json')),false);
  } finally {rmSync(dir,{recursive:true,force:true});}
});
