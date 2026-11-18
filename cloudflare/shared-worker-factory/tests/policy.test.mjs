import test from 'node:test';
import assert from 'node:assert/strict';
import {validateRequest,workerEditorPolicy,isOrdinaryWorker,SCHEMA} from '../src/policy.js';

const now=1800000000;
const mk=(operation='ordinary_worker.create')=>({
  schema:SCHEMA,operation,request_id:'a'.repeat(32),
  worker_name:'example-project-worker',expires_at:now+120,
  ...(operation==='existing_worker.editor_token.issue'
    ?{worker_id:'b'.repeat(32),token_ttl_hours:24}:{}),
});
test('ordinary create requires exact bounded fields and fresh expiry',()=>{
  assert.equal(validateRequest(mk(),now).operation,'ordinary_worker.create');
  assert.throws(()=>validateRequest({...mk(),arbitrary_shell:'bash'},now));
  assert.throws(()=>validateRequest({...mk(),expires_at:now+301},now));
  assert.throws(()=>validateRequest({...mk(),expires_at:now-1},now));
  assert.throws(()=>validateRequest({...mk(),request_id:'wrong'},now));
});
test('reserved neutral, signer, console and factory targets are excluded',()=>{
  for(const name of ['reference-release-broker-v1','reference-maintenance-authority-v1',
    'ccpi-owner-cloudflare-authority','fleet-authority','mmibkr-operator-console',
    'shared-compute-worker-factory','example--worker','../../etc/passwd']) {
    assert.equal(isOrdinaryWorker(name),false,name);
  }
  assert.equal(isOrdinaryWorker('lpc-site-v2'),true);
  assert.equal(isOrdinaryWorker('new-project-worker'),true);
});
test('scoped credential issuance requires fixed existing worker and TTL',()=>{
  assert.equal(validateRequest(mk('existing_worker.editor_token.issue'),now).token_ttl_hours,24);
  assert.throws(()=>validateRequest({...mk('existing_worker.editor_token.issue'),token_ttl_hours:999},now));
  assert.throws(()=>validateRequest({...mk('existing_worker.editor_token.issue'),worker_id:'wrong'},now));
});
test('individual editor policy never grants product Admin or cross-account scope',()=>{
  const p=workerEditorPolicy('a'.repeat(32),'b'.repeat(32));
  assert.equal(p.length,1);
  assert.equal(p[0].permission_groups[0].id,'7e79ec33834341f28dd431ab73884400');
  assert.deepEqual(Object.keys(p[0].resources),['com.cloudflare.api.account.'+'a'.repeat(32)]);
  assert.deepEqual(Object.keys(p[0].resources['com.cloudflare.api.account.'+'a'.repeat(32)]),
    ['com.cloudflare.edge.worker.script.'+'b'.repeat(32)]);
  assert.throws(()=>workerEditorPolicy('invalid','b'.repeat(32)));
});
