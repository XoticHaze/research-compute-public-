// Resumable research-only campaign over the existing Cloudflare local Service
// Binding. No direct NVIDIA API access, credentials, arbitrary prompts, files,
// shell commands, broker or production actions. Never saves model responses.
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {CASES} from "../src/workforce_domain_suite.js";
import {sanitizeWorkforceReceipt} from "../local-probe/src/workforce_receipt.js";
import {evaluateWorkforceReadiness} from "../src/workforce_role_selector.js";
const URL="http://127.0.0.1:8787/workforce-case";
const SCHEMA="commandcenter.workforce_campaign_progress.v1";
const STOP=new Set(["provider_rate_limited","catalog_unavailable",
 "provider_upstream_error",
 "transport_or_decoding_failure"]);
const DONE=new Set(["scored_pass","scored_fail","human_review_required",
 "tool_attempt_rejected","model_http_unavailable","request_profile_rejected"]);
const safeInteger=(v)=>Number.isSafeInteger(v)&&v>=0;
const idKey=(r)=>r.model_index+":"+r.case_index;
export function newCampaign({sourceSha,runId,modelIndex=0,caseIndex=0}){
 if(typeof sourceSha!=="string"||!/^[a-f0-9]{40}$/.test(sourceSha)||
  typeof runId!=="string"||!/^[A-Za-z0-9_.-]{3,100}$/.test(runId)||
  !safeInteger(modelIndex)||modelIndex>=10000||
  !safeInteger(caseIndex)||caseIndex>=CASES.length)
  throw Error("invalid_source_or_campaign_identity");
 return{schema:SCHEMA,source_sha:sourceSha,run_id:runId,
  next_model_index:modelIndex,next_case_index:caseIndex,
  model_id_by_index:{},observations:[],attempt_history:[],calls:0,provider_http_calls:0,
  status:"prepared_not_executed",raw_responses_stored:false,
  provider_key_stored:false,private_input_stored:false,
  production_admitted:false};
}
function checkState(doc){
 if(!doc||doc.schema!==SCHEMA||!/^[a-f0-9]{40}$/.test(doc.source_sha)||
    !Array.isArray(doc.observations)||!Array.isArray(doc.attempt_history)||
    !safeInteger(doc.calls)||!safeInteger(doc.provider_http_calls)||
    !safeInteger(doc.next_model_index)||!safeInteger(doc.next_case_index)||
    doc.raw_responses_stored!==false||doc.provider_key_stored!==false||
    doc.private_input_stored!==false||doc.production_admitted!==false||
    !doc.model_id_by_index||typeof doc.model_id_by_index!=="object")throw Error("invalid_campaign_checkpoint");
 const seen=new Set();
 for(const row of doc.attempt_history){
  const safe=sanitizeWorkforceReceipt(row);
  if(!safe||JSON.stringify(safe)!==JSON.stringify(row)||
     !STOP.has(row.status)&&row.catalog_status!==401&&row.completion_status!==401)
   throw Error("unsafe_held_attempt");
 }
 for(const row of doc.observations){
  const safe=sanitizeWorkforceReceipt(row);
  if(!safe||JSON.stringify(safe)!==JSON.stringify(row))throw Error("unsafe_campaign_observation");
  const key=idKey(row);
  if(seen.has(key))throw Error("duplicate_campaign_observation");
  seen.add(key);
  if(row.model!==null&&doc.model_id_by_index[row.model_index]!==row.model)
   throw Error("catalog_index_mapping_changed");
 }
 return seen;
}
export async function runCampaign({state,callCase,limit=64,onCheckpoint=async()=>{}}){
 if(typeof callCase!=="function"||typeof onCheckpoint!=="function"||
   !safeInteger(limit)||limit<1||limit>64)throw Error("invalid_bounded_campaign");
 const seen=checkState(state);
 if(state.status==="catalog_complete")return state;
 const observations=state.observations.slice();
 const attempt_history=state.attempt_history.slice();
 const mapping={...state.model_id_by_index};
 let m=state.next_model_index,c=state.next_case_index,calls=state.calls,
    providerCalls=state.provider_http_calls,made=0;
 let outcome="session_call_limit_reached";
 while(made<limit&&m<10000){
  const supplied=await callCase({model_index:m,case_index:c});
  const safe=sanitizeWorkforceReceipt(supplied);
  if(!safe||safe.model_index!==m||safe.case_index!==c)
   throw Error("untrusted_workforce_case_result");
  if(safe.model!==null&&mapping[m]!==undefined&&mapping[m]!==safe.model)
   throw Error("catalog_index_mapping_changed");
  if(safe.model!==null)mapping[m]=safe.model;
  const pair=idKey(safe);
  if(seen.has(pair))throw Error("resume_attempt_replay");
  const hold=STOP.has(safe.status)||safe.catalog_status===401||safe.completion_status===401;
  if(hold)attempt_history.push(safe);
  else {seen.add(pair);observations.push(safe);}
  made++;calls++;providerCalls+=safe.provider_calls;
  if(safe.status==="model_index_not_in_authenticated_catalog"){
   outcome="catalog_complete";
  }else if(STOP.has(safe.status)||safe.catalog_status===401||safe.completion_status===401){
   outcome="provider_hold";
  }else if(!DONE.has(safe.status)){
   outcome="unclassified_provider_case";
  }
  if(outcome==="session_call_limit_reached"){
   if(["model_http_unavailable","request_profile_rejected"].includes(safe.status)&&
       [400,403,404,410].includes(safe.completion_status)){
    c=0;m++; // Unsupported/inaccessible model: avoid 31 pointless repetitions.
   }else{
    c++;
    if(c>=CASES.length){c=0;m++;}
   }
  }
  // Save after every trusted outcome, never only at the end.
  const next={...state,next_model_index:m,next_case_index:c,
   model_id_by_index:{...mapping},observations:observations.slice(),
   attempt_history:attempt_history.slice(),calls,provider_http_calls:providerCalls,status:outcome,raw_responses_stored:false,provider_key_stored:false,
   private_input_stored:false,production_admitted:false};
  await onCheckpoint(next);
  if(outcome!=="session_call_limit_reached")return next;
 }
 return{...state,next_model_index:m,next_case_index:c,model_id_by_index:mapping,
  observations,attempt_history,calls,provider_http_calls:providerCalls,status:outcome,raw_responses_stored:false,
  provider_key_stored:false,private_input_stored:false,
  production_admitted:false};
}
export function resultsFromCampaign(state){
 checkState(state);
 // Some models may produce only partial role observations. Preserve that
 // incompleteness and keep all candidate routes unpromoted.
 const accepted=state.observations.filter(v=>v.model!==null);
 return evaluateWorkforceReadiness({receipts:accepted});
}
export function validatePublicHost(){
 const repo=process.env.GITHUB_REPOSITORY;
 const sha=process.env.WORKFORCE_SOURCE_SHA;
 const run=process.env.GITHUB_RUN_ID;
 const approvedWorkflow="XoticHaze/waterboys-fantasy-compute/.github/workflows/nvidia-workforce-shadow-qualification.yml@refs/heads/main";
 if(repo!=="XoticHaze/waterboys-fantasy-compute"||
   process.env.GITHUB_WORKFLOW_REF!==approvedWorkflow||
   process.env.GITHUB_EVENT_NAME!=="push"||
   typeof sha!=="string"||!/^[a-f0-9]{40}$/.test(sha)||
   typeof run!=="string"||!/^[0-9]{6,20}$/.test(run))
   throw Error("untrusted_execution_host");
 return{sourceSha:sha,runId:"github-"+run};
}
async function main(){
 const info=validatePublicHost();
 const root=path.join(process.cwd(),"artifacts","nvidia-workforce-qualification");
 fs.mkdirSync(root,{recursive:true});
 const file=path.join(root,"campaign_progress.json");
 let state=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,"utf8")):newCampaign({
  ...info,modelIndex:Number(process.env.WORKFORCE_MODEL_INDEX_START??"0"),
  caseIndex:Number(process.env.WORKFORCE_CASE_INDEX_START??"0")
 });
 if(state.source_sha!==info.sourceSha)throw Error("source_revision_changed_do_not_mix");
 const limit=Number(process.env.WORKFORCE_CASES_THIS_PASS??"64");
 // Runtime budget affects only this session; no lifetime catalog or task cap.
 const callCase=async selector=>{
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),270000);
  try{
   const res=await fetch(URL,{method:"POST",redirect:"manual",
    headers:{"content-type":"application/json"},
    body:JSON.stringify(selector),signal:controller.signal});
   const bytes=await res.text();
   if(bytes.length>14000)throw Error("untrusted_oversized_workforce_receipt");
   let json;try{json=JSON.parse(bytes);}catch{throw Error("invalid_workforce_receipt");}
   return json;
  }finally{clearTimeout(timeout);}
 };
 const write=async value=>{
  const temp=file+".tmp";
  fs.writeFileSync(temp,JSON.stringify(value,null,2)+"\n",{mode:0o600});
  fs.renameSync(temp,file);
 };
 const result=await runCampaign({state,callCase,limit,onCheckpoint:write});
 await write(result);
 fs.writeFileSync(path.join(root,"role_readiness.json"),
  JSON.stringify(resultsFromCampaign(result),null,2)+"\n",{mode:0o600});
 // No source, answer, untrusted note or credential ever printed.
 console.log("WORKFORCE_CAMPAIGN_STATUS="+result.status);
 console.log("WORKFORCE_SESSION_OBSERVATIONS="+(result.observations.length-state.observations.length));
 console.log("WORKFORCE_TOTAL_OBSERVATIONS="+result.observations.length);
 console.log("WORKFORCE_PROVIDER_HTTP_CALLS="+result.provider_http_calls);
 console.log("WORKFORCE_HELD_ATTEMPTS="+result.attempt_history.length);
 console.log("WORKFORCE_MODEL_INDEX_NEXT="+result.next_model_index);
 console.log("WORKFORCE_CASE_INDEX_NEXT="+result.next_case_index);
 console.log("WORKFORCE_PRIVATE_DATA_EXPORTED=false");
 console.log("WORKFORCE_PRODUCTION_ADMITTED=false");
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1])){
 main().catch(()=>{console.error("WORKFORCE_CAMPAIGN_HELD_SAFE_ERROR");process.exitCode=1;});
}
