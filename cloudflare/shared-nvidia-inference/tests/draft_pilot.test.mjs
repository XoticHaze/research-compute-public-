import test from "node:test";
import assert from "node:assert/strict";
import {DRAFT_CASES,DRAFT_MODEL,draftRequest,scoreDraft,templateBaseline} from "../src/draft_pilot_fixtures.js";
import {runFixedDraftPilot} from "../src/draft_pilot_runner.js";
import {sanitizeDraftReceipt} from "../local-probe/src/draft_receipt.js";

test("four original fictional draft tasks and template baselines are coherent",()=>{
 assert.deepEqual(DRAFT_CASES.map(x=>x.id),["OP01","OP02","CX01","CX02"]);
 for(const x of DRAFT_CASES){
  const score=templateBaseline(x);
  assert.equal(score.passed,true,JSON.stringify({id:x.id,score}));
  assert(x.template.length>90);
 }
 assert.equal(DRAFT_MODEL,"poolside/laguna-xs-2.1");
});

test("fixed draft path makes four real text generation calls and suppresses all generated text",async()=>{
 let count=0,clock=0;
 const receipt=await runFixedDraftPilot({providerFetch:async(url,opts)=>{
  assert.equal(url,"https://integrate.api.nvidia.com/v1/chat/completions");
  assert.equal(opts.redirect,"manual");
  const x=JSON.parse(opts.body);
  assert.equal(x.model,DRAFT_MODEL);
  assert.equal(x.messages[1].content,DRAFT_CASES[count].facts+"\n"+DRAFT_CASES[count].task);
  const body=JSON.stringify({message:DRAFT_CASES[count].template,review_required:true});
  count++;clock+=200;
  return {status:200,async json(){return{choices:[{message:{content:body}}]}}};
 },now:()=>clock});
 assert.equal(count,4);
 assert.equal(receipt.status,"completed_not_human_reviewed");
 assert.equal(receipt.attempted,4);
 assert(receipt.results.every(r=>r.draft_passed&&r.template_passed));
 assert.equal(receipt.model_text_exposed,false);
 const safe=sanitizeDraftReceipt(receipt);
 assert(safe&&safe.results.length===4);
 for(const x of DRAFT_CASES)assert(!JSON.stringify(safe).includes(x.template));
});

test("first provider 429 terminates before further draft calls",async()=>{
 let calls=0;
 const receipt=await runFixedDraftPilot({providerFetch:async()=>{calls++;return{status:429};}});
 assert.equal(calls,1);
 assert.equal(receipt.attempted,1);
 assert.equal(receipt.status,"rate_limited");
 assert.equal(receipt.results[0].http_status,429);
 assert(sanitizeDraftReceipt(receipt));
});

test("fabricated refund approval and invented tracking fail draft review",()=>{
 let draft=JSON.stringify({message:DRAFT_CASES[3].template+" The refund is approved.",review_required:true});
 let r=scoreDraft(draft,DRAFT_CASES[3]);
 assert.equal(r.unsupported_claim_flag,true);assert.equal(r.passed,false);
 draft=JSON.stringify({message:DRAFT_CASES[2].template+" Tracking number: ZX-1234",review_required:true});
 r=scoreDraft(draft,DRAFT_CASES[2]);
 assert.equal(r.unsupported_claim_flag,true);assert.equal(r.passed,false);
});
test("response sanitizer rejects arbitrary user prose or fabricated case IDs",()=>{
 const receipt={schema:"commandcenter.nvidia_fixed_draft_pilot.v1",
  model:DRAFT_MODEL,status:"completed_not_human_reviewed",attempted:4,
  results:DRAFT_CASES.map((x)=>({id:x.id,kind:x.kind,http_status:200,
    latency_ms:100,anchor_groups:x.anchors.length,anchor_groups_met:x.anchors.length,
    format_valid:true,unsupported_claim_flag:false,human_review_flag:true,
    draft_length_ok:true,draft_passed:true,template_passed:true,
    raw_model_text:"SHOULD_NOT_EXPORT_SECRET"}))};
 assert(!JSON.stringify(sanitizeDraftReceipt(receipt)).includes("SHOULD_NOT_EXPORT_SECRET"));
 receipt.results[0].id="other";
 assert.equal(sanitizeDraftReceipt(receipt),null);
});
test("one fictional fixed model and no arbitrary prompts or models",()=>{
 assert.throws(()=>draftRequest(4),/invalid_fixed_draft_case/);
 assert.throws(()=>draftRequest("0"),/invalid_fixed_draft_case/);
 assert.deepEqual(Object.keys(draftRequest(0)).sort(),["max_tokens","messages","model","stream","temperature"]);
 const row=scoreDraft('{"message":"hello","review_required":false}',DRAFT_CASES[0]);
 assert.equal(row.passed,false);
});
