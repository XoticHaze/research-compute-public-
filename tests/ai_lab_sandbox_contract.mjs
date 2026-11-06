import assert from 'node:assert/strict';
import {
  AI_LAB_SCHEMA, AI_LAB_MAX_NOTES, aiLabAsset, aiLabStub, labStateFetch, validateLabNote,
} from '../cloudflare/operator-console/src/ai_lab_sandbox.js';

class MemoryStorage {
  constructor() { this.data = new Map(); }
  get(key) { return Promise.resolve(this.data.get(key)); }
  put(key, value) { this.data.set(key, value); return Promise.resolve(); }
  delete(key) { this.data.delete(key); return Promise.resolve(true); }
  transaction(fn) { return fn(this); }
}

const uuid = n => '00000000-0000-4000-8000-' + String(n).padStart(12, '0');
const body = (n, text = 'fictional data only') =>
  ({ schema: AI_LAB_SCHEMA, id: uuid(n), text });
const request = (method, path, payload) => new Request('https://operator-state.internal' + path, {
  method, ...(payload ? { headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload) } : {}),
});

const store = new MemoryStorage();
let result = await labStateFetch(request('GET', '/lab/latest'), store);
assert.equal(result.status, 200);
assert.deepEqual((await result.json()).notes, []);

result = await labStateFetch(request('POST', '/lab/append', body(1)), store);
assert.equal(result.status, 201);
assert.equal((await result.json()).durable_readback_verified, true);
result = await labStateFetch(request('POST', '/lab/append', body(1)), store);
assert.equal(result.status, 200);
assert.equal((await result.json()).repeated, true);
assert.equal((await (await labStateFetch(request('GET', '/lab/latest'), store)).json()).notes.length, 1);

for (let n = 2; n <= 49; n++) {
  assert.equal((await labStateFetch(request('POST', '/lab/append', body(n)), store)).status, 201);
}
const history = await (await labStateFetch(request('GET', '/lab/latest'), store)).json();
assert.equal(history.notes.length, AI_LAB_MAX_NOTES);
assert.equal(history.notes[0].id, uuid(10));
assert.equal(history.notes.at(-1).id, uuid(49));
assert.equal(history.model_status, 'NOT_CONNECTED');

for (const invalid of [
  null, [], { ...body(50), model: 'nvidia/nemotron-3-ultra-550b-a55b' },
  { ...body(50), text: '' }, { ...body(50), text: 'x'.repeat(1201) },
  { ...body(50), text: 'bad\u0000secret' }, { ...body(50), id: '../escape' },
  { ...body(50), schema: 'operator.ai_lab.executor.v1' },
]) assert.throws(() => validateLabNote(invalid));

result = await labStateFetch(request('POST', '/lab/append', { ...body(50), token: 'exfil' }), store);
assert.equal(result.status, 400);
assert.equal((await (await labStateFetch(request('GET', '/lab/latest'), store)).json()).notes.length, 40);

const badStore = new MemoryStorage();
await badStore.put('lab_notes_v1', { bad: 'object' });
assert.equal((await labStateFetch(request('GET', '/lab/latest'), badStore)).status, 503);
assert.equal((await labStateFetch(request('POST', '/lab/append', body(1)), badStore)).status, 503);

result = await labStateFetch(request('DELETE', '/lab/clear'), store);
assert.equal(result.status, 200);
assert.equal((await result.json()).notes_cleared, true);
assert.equal((await (await labStateFetch(request('GET', '/lab/latest'), store)).json()).notes.length, 0);

const names = [];
const mockEnv = {
  OPERATOR_STATE: {
    idFromName: name => { names.push(name); return name; },
    get: id => ({ id }),
  },
};
const alice = { email: 'alice@example.test', sub: 'alice' };
const bob = { email: 'bob@example.test', sub: 'bob' };
assert.equal((await aiLabStub(mockEnv, alice)).id, (await aiLabStub(mockEnv, alice)).id);
assert.notEqual((await aiLabStub(mockEnv, alice)).id, (await aiLabStub(mockEnv, bob)).id);
assert(names.every(name => name.startsWith('ai-lab/v1/') && !name.includes('@')));
await assert.rejects(() => aiLabStub(mockEnv, { email: 'test@example.test', sub: '' }));

const page = aiLabAsset('/ai-lab');
assert.equal(page.status, 200);
assert.match(page.headers.get('content-security-policy'), /script-src 'self'/);
assert.doesNotMatch(await page.text(), /NVIDIA_API_KEY|Bearer |cloudflare.*secret/i);
const js = await aiLabAsset('/ai-lab/client.js').text();
assert.match(js, /textContent = note.text/);
assert.doesNotMatch(js, /innerHTML|eval\s*\(/);
assert.equal(aiLabAsset('/random-route'), null);

console.log('AI_LAB_CONTRACT=PASS; model_invocation=false; private_actions_compute=false');
