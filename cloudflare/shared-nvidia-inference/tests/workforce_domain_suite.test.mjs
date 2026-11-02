import test from "node:test";
import {V4_HOLDOUT_CASES,V4_HOLDOUT_AUDIT} from "../src/workforce_v4_holdout_suite.js";
import assert from "node:assert/strict";
import {CASES,WORKFORCE_DOMAINS,WORKFORCE_SKILLS,corpusAudit,messagesForCase,supportingDossier,gradeCase} from "../src/workforce_domain_suite.js";

test("cross-project benchmark is a paired, broad 32-case research/workforce battery",()=>{
 const a=corpusAudit();
 assert.equal(a.cases,92);
 assert.equal(a.domains,19);
 assert(a.roles>=13);
 assert.equal(a.paired_domains,true);
 assert.equal(a.human_review_count,2);
 assert.equal(a.real_provider_calls,0);
 assert.equal(a.independent_skill_qualification,false);
 assert.equal(new Set(CASES.map(c=>c.id)).size,92);
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
 for(const d of WORKFORCE_DOMAINS.filter(d=>!d.endsWith("_v4"))){
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
 for(const bad of [-1,92,1.2,"0",NaN,null]){
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

test("reasoning and document workloads include long conflicting provenance archives",()=>{
 const hard=CASES.filter(x=>["research_doc_audit","long_context_reconciliation"].includes(x.domain));
 assert.equal(hard.length,4);
 for(const c of hard){
  const dossier=supportingDossier(c.index);
  assert(dossier.length>10000,c.id);
  assert(dossier.includes("[UNTRUSTED-SUMMARY]"));
  assert(dossier.includes("does not grant status to the target"));
  assert(!dossier.includes("XoticHaze"));
  assert(messagesForCase(c.index)[1].content.length>10000);
  assert.equal(gradeCase(c.index,JSON.stringify(c.expected)).passed,true);
 }
 for(const c of CASES.filter(x=>x.domain==="portfolio_exposure"))
  assert.equal(supportingDossier(c.index),"");
});

test("model receives explicit role vocabulary and types instead of hidden exact-label tests",()=>{
 for(const c of CASES){
  const prompt=messagesForCase(c.index)[1].content;
  assert(prompt.includes("Output contract:"),c.id);
  for(const [key,value] of Object.entries(c.expected)){
   assert(prompt.includes(key+": "),c.id+" "+key);
   if(typeof value==="boolean")assert(prompt.includes(key+": boolean"),c.id);
   if(Array.isArray(value))assert(prompt.includes(key+": array of unique string IDs"),c.id);
   if(typeof value==="string"&&key!=="message"&&!key.endsWith("_at"))
    assert(prompt.includes(key+": string; allowed values "),c.id);
  }
 }
});
test("field-grade contracts accept numeric tolerance and unordered unique ID sets",()=>{
 const c=CASES[0],rev={...c.expected,rejected:[...c.expected.rejected].reverse()};
 assert.equal(gradeCase(0,JSON.stringify(rev)).passed,true);
 assert.equal(gradeCase(0,JSON.stringify({...rev,rejected:["P2","P2"]})).passed,false);
 const quote=CASES[16],round={...quote.expected,cost_usd:156.20000000000002,
  margin_usd:83.80000000000001};
 assert.equal(gradeCase(16,JSON.stringify(round)).passed,true);
 const bad={...round,margin_usd:88.8};
 assert.equal(gradeCase(16,JSON.stringify(bad)).passed,false);
});

test("news join gold never uses events first observed after cutoff",()=>{
 const delayed=CASES[0];
 const available=CASES[1];
 assert.deepEqual(delayed.expected.eligible,[]);
 assert.deepEqual([...delayed.expected.rejected].sort(),["P1","P2","P3"]);
 assert.deepEqual(available.expected.eligible,["S1"]);
 assert(available.input.includes("fetched 12:01Z"));
 assert(delayed.input.includes("observed_at 14:10Z"));
 for(const c of [delayed,available]){
  const question=messagesForCase(c.index)[1].content;
  assert(question.includes("BOTH a known publication time and observed/fetched time"));
  assert(question.includes("no later than the decision cutoff"));
 }
 const lookahead={eligible:["P1"],rejected:["P2","P3"],assumed_published:false};
 assert.equal(gradeCase(0,JSON.stringify(lookahead)).passed,false);
 assert.equal(gradeCase(0,JSON.stringify(delayed.expected)).passed,true);
 assert.equal(gradeCase(1,JSON.stringify(available.expected)).passed,true);
});
test("missing conflict is an explicitly nullable value, not a hidden enum",()=>{
 const a=messagesForCase(7)[1].content;
 assert(a.includes("conflict_at: nullable string or null"));
 assert(gradeCase(7,JSON.stringify(CASES[7].expected)).passed);
});

test("v4 changed-fact holdouts are separate from frozen v3 and default-denied",()=>{
 assert.equal(CASES.length,92);
 assert.equal(V4_HOLDOUT_CASES.length,60);
 assert.equal(V4_HOLDOUT_AUDIT.size,60);
 assert.equal(V4_HOLDOUT_AUDIT.production_admitted,false);
 assert.equal(V4_HOLDOUT_AUDIT.private_input_used,false);
 for(const [domain,role] of [
  ["worker_receipt_holdout_v4","cc.receipt_intelligence"],
  ["incident_diagnosis_holdout_v4","cc.ops_log_triage"],
  ["long_context_reconciliation_holdout_v4","shared.document_long_context"]]){
  const rows=CASES.filter(c=>c.domain===domain);
  assert.equal(rows.length,20);
  assert.equal(new Set(rows.map(c=>c.input)).size,20);
  assert(rows.every(c=>c.role===role&&c.case_version==="v4_changed_fact_20261102"&&c.synthetic));
  for(let i=0;i<20;i+=2){
    assert.notDeepEqual(rows[i].expected,rows[i+1].expected);
    assert.equal(gradeCase(rows[i].index,JSON.stringify(rows[i+1].expected)).passed,false);
    assert.equal(gradeCase(rows[i+1].index,JSON.stringify(rows[i].expected)).passed,false);
  }
 }
 assert(CASES.slice(0,32).every(c=>c.case_version==="1"));
 assert(CASES.slice(32).every(c=>c.case_version==="v4_changed_fact_20261102"));
});
