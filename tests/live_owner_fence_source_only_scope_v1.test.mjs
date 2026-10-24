import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root=resolve(import.meta.dirname,'..');
const read=(p)=>readFileSync(resolve(root,p),'utf8');
const candidate=[
  'research/mmibkr_live_owner_fence_contract/live_owner_fence_transition_v1.mjs',
  'research/mmibkr_live_owner_fence_contract/live_owner_fence_sqlite_candidate_v1.mjs',
];

test('candidate modules are outside auto-deployed Fleet Worker source scope',()=>{
  const deploy=read('.github/workflows/fleet-authority-deploy-r2.yml');
  assert.match(deploy,/cloudflare\/fleet-authority\/\*\*/);
  for(const path of candidate){
    assert.equal(path.startsWith('cloudflare/fleet-authority/'),false);
    assert.ok(read(path).length>100);
  }
});
test('production Worker routes and existing source exchange never import candidate authority',()=>{
  const index=read('cloudflare/fleet-authority/src/index.js');
  const exchange=read('cloudflare/fleet-authority/src/source_exchange.js');
  for(const live of ['live_owner_fence_transition_v1','live_owner_fence_sqlite_candidate_v1']){
    assert.equal(index.includes(live),false);
    assert.equal(exchange.includes(live),false);
  }
  assert.equal(index.includes('/v1/live-owner-fence/'),false);
  assert.equal(exchange.includes('/v1/live-owner-fence/'),false);
});
test('no extra Durable Object namespace or binding was required for candidate model',()=>{
  const local=JSON.parse(read('cloudflare/fleet-authority/wrangler.jsonc'));
  const prod=JSON.parse(read('wrangler.jsonc'));
  const bindings=(node)=>(node.durable_objects?.bindings||[])
    .map(x=>[x.name,x.class_name]);
  const expected=[['SOURCE_EXCHANGE','SourceExchange']];
  assert.deepEqual(bindings(local),expected);
  assert.deepEqual(bindings(prod),expected);
});
test('candidate adapter does not call any broker or report a live mutation authorization',()=>{
  const a=read(candidate[1]),b=read(candidate[0]);
  assert.match(a,/live_submit_authorized: false/);
  assert.match(a,/broker_mutation_attempted: false/);
  for(const source of [a,b]){
    assert.doesNotMatch(source,/\.placeOrder\(|\.cancelOrder\(|reqGlobalCancel\(/);
  }
});
