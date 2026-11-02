import test from "node:test";
import assert from "node:assert/strict";
import {sanitizeCodeRoleReceipt} from "../local-probe/src/code_role_receipt.js";

function makeReceipt(overrides={}){
 return {
  schema:"commandcenter.nvidia_role_code_case.v1",
  model:"minimaxai/minimax-m3.1-flash",model_index:1,
  task_id:"RESERVED_BUDGET_03",task_index:2,
  status:"format_rejected",provider_calls:1,http_status:200,elapsed_ms:2100,
  source:null,source_valid_shape:false,
  final_content_present:false,reasoning_content_present:true,
  finish_reason:"length",
  ...overrides
 };
}

test("length exhaustion remains diagnosable without revealing reasoning or text",()=>{
 const v=makeReceipt({reasoning_content:"REDACTED_SECRET_DO_NOT_COPY",content:"REDACTED_PRIVATE_CONTENT"});
 const clean=sanitizeCodeRoleReceipt(v);
 assert.ok(clean);
 assert.equal(clean.status,"format_rejected");
 assert.equal(clean.finish_reason,"length");
 assert.equal(clean.reasoning_content_present,true);
 assert.equal(clean.final_content_present,false);
 assert.equal(clean.code,null);
 const safe=JSON.stringify(clean);
 assert.equal(safe.includes("REDACTED_SECRET"),false);
 assert.equal(safe.includes("REDACTED_PRIVATE"),false);
 assert.equal("reasoning_content" in clean,false);
 assert.equal("content" in clean,false);
});
test("known finish classes and booleans survive, arbitrary strings reject",()=>{
 const stop=sanitizeCodeRoleReceipt(makeReceipt({finish_reason:"stop",final_content_present:true,reasoning_content_present:false}));
 assert.equal(stop.finish_reason,"stop");
 assert.equal(stop.final_content_present,true);
 assert.equal(stop.reasoning_content_present,false);
 for(const bad of ["injected secret","../../leak",{},12]){
   assert.equal(sanitizeCodeRoleReceipt(makeReceipt({finish_reason:bad})),null);
 }
 for(const bad of ["true",{},11]){
   assert.equal(sanitizeCodeRoleReceipt(makeReceipt({final_content_present:bad})),null);
   assert.equal(sanitizeCodeRoleReceipt(makeReceipt({reasoning_content_present:bad})),null);
 }
});
test("legacy bounded receipts remain backward compatible and do not invent a reason",()=>{
 const old=makeReceipt();
 delete old.final_content_present;
 delete old.reasoning_content_present;
 delete old.finish_reason;
 const clean=sanitizeCodeRoleReceipt(old);
 assert.ok(clean);
 assert.equal(clean.finish_reason,"not_recorded");
 assert.equal(clean.final_content_present,null);
 assert.equal(clean.reasoning_content_present,null);
});
test("provider-rate-limit receipt is classified without exposing provider body",()=>{
 const clean=sanitizeCodeRoleReceipt(makeReceipt({
  status:"provider_rate_limited",http_status:429,
  final_content_present:null,reasoning_content_present:null,
  finish_reason:"not_recorded",source:"DONOTOUTPUT_SECRET"
 }));
 assert.ok(clean);
 assert.equal(clean.code,null);
 assert.equal(clean.status,"provider_rate_limited");
 assert.equal(JSON.stringify(clean).includes("DONOTOUTPUT_SECRET"),false);
});
