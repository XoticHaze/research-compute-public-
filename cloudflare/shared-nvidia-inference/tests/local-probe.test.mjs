import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createCaller } from "../local-probe/src/index.js";

const url = "http://127.0.0.1:8787/run-once";
const call = (target = url, body) => new Request(target, { method: "POST", ...(body === undefined ? {} : { body }) });

test("local caller configuration is private and has only the intended remote service binding", async () => {
  const config = JSON.parse(await readFile(new URL("../local-probe/wrangler.jsonc", import.meta.url), "utf8"));
  assert.equal(config.name, "cc-shared-nvidia-operator-local-caller");
  assert.equal(config.workers_dev, false);
  assert.equal(config.preview_urls, false);
  assert.equal(config.routes, undefined);
  assert.equal(config.route, undefined);
  assert.equal(config.secrets_store_secrets, undefined);
  assert.equal(config.vars, undefined);
  assert.deepEqual(config.services, [{ binding: "NVIDIA_SERVICE", service: "cc-shared-nvidia-inference", remote: true }]);
});

test("local caller rejects wrong ingress and body without invoking the service", async () => {
  const caller = createCaller();
  let calls = 0;
  const env = { NVIDIA_SERVICE: { async fetch() { calls++; return new Response(); } } };
  assert.equal((await caller.fetch(call("http://example.com/run-once"), env)).status, 404);
  assert.equal((await caller.fetch(call("http://127.0.0.1:8787/run-once?model=anything"), env)).status, 404);
  assert.equal((await caller.fetch(call(url, "secret payload"), env)).status, 400);
  assert.equal(calls, 0);
});

test("a zero-byte POST stream is admissible but no request data is forwarded", async () => {
  const caller = createCaller();
  const received = [];
  const empty = new Request(url, {
    method: "POST",
    body: "",
    headers: { "content-length": "0" },
  });
  const env = { NVIDIA_SERVICE: { async fetch(request) {
    received.push({ url: request.url, method: request.method, body: request.body });
    return new Response(JSON.stringify({ error: "diagnostic_not_admitted" }), { status: 503 });
  } } };
  const reply = await caller.fetch(empty, env);
  assert.equal(reply.status, 502);
  assert.equal((await reply.json()).classification, "unexpected_upstream_receipt");
  assert.deepEqual(received, [{
    url: "https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia",
    method: "POST", body: null,
  }]);
  assert.equal((await caller.fetch(call(), env)).status, 409);
});

test("missing service binding fails closed and does not consume one-shot slot", async () => {
  const caller = createCaller();
  assert.equal((await caller.fetch(call(), {})).status, 503);
  const env = { NVIDIA_SERVICE: { async fetch() { return new Response(JSON.stringify({
    schema: "commandcenter.shared_nvidia_private_diagnostic.v1",
    classification: "completion_http_200", calls_made: 2,
  }), { status: 200 }); } } };
  assert.equal((await caller.fetch(call(), env)).status, 200);
});

test("one bound call only, fixed private destination, unexpected fields dropped", async () => {
  const caller = createCaller();
  const called = [];
  const env = { NVIDIA_SERVICE: { async fetch(request) {
    called.push({ url: request.url, method: request.method, body: request.body });
    return new Response(JSON.stringify({
      schema: "commandcenter.shared_nvidia_private_diagnostic.v1",
      catalog_http_status: 200, completion_http_status: 403,
      catalog_includes_model: true, catalog_count: 20,
      completion_response_valid: false, exact_reply_observed: false,
      elapsed_ms: 102, calls_made: 2, classification: "provider_access_rejected",
      API_KEY: "DO_NOT_EXPOSE", raw_provider_body: "DO_NOT_EXPOSE",
    }), { status: 503 });
  } } };
  const response = await caller.fetch(call(), env);
  assert.equal(response.status, 502);
  const content = await response.text();
  assert.equal(content.includes("DO_NOT_EXPOSE"), false);
  const receipt = JSON.parse(content);
  assert.equal(receipt.completion_http_status, 403);
  assert.equal(receipt.classification, "provider_access_rejected");
  assert.deepEqual(called, [{
    url: "https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia",
    method: "POST", body: null,
  }]);
  assert.equal((await caller.fetch(call(), env)).status, 409);
  assert.equal(called.length, 1);
});

test("local-only role selector preserves private destination, rejects injection and redacts upstream fields",async()=>{
 const caller=createCaller();
 const requests=[];
 const env={NVIDIA_SERVICE:{async fetch(req){
   requests.push({url:req.url,body:await req.text()});
   return new Response(JSON.stringify({
     schema:"commandcenter.nvidia_synthetic_roles.v1",batch:0,
     status:"batch_complete",catalog_http:200,catalog_count:85,
     catalog_model_ids:["openai/gpt-oss-20b"],eligible_count:1,
     eligible_model_ids:["openai/gpt-oss-20b"],calls:5,elapsed_ms:350,
     results:[{model:"openai/gpt-oss-20b",results:[
       {task:"tool_call",http_status:200,latency_ms:120,format_valid:true,passed:true}
     ]}], SECRET:"LEAK",raw_answer:"LEAK"
   }),{status:200});
 }}};
 const url="http://127.0.0.1:8787/roles-batch";
 const bad=new Request(url,{method:"POST",headers:{
   "content-type":"application/json","content-length":"14"
 },body:'{"batch":"0"}'});
 assert.equal((await caller.fetch(bad,env)).status,400);
 const body='{"batch":0}';
 const good=new Request(url,{method:"POST",headers:{
   "content-type":"application/json","content-length":String(body.length)
 },body});
 const response=await caller.fetch(good,env);
 assert.equal(response.status,200);
 const raw=await response.text();
 assert.equal(raw.includes("LEAK"),false);
 const receipt=JSON.parse(raw);
 assert.equal(receipt.results[0].results[0].passed,true);
 assert.deepEqual(requests,[{url:"https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-roles",body}]);
 assert.equal((await caller.fetch(call(),env)).status,409);
});

test("five distinct synthetic batches per existing local caller, sixth and replay denied",async()=>{
 const caller=createCaller();
 let calls=0;
 const env={NVIDIA_SERVICE:{async fetch(req){
   calls++;
   const params=JSON.parse(await req.text());
   return new Response(JSON.stringify({
     schema:"commandcenter.nvidia_synthetic_roles.v1",batch:params.batch,
     status:"batch_complete",calls:1,catalog_http:200,catalog_count:85,
     catalog_model_ids:["openai/gpt-oss-20b"],eligible_count:1,
     eligible_model_ids:["openai/gpt-oss-20b"],results:[]
   }),{status:200});
 }}};
 const input=n=>{
   const body=JSON.stringify({batch:n});
   return new Request("http://127.0.0.1:8787/roles-batch",{method:"POST",
     headers:{"content-type":"application/json","content-length":String(body.length)},body});
 };
 for(let n=0;n<5;n++)assert.equal((await caller.fetch(input(n),env)).status,200);
 assert.equal((await caller.fetch(input(0),env)).status,409);
 assert.equal((await caller.fetch(input(5),env)).status,409);
 assert.equal(calls,5);
});
