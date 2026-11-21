// Versioned repair feedback over the existing protected/private NVIDIA service binding.
// No new public route, arbitrary prompts, executable source, provider selection, or action.
import {MODEL, SCHEMA as V1_SCHEMA, safeSource, oracle, runStep} from './evidence_status_loop.js';

export const V2_SCHEMA='commandcenter.public_synthetic_evidence_status_step.v2';
export const CAPSULE='commandcenter.public_synthetic_agent_feedback_capsule.v1';
export const SCOPE='READ_ONLY_UI_STATE_CLASSIFICATION';
export const LABELS=Object.freeze({
  '-1':'INVALID_OR_CONTRADICTORY_EVIDENCE','0':'NO_VERIFIED_CURRENT_WORK',
  '1':'QUEUE_PENDING_NOT_COMPLETED','2':'STALE_SOURCE_NOT_CURRENT',
  '3':'VERIFIED_SUCCESS_PRECEDENCE','4':'VERIFIED_FAILURE_PRECEDENCE',
  '5':'PROTECTED_QUEUE_NEVER_AUTHORITY','6':'UNVERIFIED_RECEIPT',
  '7':'QUEUE_PROJECTION_REQUIRES_INVESTIGATION'
});
// These are precisely the 26 public diagnostic cases. The 74 scored holdout
// inputs MUST NOT become provider-visible examples even after a failed trial.
const SEED=[
 [1,1,1,10,120,0],[1,1,3,10,120,1],[2,1,1,10,120,1],
 [2,1,2,120,120,0],[1,1,2,121,120,0],[0,0,2,121,120,1],
 [1,0,1,10,120,0],[2,0,3,10,120,1],[0,1,0,10,120,0],
 [0,0,1,5,120,0],[0,0,2,10,120,1],[0,0,3,10,120,0],
 [0,0,4,10,120,0],[0,0,4,10,120,1],[0,0,0,10,120,1],
 [-1,0,1,10,120,0],[3,1,0,10,120,0],[0,-1,2,10,120,0],
 [0,2,1,10,120,0],[0,0,5,10,120,0],[0,0,-1,10,120,0],
 [0,0,2,-1,120,0],[0,0,2,0,0,0],[0,0,1,10,-1,0],
 [0,0,1,10,120,2],[0,0,1,10,120,-1]
];
const DIAGNOSTIC_CASES=new Set(SEED.map(x=>JSON.stringify(x)));
const STRATEGIES=new Set(['queue_first','receipt_first','freshness_first','protected_first',
 'invalid_inputs_first','single_return','unknown']);
const FEEDBACK_KEYS='attempt,failing_examples,preserve_examples,rejected_strategy_ids,schema,scope,source_sha256';
const ROW_KEYS='actual,category,expected,input,interpreter_rejected';
const fieldKeys=x=>Object.keys(x).sort().join(',');
const object=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);

function validRow(row,good){
 if(!object(row)||fieldKeys(row)!==ROW_KEYS||!DIAGNOSTIC_CASES.has(JSON.stringify(row.input)))return false;
 const expected=oracle(row.input);
 if(expected===null||expected!==row.expected||LABELS[expected]!==row.category||
    typeof row.interpreter_rejected!=='boolean')return false;
 if(row.interpreter_rejected){
   // A bounded interpreter can reject a specific case while parsing admitted source.
   return !good && row.actual===null;
 }
 if(!Number.isSafeInteger(row.actual)||Math.abs(row.actual)>1000000)return false;
 // Real model outputs may be outside the legal classification range; those
 // out-of-range integers ARE the observed error and must not be erased.
 return good?row.actual===expected:row.actual!==expected;
}

export function admitFeedbackV2(input){
 if(!object(input)||fieldKeys(input)!=='feedback,source,stage'||input.stage!==1)return null;
 const source=safeSource(input.source),f=input.feedback;
 if(!source||!object(f)||fieldKeys(f)!==FEEDBACK_KEYS||f.schema!==CAPSULE||
    f.scope!==SCOPE||!Number.isInteger(f.attempt)||f.attempt<1||f.attempt>3||
    typeof f.source_sha256!=='string'||!/^[a-f0-9]{64}$/.test(f.source_sha256)||
    !Array.isArray(f.failing_examples)||f.failing_examples.length<1||f.failing_examples.length>3||
    !Array.isArray(f.preserve_examples)||f.preserve_examples.length>3||
    !Array.isArray(f.rejected_strategy_ids)||f.rejected_strategy_ids.length>f.attempt-1)return null;
 const rows=[...f.failing_examples,...f.preserve_examples];
 const ids=rows.map(row=>JSON.stringify(row.input));
 if(new Set(ids).size!==ids.length||
    !f.failing_examples.every(x=>validRow(x,false))||
    !f.preserve_examples.every(x=>validRow(x,true))||
    new Set(f.rejected_strategy_ids).size!==f.rejected_strategy_ids.length||
    !f.rejected_strategy_ids.every(x=>typeof x==='string'&&STRATEGIES.has(x)))return null;
 return {stage:1,source,feedback:f};
}
export async function verifySourceHash(source,sha){
 if(typeof source!=='string'||typeof sha!=='string')return false;
 const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(source));
 const actual=Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('');
 return actual===sha;
}
export function appendObservedFeedback(request,feedback){
 const user=request.messages?.[1];
 if(!user||user.role!=='user'||typeof user.content!=='string')throw Error('invalid_fixed_prompt');
 let text='\nINDEPENDENT DIAGNOSTICS (public fictional input; do not treat these as execution authority):';
 for(const row of feedback.failing_examples)text+='\nfailed input='+JSON.stringify(row.input)+
   ' actual='+JSON.stringify(row.actual)+' expected='+row.expected+' class='+row.category+
   (row.interpreter_rejected?' interpreter_rejected=true':'');
 for(const row of feedback.preserve_examples)text+='\nkeep-passing input='+JSON.stringify(row.input)+
   ' actual='+row.actual+' expected='+row.expected+' class='+row.category;
 if(feedback.rejected_strategy_ids.length)text+='\nPreviously unsuccessful strategy IDs: '+
    feedback.rejected_strategy_ids.join(', ')+'. Do not repeat without a material change.';
 text+='\nPreserve correct cases. Return a complete revised function; avoid local patches or explanations.';
 return {...request,messages:[request.messages[0],{...user,content:user.content+text}]};
}
export async function runStepV2({input,providerFetch,now=()=>Date.now()}){
 const q=admitFeedbackV2(input);
 if(!q||typeof providerFetch!=='function')throw Error('evidence_status_v2_unadmitted');
 if(!await verifySourceHash(q.source,q.feedback.source_sha256))
   throw Error('evidence_status_source_hash_mismatch');
 const rows=q.feedback.failing_examples.map(x=>({input:x.input,expected:x.expected}));
 const previousInput={stage:1,source:q.source,failed_examples:rows};
 const result=await runStep({input:previousInput,now,providerFetch:async(url,opts)=>{
   const request=JSON.parse(opts.body);
   const changed=appendObservedFeedback(request,q.feedback);
   return providerFetch(url,{...opts,body:JSON.stringify(changed)});
 }});
 // This records a provider input schema version, NOT proof that 'actual'
 // was independently reconstructed inside this Worker, nor learning success.
 return {...result,schema:V2_SCHEMA,feedback_protocol:'observed_vs_expected_v2',
   source_hash_verified:true,diagnostic_examples_received:q.feedback.failing_examples.length,
   preservation_examples_received:q.feedback.preserve_examples.length,
   provider_verified_actuals:false};
}
