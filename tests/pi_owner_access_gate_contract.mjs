import assert from 'node:assert/strict';
import worker, {operatorDecisionRequestIsSameOrigin} from '../cloudflare/operator-console/src/index.js';
const url = 'https://mmibkr-operator-console.slenderiq.workers.dev';
for (const path of [
  '/operator/pi-owner-approval',
  '/operator/pi-owner-approval.js',
  '/api/pi-owner/status',
  '/api/pi-owner/receipt?request_id=synthetic-123',
]) {
  const response = await worker.fetch(new Request(url+path), {});
  assert.equal(response.status,403,path+' must require Cloudflare Access identity');
  assert.deepEqual(await response.json(),{error:'access_denied'});
}
for (const path of [
  '/api/pi-owner/initialize','/api/pi-owner/enroll','/api/pi-owner/approve',
]) {
  const response = await worker.fetch(new Request(url+path,{
    method:'POST',headers:{'content-type':'application/json','origin':url},
    body:'{}',
  }), {});
  assert.equal(response.status,403,path+' must require Cloudflare Access before POST');
  assert.deepEqual(await response.json(),{error:'access_denied'});
}
assert.equal(operatorDecisionRequestIsSameOrigin(new Request(url+'/api/pi-owner/approve',{
  method:'POST',
  headers:{origin:url,'content-type':'application/json','sec-fetch-site':'same-origin'},
  body:'{}',
})),true);
for (const headers of [
  {origin:'https://untrusted.example','content-type':'application/json'},
  {'content-type':'application/json'},
  {origin:url,'content-type':'text/plain'},
  {origin:url,'content-type':'application/json','sec-fetch-site':'cross-site'},
]) {
  assert.equal(operatorDecisionRequestIsSameOrigin(new Request(url+'/api/pi-owner/approve',{
    method:'POST',headers,body:'{}',
  })),false);
}
console.log('Pi owner API and HTML: Access-first and exact same-origin JSON protection PASSED');
