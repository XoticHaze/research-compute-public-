import test from "node:test";
import assert from "node:assert/strict";
import {CASES,WORKFORCE_DOMAINS,WORKFORCE_SKILLS,corpusAudit,messagesForCase,gradeCase} from "../src/workforce_domain_suite.js";

test("cross-project benchmark is a paired, broad 32-case research/workforce battery",()=>{
 const a=corpusAudit();
 assert.equal(a.cases,32);
 assert.equal(a.domains,16);
 assert(a.roles>=13);
 assert.equal(a.paired_domains,true);
 assert.equal(a.human_review_count,2);
 assert.equal(a.real_provider_calls,0);
 assert.equal(a.independent_skill_qualification,false);
 assert.equal(new Set(CASES.map(c=>c.id)).size,32);
 assert(WORKFORCE_DOMAINS.includes("trader_ops_advice"));
 assert(WORKFORCE_DOMAINS.includes("market_news_relevance"));
 assert(WORKFORCE_DOMAINS.includes("income_quote_economics"));
 assert(WORKFORCE_DOMAINS.includes("dashboard_state"));
 assert(WORKFORCE_DOMAINS.includes("long_context_reconciliation"));
});
test("each ground-truth answer is scoreable without exposing model-generated text",()=>{
 for(const c of CASES){
  const parsed=gradeCase(c.index,JSON.stringify(c.expected));
  assert(parsed.format_valid,c.id);
  if(!c.human_review_required) assert.equal(parsed.fields_correct,parsed.fields_total,c.id);
  assert.equal(parsed.passed,!c.human_review_required,c.id);
  assert.equal(parsed.human_review_required,c.human_review_required);
  assert.equal(parsed.answer_exported,false);
  assert.equal(parsed.production_authorized,false);
  assert(!JSON.stringify(parsed).includes("BROKER_ACCOUNT_ID"));
  assert.equal(c.synthetic,true);
  assert(c.question.length>40);
  assert(c.input.length>150);
  assert(c.baseline.length>4);
  assert(!c.input.includes("XoticHaze"));
  const messages=messagesForCase(c.index);
  assert.equal(messages.length,2);
  assert.equal(messages[0].role,"system");
  assert.equal(messages[1].role,"user");
  assert(!messages[1].content.includes("NVIDIA_API_KEY"));
  assert(messages[1].content.includes(c.question));
 }
});
test("each counterfactual pair changes expected facts and recycled answers fail",()=>{
 for(const d of WORKFORCE_DOMAINS){
  const pair=CASES.filter(c=>c.domain===d);
  assert.equal(pair.length,2);
  if(!pair[0].human_review_required)assert.notDeepEqual(pair[0].expected,pair[1].expected,d);
  const first=gradeCase(pair[1].index,JSON.stringify(pair[0].expected));
  const second=gradeCase(pair[0].index,JSON.stringify(pair[1].expected));
  assert.equal(first.passed,false,d);
  assert.equal(second.passed,false,d);
  if(!pair[0].human_review_required){
   assert(first.fields_correct<first.fields_total,d);
   assert(second.fields_correct<second.fields_total,d);
  }
 }
});
test("false approval, fabricated availability and bad calculations fail per-case",()=>{
 const originals=[
  ["news_causal_join",{eligible:["P1","P2"],rejected:["P3"],assumed_published:true}],
  ["trader_ops_advice",{fresh:true,status:"review_candidate",order_allowed:true}],
  ["portfolio_exposure",{gross_pct:85,headroom_usd:0,proposal_breaches:false}],
  ["dashboard_state",{build_parity:true,market_overview:"available",fully_healthy:true}],
  ["worker_receipt_triage",{complete_verified:true,receipt_matches:true,next_action:"consume_only_W10"}],
  ["commerce_reconciliation",{cash_captured:true,fulfillment:"fulfilled_twice",allowed_first_fulfillments:2}],
  ["long_context_reconciliation",{verified_sha:"Z12",release_approved:true,blocker_source:"DOC B"}],
  ["home_voice_intent",{entity:"light.hallway",action:"turn_off",execute_earlier:true}]
 ];
 for(const [domain,bad] of originals){
  const c=CASES.find(x=>x.domain===domain);
  const result=gradeCase(c.index,JSON.stringify(bad));
  assert.equal(result.passed,false,domain);
  assert(result.fields_correct<result.fields_total,domain);
 }
});
test("malformed provider replies are rejected with metadata-only safe receipts",()=>{
 for(const c of CASES){
  for(const raw of ["not json","{}",JSON.stringify({...c.expected,secret:"DO_NOT_EXPOSE"}),"x".repeat(16001)]){
   const r=gradeCase(c.index,raw);
   assert.equal(r.passed,false,c.id);
   assert.equal(r.answer_exported,false);
   assert.equal(r.production_authorized,false);
   assert(!JSON.stringify(r).includes("DO_NOT_EXPOSE"));
  }
 }
 for(const bad of [-1,32,1.2,"0",NaN,null]){
  assert.throws(()=>messagesForCase(bad),/invalid_fixed_workforce_case/);
  assert.throws(()=>gradeCase(bad,"{}"),/invalid_fixed_workforce_case/);
 }
});
test("human prose remains explicitly unqualified pending blinded review",()=>{
 for(const c of CASES.filter(c=>c.human_review_required)){
  assert.equal(gradeCase(c.index,JSON.stringify({message:"This is a sufficiently long sample response with no proof of helpfulness."})).passed,false);
  assert.equal(gradeCase(c.index,JSON.stringify({message:"A"})).fields_correct,0);
 }
});
