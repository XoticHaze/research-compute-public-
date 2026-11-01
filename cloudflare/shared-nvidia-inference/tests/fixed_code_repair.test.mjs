import test from "node:test";
import assert from "node:assert/strict";
import {fixedRepairRequest,sanitizeCodeCandidate} from "../src/fixed_code_repair_fixture.js";
import {runFixedCodeRepair} from "../src/fixed_code_repair_runner.js";
import {sanitizeCodeReceipt} from "../local-probe/src/code_receipt.js";
const FIXED=`def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    if attempt <= 0 or max_attempts <= 0 or attempt >= max_attempts:
        return None
    if base_ms <= 0 or cap_ms <= 0:
        return None
    return min(cap_ms, base_ms * (2 ** (attempt - 1)))
`;

test("fixed code work prompt has exact one model/one synthetic bug, not an arbitrary proxy",()=>{
 for(let i=0;i<2;i++){
  const r=fixedRepairRequest(i);
  assert.equal(r.messages.length,2);
  assert(r.messages[1].content.includes("def retry_delay_ms"));
  assert(r.messages[1].content.includes("attempt >= max_attempts"));
  assert.equal(r.model,i===0?"poolside/laguna-xs-2.1":"minimaxai/minimax-m3.1-flash");
  assert.deepEqual(Object.keys(r).sort(),["max_tokens","messages","model","stream","temperature"]);
 }
 for(const x of [-1,2,"0",0.5])assert.throws(()=>fixedRepairRequest(x),/invalid_fixed_code/);
});

test("actual model generated synthetic function is preserved only after strict source sanitization",async()=>{
 let requests=0;
 const out=await runFixedCodeRepair({modelIndex:0,providerFetch:async(u,o)=>{
  requests++;
  assert.equal(u,"https://integrate.api.nvidia.com/v1/chat/completions");
  assert.equal(o.redirect,"manual");
  return {status:200,async json(){return {choices:[{message:{
    content:JSON.stringify({source:FIXED})
  }}]}}};
 }});
 assert.equal(requests,1);
 assert.equal(out.status,"candidate_unexecuted");
 assert.equal(out.source,FIXED);
 assert.equal(out.source_executed,false);
 assert.equal(out.real_repo_modified,false);
 const local=sanitizeCodeReceipt(out);
 assert.equal(local.code,FIXED);
 assert.equal(local.source_executed,false);
 assert.equal(local.private_data_exported,false);
});

test("first provider 429 stops immediately with zero code exported",async()=>{
 let calls=0;
 const out=await runFixedCodeRepair({modelIndex:1,providerFetch:async()=>{
  calls++;return{status:429};
 }});
 assert.equal(calls,1);
 assert.equal(out.status,"rate_limited");
 assert.equal(out.source,null);
 assert.equal(sanitizeCodeReceipt(out).code,null);
});

test("injected arbitrary code, imports, markdown, string literals and extra fields fail closed",()=>{
 const injections=[
  'def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):\n    import os\n    return 1\n',
  'def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):\n    return __import__(os)\n',
  'def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):\n    return open(secret)\n',
  'def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):\n    return "SECRET"\n',
  'def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):\n    # malicious\n    return 1\n',
 ];
 assert.equal(sanitizeCodeCandidate(JSON.stringify({source:FIXED})),FIXED);
 for(const candidate of injections)assert.equal(sanitizeCodeCandidate(JSON.stringify({source:candidate})),null);
 assert.equal(sanitizeCodeCandidate(JSON.stringify({source:FIXED,other:"secrets"})),null);
 assert.equal(sanitizeCodeCandidate(`\`\`python\n${FIXED}\`\``),null);
});

test("sanitize only exact original synthetic source identity",()=>{
 const v={schema:"commandcenter.nvidia_fixed_code_repair.v1",
 task_id:"RETRY_DEADLINE_01",model:"poolside/laguna-xs-2.1",model_index:0,
 status:"candidate_unexecuted",provider_calls:1,http_status:200,
 elapsed_ms:1000,source:FIXED,source_valid_shape:true};
 assert(sanitizeCodeReceipt(v));
 assert.equal(sanitizeCodeReceipt({...v,model:"wrong"}),null);
 assert.equal(sanitizeCodeReceipt({...v,source:FIXED+"\nimport os"}),null);
 assert.equal(sanitizeCodeReceipt({...v,source_executed:true}).source_executed,false);
});
