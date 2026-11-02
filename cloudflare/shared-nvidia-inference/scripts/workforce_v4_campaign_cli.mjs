// Synthetic v4 fixed-cohort campaign. Source-only pending owner-reviewed Worker
// deployment and WaterBoys exact-source repin. No arbitrary prompts, private inputs,
// user-provided URLs, broker tools, or model response persistence.
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {V4_MECHANISM_HOLDOUTS} from "../src/workforce_v4_mechanism_holdout.js";
import {sanitizeV4MechanismReceipt} from "../local-probe/src/workforce_v4_receipt.js";
const URL="http://127.0.0.1:8787/workforce-v4-case";
const SCHEMA="commandcenter.workforce_v4_mechanism_campaign.v1";
const HELD=new Set(["provider_rate_limited","catalog_unavailable","transport_or_decoding_failure"]);
const integer=x=>Number.isSafeInteger(x)&&x>=0;
export function newV4Campaign({sourceSha,runId,modelIndex,caseIndex}){
 if(typeof sourceSha!=="string"||!/^[a-f0-9]{40}$/.test(sourceSha)||
   typeof runId!=="string"||!/^[A-Za-z0-9_.-]{6,100}$/.test(runId)||
   !integer(modelIndex)||modelIndex>9999||!integer(caseIndex)||caseIndex>=V4_MECHANISM_HOLDOUTS.length)
   throw Error("invalid_v4_campaign_origin");
 return{schema:SCHEMA,source_sha:sourceSha,run_id:runId,cohort:"mechanism_v4",
   model_index:modelIndex,next_case_index:caseIndex,observations:[],held_attempts:[],
   provider_calls:0,provider_http_calls:0,status:"prepared_not_executed",
   private_input_used:false,raw_responses_stored:false,production_admitted:false};
}
export function checkV4Campaign(state){
 if(!state||state.schema!==SCHEMA||state.cohort!=="mechanism_v4"||
   !/^[a-f0-9]{40}$/.test(state.source_sha??"")||
   !/^[A-Za-z0-9_.-]{6,100}$/.test(state.run_id??"")||
   !integer(state.model_index)||state.model_index>9999||
   !integer(state.next_case_index)||state.next_case_index>V4_MECHANISM_HOLDOUTS.length||
   !integer(state.provider_calls)||!integer(state.provider_http_calls)||
   state.private_input_used!==false||state.raw_responses_stored!==false||
   state.production_admitted!==false||
   !Array.isArray(state.observations)||!Array.isArray(state.held_attempts))
   throw Error("invalid_v4_campaign_state");
 const keys=new Set(),attempts=[...state.observations,...state.held_attempts];
 if(attempts.length!==state.provider_calls)throw Error("v4_call_count_mismatch");
 if(attempts.reduce((n,a)=>n+a.provider_calls,0)!==state.provider_http_calls)
   throw Error("v4_provider_call_count_mismatch");
 for(const attempt of attempts){
  if(JSON.stringify(sanitizeV4MechanismReceipt(attempt))!==JSON.stringify(attempt)||
    attempt.model_index!==state.model_index)throw Error("untrusted_v4_checkpoint");
 }
 for(const attempt of state.observations){
  if(keys.has(attempt.case_index))throw Error("duplicate_v4_case");
  keys.add(attempt.case_index);
 }
 if(state.held_attempts.some(x=>!HELD.has(x.status)&&x.catalog_status!==401&&x.completion_status!==401))
   throw Error("invalid_v4_held_attempt");
 return keys;
}
export async function runV4Campaign({state,callCase,limit,onCheckpoint=async()=>{}}){
 if(typeof callCase!=="function"||typeof onCheckpoint!=="function"||
   !integer(limit)||limit<1||limit>8)throw Error("invalid_v4_campaign_budget");
 const seen=checkV4Campaign(state);
 if(state.status==="completed_cohort")return state;
 let next=state;
 for(let n=0;n<limit;n++){
  const i=next.next_case_index;
  if(i>=V4_MECHANISM_HOLDOUTS.length)return{...next,status:"completed_cohort"};
  if(seen.has(i))throw Error("v4_case_replayed");
  const response=await callCase({model_index:next.model_index,case_index:i});
  const safe=sanitizeV4MechanismReceipt(response);
  if(!safe||safe.case_index!==i||safe.model_index!==next.model_index)
   throw Error("untrusted_v4_provider_receipt");
  const held=HELD.has(safe.status)||safe.catalog_status===401||safe.completion_status===401;
  next={...next,
   observations:held?next.observations:[...next.observations,safe],
   held_attempts:held?[...next.held_attempts,safe]:next.held_attempts,
   provider_calls:next.provider_calls+1,
   provider_http_calls:next.provider_http_calls+safe.provider_calls,
   next_case_index:held?i:i+1,
   status:held?"provider_hold":i+1===V4_MECHANISM_HOLDOUTS.length?"completed_cohort":"bounded_session_complete"
  };
  await onCheckpoint(next);
  if(held)return next;
 }
 return next;
}
export function validateV4Host(){
 const repo=process.env.GITHUB_REPOSITORY,workflow=process.env.GITHUB_WORKFLOW_REF,
  sha=process.env.WORKFORCE_V4_SOURCE_SHA,run=process.env.GITHUB_RUN_ID;
 if(repo!=="XoticHaze/waterboys-fantasy-compute"||
   workflow!=="XoticHaze/waterboys-fantasy-compute/.github/workflows/nvidia-workforce-shadow-qualification.yml@refs/heads/main"||
   process.env.GITHUB_EVENT_NAME!=="push"||!/^[a-f0-9]{40}$/.test(sha??"")||
   !/^[0-9]{6,20}$/.test(run??""))throw Error("v4_untrusted_execution_host");
 return{sourceSha:sha,runId:"github-"+run};
}
async function main(){
 const origin=validateV4Host();
 const state=newV4Campaign({...origin,
  modelIndex:Number(process.env.WORKFORCE_MODEL_INDEX_START),
  caseIndex:Number(process.env.WORKFORCE_CASE_INDEX_START)});
 const limit=Number(process.env.WORKFORCE_CASES_THIS_PASS);
 const dir=path.join(process.cwd(),"artifacts","nvidia-v4-mechanism");
 fs.mkdirSync(dir,{recursive:true});
 const file=path.join(dir,"campaign_progress.json");
 const checkpoint=async x=>{
  const temp=file+".tmp";
  fs.writeFileSync(temp,JSON.stringify(x,null,2)+"\n",{mode:0o600});
  fs.renameSync(temp,file);
 };
 const result=await runV4Campaign({state,limit,onCheckpoint:checkpoint,callCase:async selector=>{
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),270000);
  try{
   const res=await fetch(URL,{method:"POST",redirect:"manual",
    headers:{"content-type":"application/json"},body:JSON.stringify(selector),
    signal:controller.signal});
   const raw=await res.text();
   if(raw.length>14000)throw Error("oversized_v4_receipt");
   return JSON.parse(raw);
  }finally{clearTimeout(timeout);}
 }});
 await checkpoint(result);
 console.log("V4_CAMPAIGN_STATUS="+result.status);
 console.log("V4_CASES_FINISHED="+result.observations.length);
 console.log("V4_HELD_ATTEMPTS="+result.held_attempts.length);
 console.log("V4_PROVIDER_HTTP_CALLS="+result.provider_http_calls);
 console.log("V4_PRIVATE_INPUT_EXPORTED=false");
 console.log("V4_PRODUCTION_ADMITTED=false");
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))
 main().catch(()=>{console.error("V4_SYNTHETIC_CAMPAIGN_HELD_SAFE_ERROR");process.exitCode=1;});
