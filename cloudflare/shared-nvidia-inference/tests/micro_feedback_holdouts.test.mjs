import test from 'node:test';
import assert from 'node:assert/strict';
import {FEEDBACK_HOLDOUTS,FEEDBACK_LESSON,feedbackRequest,scoreFeedback} from '../src/micro_feedback_holdouts.js';
import {runFeedbackPair} from '../src/micro_feedback_runner.js';
import {MICRO_CASES,MICRO_MODELS} from '../src/micro_worker_fixtures.js';
const syntheticReply=(action,route)=>({status:200,async json(){return {choices:[{message:{content:JSON.stringify({action,route})}}]}}});
test('changed-fact, source-owned holdouts remain separate from previously scored fixtures',()=>{
 assert.equal(FEEDBACK_HOLDOUTS.length,12);
 assert.equal(new Set(FEEDBACK_HOLDOUTS.map(x=>x.id)).size,12);
 assert.equal(new Set(FEEDBACK_HOLDOUTS.map(x=>x.scenario)).size,12);
 assert.equal(FEEDBACK_HOLDOUTS.filter(x=>x.protected).length,5);
 assert(!FEEDBACK_HOLDOUTS.some(x=>MICRO_CASES.some(y=>x.scenario===y.scenario)));
 assert(!FEEDBACK_LESSON.includes('F01')&&!FEEDBACK_LESSON.includes('F05'));
});
test('each arm shares identical scenario, model, bounds; lesson only in verified context',()=>{
 for(const i of [0,4,8,11]){
  const base=feedbackRequest(0,i,0), lesson=feedbackRequest(0,i,1);
  assert.equal(base.model,MICRO_MODELS[0]);assert.equal(base.max_tokens,200);
  assert.equal(base.temperature,0);assert.equal(base.stream,false);
  assert.equal(base.messages[1].content,lesson.messages[1].content);
  assert(!base.messages[0].content.includes(FEEDBACK_LESSON));
  assert(lesson.messages[0].content.includes(FEEDBACK_LESSON));
 }
});
test('closed model, case and arm selectors',()=>{
 for(const bad of [-1,12,100,'0',null])assert.throws(()=>feedbackRequest(0,bad,0));
 for(const bad of [-1,2,100,'1',null])assert.throws(()=>feedbackRequest(0,0,bad));
 for(const bad of [-1,2,7,'0',null])assert.throws(()=>feedbackRequest(bad,0,0));
});
test('independent scorer rejects unexpected keys and wrong action',()=>{
 assert.equal(scoreFeedback({content:'{"action":"route","route":"haos"}'},4).passed,true);
 assert.equal(scoreFeedback({content:'{"action":"call","route":"read_status"}'},4).passed,false);
 assert.equal(scoreFeedback({content:'{"action":"route","route":"haos","execute":true}'},4).passed,false);
});
test('runner scores paired completions with no emitted model content',async()=>{
 let calls=0;
 const out=await runFeedbackPair({modelIndex:0,caseIndex:4,providerFetch:async(u,opts)=>{
   assert.equal(u,'https://integrate.api.nvidia.com/v1/chat/completions');
   assert.equal(opts.redirect,'manual');
   const parsed=JSON.parse(opts.body);
   assert.equal(parsed.model,MICRO_MODELS[0]);
   calls++;
   return calls===1?syntheticReply('call','read_status'):syntheticReply('route','haos');
 }});
 assert.equal(out.status,'pair_complete');assert.equal(out.provider_calls,2);
 assert.equal(out.lesson_delta,1);assert.equal(out.protected_regression,false);
 assert.equal(out.baseline.passed,false);assert.equal(out.lesson.passed,true);
 assert(!JSON.stringify(out).includes('scenario'));assert(!JSON.stringify(out).includes('Verified category-level'));
 assert.equal(out.commands_executed,false);
});
test('protected lesson regression is explicitly classified',async()=>{
 let count=0;
 const out=await runFeedbackPair({modelIndex:0,caseIndex:4,providerFetch:async()=>{
   count++;return count===1?syntheticReply('route','haos'):syntheticReply('call','read_status');
 }});
 assert.equal(out.lesson_delta,-1);assert.equal(out.protected_regression,true);
});
test('inference 429 stops early without fabricating a result or retry',async()=>{
 let count=0;
 const out=await runFeedbackPair({modelIndex:0,caseIndex:2,providerFetch:async()=>{
   count++;return {status:429};
 }});
 assert.equal(count,1);assert.equal(out.provider_calls,1);assert.equal(out.lesson,null);assert.equal(out.status,'rate_limited');
});
test('transport failure retains reason enum, does not leak secrets or attempt second arm',async()=>{
 let count=0;
 const out=await runFeedbackPair({modelIndex:0,caseIndex:8,providerFetch:async()=>{
   count++;throw new Error('Bearer DO_NOT_LEAK');
 }});
 assert.equal(count,1);assert.equal(out.status,'provider_unavailable_or_partial');
 assert.equal(out.baseline.error,'transport_error');
 assert(!JSON.stringify(out).includes('DO_NOT_LEAK'));
});
import {sanitizeFeedbackReceipt} from '../local-probe/src/feedback_receipt.js';
test('receipt sanitizer preserves only fixed public labels and rejects untrusted private flags',async()=>{
 const result=await runFeedbackPair({modelIndex:0,caseIndex:4,providerFetch:async()=>syntheticReply('route','haos')});
 const sanitized=sanitizeFeedbackReceipt({...result,custom_secret:'DO_NOT_LEAK',baseline:{...result.baseline,raw_content:'DO_NOT_LEAK'}});
 assert(sanitized);assert(!JSON.stringify(sanitized).includes('DO_NOT_LEAK'));
 assert.equal(sanitized.provider_calls,2);
 assert.equal(sanitizeFeedbackReceipt({...result,production_admitted:true}),null);
 assert.equal(sanitizeFeedbackReceipt({...result,model:'attack/arbitrary'}),null);
});
test('sanitizer rejects false pair complete and wrong case identity',()=>{
 const receipt={schema:'commandcenter.nvidia_micro_feedback_holdouts.v1',
   model:MICRO_MODELS[0],model_index:0,case_index:4,case_id:'F05',category:'placement',protected:true,
   provider_calls:0,elapsed_ms:0,status:'pair_complete',baseline:null,lesson:null,
   raw_response_exposed:false,private_input_used:false,commands_executed:false,
   protected_action_authorized:false,production_admitted:false};
 assert.equal(sanitizeFeedbackReceipt(receipt),null);
 assert.equal(sanitizeFeedbackReceipt({...receipt,case_id:'F01'}),null);
});
import {createFeedbackCaller} from '../local-probe/src/feedback_caller.js';
const LOCAL='http://127.0.0.1:8787/feedback-pair';
function localRequest(json){const body=JSON.stringify(json);return new Request(LOCAL,{method:'POST',headers:{'Content-Type':'application/json','Content-Length':String(Buffer.byteLength(body))},body});}
test('local caller rejects arbitrary fields and nonlocal URLs before binding',async()=>{
 const caller=createFeedbackCaller();let count=0;
 const env={NVIDIA_SERVICE:{fetch:async()=>{count++;return {};}}};
 assert.equal((await caller.fetch(localRequest({model_index:0,case_index:0,prompt:'secrets'}),env)).status,400);
 assert.equal((await caller.fetch(new Request('https://example.com/feedback-pair',{method:'POST'}),env)).status,404);
 assert.equal((await caller.fetch(localRequest({model_index:0,case_index:12}),env)).status,400);
 assert.equal(count,0);
});
test('one-use caller returns only sanitized fixed receipt, cannot replay',async()=>{
 const caller=createFeedbackCaller();let count=0;
 const value=await runFeedbackPair({modelIndex:0,caseIndex:4,providerFetch:async()=>syntheticReply('route','haos')});
 const env={NVIDIA_SERVICE:{fetch:async(req)=>{
   count++;assert.equal(new URL(req.url).pathname,'/internal/diagnostics/nvidia-micro-feedback');
   return new Response(JSON.stringify({...value,secret:'never-export'}),{status:200});
 }}};
 const first=await caller.fetch(localRequest({model_index:0,case_index:4}),env);
 assert.equal(first.status,200);const data=await first.json();
 assert.equal(data.case_id,'F05');assert(!JSON.stringify(data).includes('never-export'));
 assert.equal((await caller.fetch(localRequest({model_index:0,case_index:4}),env)).status,409);
 assert.equal(count,1);
});
import {summarizeFeedbackCampaign} from '../local-probe/src/feedback_summary.js';
test('campaign summary cannot promote the model from partial scored work',async()=>{
 const r=await runFeedbackPair({modelIndex:0,caseIndex:4,providerFetch:async()=>syntheticReply('route','haos')});
 const x=summarizeFeedbackCampaign([r]);
 assert.equal(x.status,'incomplete_no_inference_claim');
 assert.equal(x.advisory_review_candidate,false);
 assert.equal(x.automatic_model_promotion,false);
 assert.equal(x.protected_routing_allowed,false);
});
test('campaign summary rejects duplicate case identity or model mixing',async()=>{
 const r=await runFeedbackPair({modelIndex:0,caseIndex:4,providerFetch:async()=>syntheticReply('route','haos')});
 assert.throws(()=>summarizeFeedbackCampaign([r,r]));
 const other=await runFeedbackPair({modelIndex:1,caseIndex:2,providerFetch:async()=>syntheticReply('investigate','receipts')});
 assert.throws(()=>summarizeFeedbackCampaign([r,other]));
});
test('even perfect fictional feedback campaign is review-only, never executor admission',async()=>{
 const receipts=[];
 for(let i=0;i<FEEDBACK_HOLDOUTS.length;i++){
   const fixture=FEEDBACK_HOLDOUTS[i];
   receipts.push(await runFeedbackPair({modelIndex:0,caseIndex:i,
     providerFetch:async()=>syntheticReply(fixture.action,fixture.route)}));
 }
 const x=summarizeFeedbackCampaign(receipts);
 assert.equal(x.status,'fully_scored');assert.equal(x.paired_cases_completed,12);
 assert.equal(x.baseline_passes,12);assert.equal(x.lesson_passes,12);
 assert.equal(x.protected_cases_scored,5);assert.equal(x.protected_misses,0);
 assert.equal(x.advisory_review_candidate,true);
 assert.equal(x.automatic_model_promotion,false);assert.equal(x.protected_routing_allowed,false);
});