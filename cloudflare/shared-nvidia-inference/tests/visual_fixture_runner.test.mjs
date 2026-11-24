import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {verifyFixture,sanitizeCandidate,runVisualFixture,FIXTURE_ID,MODEL,IMAGE_BYTES,IMAGE_SHA,MAX_OUTPUT_TOKENS} from "../src/visual_fixture_runner.js";
import {createVisualFixtureCaller} from "../local-probe/src/visual_fixture_caller.js";

const makeDoc=()=>({cards:Array.from({length:6},(_,i)=>({card:"0"+(i+1),classification:"other",
 display_value:"test",supported_value:null,bbox_px:null,rationale:"fictional mock output"})),protected_action_recommended:false});
const wrong={fixture_id:FIXTURE_ID,image_base64:Buffer.alloc(IMAGE_BYTES).toString("base64")};
test("wrong same-size image, arbitrary fields and URL cannot reach provider",async()=>{
 assert.equal(await verifyFixture(wrong),false);
 assert.equal(await verifyFixture({...wrong,model:"other"}),false);
 assert.equal(await verifyFixture({fixture_id:FIXTURE_ID,image_url:"https://example.com/image.png"}),false);
 let calls=0;
 await assert.rejects(runVisualFixture({input:wrong,providerFetch:async()=>{calls++;}}));
 assert.equal(calls,0);
});
test("structured output is bounded and rationale redacted; clean and defect classes are not auto-scored",()=>{
 const d=makeDoc();const c=sanitizeCandidate(d);
 assert.equal(c.cards.length,6);assert.equal(c.cards[0].rationale_present,true);
 assert.equal(Object.hasOwn(c.cards[0],"rationale"),false);
 d.cards[1].card="01";assert.equal(sanitizeCandidate(d),null);
 const e=makeDoc();e.cards[0].bbox_px=[0,0,1201,760];assert.equal(sanitizeCandidate(e),null);
 const f=makeDoc();f.cards[0].supported_value=true;assert.equal(sanitizeCandidate(f),null);
 const g=makeDoc();g.cards[0].display_value="x".repeat(201);assert.equal(sanitizeCandidate(g),null);
 const h=makeDoc();h.commands=["execute"];assert.equal(sanitizeCandidate(h),null);
});
test("loopback rejects wrong method, arbitrary host and wrong same-size PNG before binding",async()=>{
 const caller=createVisualFixtureCaller();let calls=0;
 const env={NVIDIA_SERVICE:{fetch:async()=>{calls++;}}};
 const body=JSON.stringify(wrong),headers={"Content-Type":"application/json","Content-Length":String(body.length)};
 const post=url=>new Request(url,{method:"POST",headers,body});
 assert.equal((await caller.fetch(post("https://example.com/visual-fixture"),env)).status,404);
 assert.equal((await caller.fetch(post("http://127.0.0.1/visual-fixture"),env)).status,400);
 assert.equal((await caller.fetch(new Request("http://127.0.0.1/visual-fixture"),env)).status,404);
 assert.equal(calls,0);
});
test("actual fixed fixture through mocked provider and one-use service binding",{
 skip:!process.env.NVIDIA_VISUAL_FIXTURE_PNG
},async()=>{
 const input={fixture_id:FIXTURE_ID,image_base64:readFileSync(process.env.NVIDIA_VISUAL_FIXTURE_PNG).toString("base64")};
 assert.equal(await verifyFixture(input),true);
 let calls=0;
 const providerFetch=async(endpoint,opts)=>{
  calls++;assert.equal(endpoint,"https://integrate.api.nvidia.com/v1/chat/completions");
  assert.equal(opts.redirect,"manual");const body=JSON.parse(opts.body);
  assert.equal(body.model,MODEL);assert.equal(body.max_tokens,MAX_OUTPUT_TOKENS);
  assert.equal(body.messages[0].content[1].image_url.url,"data:image/png;base64,"+input.image_base64);
  const text=body.messages[0].content[0].text;
  assert.ok(text.includes("source_truth"));assert.ok(!text.includes("expected_findings"));
  assert.ok(!text.includes("expected_boxes"));assert.ok(!text.includes("gold_truth"));
  return new Response(JSON.stringify({choices:[{message:{content:JSON.stringify(makeDoc())}}]}),{status:200});
 };
 const caller=createVisualFixtureCaller();
 const env={NVIDIA_SERVICE:{fetch:async(req)=>{
  const data=await req.json();const r=await runVisualFixture({input:data,providerFetch,now:()=>100});
  return new Response(JSON.stringify(r),{status:r.status==="candidate_unreviewed"?200:503});
 }}};
 const body=JSON.stringify(input),req=()=>new Request("http://127.0.0.1/visual-fixture",{method:"POST",
  headers:{"Content-Type":"application/json","Content-Length":String(body.length)},body});
 const response=await caller.fetch(req(),env);
 assert.equal(response.status,200);const receipt=await response.json();
 assert.equal(receipt.image_sha256,IMAGE_SHA);assert.equal(receipt.production_admitted,false);
 assert.equal(receipt.human_review_required,true);assert.equal(receipt.rationale_exported,false);
 assert.equal(receipt.candidate.cards.length,6);assert.equal(receipt.candidate.cards[0].rationale_present,true);
 assert.equal((await caller.fetch(req(),env)).status,409);assert.equal(calls,1);
});
