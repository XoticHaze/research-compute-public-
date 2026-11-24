// Novel, public-fictional, read-only evidence-state artifact qualification.
// No arbitrary prompt, user/device data, browser route, command or source execution.
const API='https://integrate.api.nvidia.com/v1/chat/completions';
export const MODEL='poolside/laguna-xs-2.1';
export const ARGS=['receipt','verified','queue','age_s','ttl_s','protected'];
export const HEADER='def evidence_state('+ARGS.join(', ')+'):\n';
export const SCHEMA='commandcenter.public_synthetic_evidence_status_step.v1';
const SOURCE=/^[A-Za-z0-9_ ()*,+\-<>=:\/\n]+$/;
const BANNED=/\b(?:import|exec|eval|open|globals|locals|lambda|class|del|while|for|yield|async|await|print|input|secret|key|token|subprocess)\b/i;
export const TASK='Write a pure Python evidence_state(receipt, verified, queue, age_s, ttl_s, protected) function returning an integer classification. All inputs are integers. receipt is 0=none,1=signed_success,2=signed_failure; verified is 0 or 1; queue is 0=none,1=pending,2=running,3=reported_failed,4=duplicate; age_s is observation age; ttl_s is freshness limit, protected is 0 or 1. In this exact priority order: invalid enum/times (age<0, ttl<=0) or verified=1 while receipt=0 -> -1. Existing receipt (receipt != 0) without verification -> 6. Stale age_s>ttl_s -> 2 historical only, even if a signed terminal exists. Verified signed success -> 3 and verified signed failure -> 4, regardless of queue state. Protected request with nonzero queue -> 5, no action. Otherwise pending/running -> 1; queue=failed or duplicate -> 7 investigate; no active queue -> 0. This is solely a UI classification, not a queue action, retry, protected placement or execution approval. Do not return a string or run tools.';
export const BROKEN=HEADER+'    if queue == 1 or queue == 2:\n        return 1\n    if receipt == 1:\n        return 3\n    if receipt == 2:\n        return 4\n    return 0\n';
export function safeSource(value){
  if(typeof value!=='string'||value.length<75||value.length>1051||value.split('\n').length>24||
     !value.startsWith(HEADER)||!SOURCE.test(value)||BANNED.test(value)||
     value.includes('__')||value.includes('\r'))return null;
  return value.endsWith('\n')?value:value+'\n';
}
export function oracle(v){
  if(!Array.isArray(v)||v.length!==6||v.some(x=>!Number.isSafeInteger(x)||Math.abs(x)>100000))return null;
  const [receipt,verified,queue,age,ttl,protectedFlag]=v;
  if(![0,1,2].includes(receipt)||![0,1].includes(verified)||![0,1,2,3,4].includes(queue)||
     ![0,1].includes(protectedFlag)||age<0||ttl<=0||(!receipt&&verified))return -1;
  if(receipt!==0&&!verified)return 6;
  if(age>ttl)return 2;
  if(receipt===1&&verified===1)return 3;
  if(receipt===2&&verified===1)return 4;
  if(protectedFlag&&queue!==0)return 5;
  if(queue===1||queue===2)return 1;
  if(queue===3||queue===4)return 7;
  return 0;
}
export function admitStep(input){
  if(!input||typeof input!=='object'||Array.isArray(input)||!
     Number.isInteger(input.stage)||![0,1].includes(input.stage))return null;
  const keys=Object.keys(input).sort().join(',');
  if(input.stage===0)return keys==='stage'?{stage:0,source:null,failedExamples:[]}:null;
  if(keys!=='failed_examples,source,stage')return null;
  const source=safeSource(input.source);
  if(!source||!Array.isArray(input.failed_examples)||input.failed_examples.length<1||input.failed_examples.length>3)return null;
  const seen=new Set(),rows=[];
  for(const row of input.failed_examples){
    if(!row||typeof row!=='object'||Array.isArray(row)||Object.keys(row).sort().join(',')!=='expected,input')return null;
    const expected=oracle(row.input);
    if(expected===null||expected!==row.expected)return null;
    const id=JSON.stringify(row.input);
    if(seen.has(id))return null;
    seen.add(id);rows.push({input:row.input,expected});
  }
  return {stage:1,source,failedExamples:rows};
}
export function requestFor(stage,source,failedExamples){
  const system='You generate a fixed, fictional, low-authority Python source artifact. Return ONLY JSON object with one key source, containing the entire function. Preserve exact function signature. Only if/else, return, simple scalar assignments, safe integer arithmetic and comparisons. No imports, exceptions, attributes, iterators, strings, booleans as outputs, calls except min/max, tools, side effects, or markdown. Stay within five local variables and 160 AST nodes.';
  let user='Repair this fictional operator UI evidence-state function.\nBroken example:\n'+BROKEN+'\nRequirements:\n'+TASK;
  if(stage===1){
    user+='\nYour previous actual source candidate:\n'+source+'\nIndependent failed examples (fixed deterministic oracle, not private data):\n';
    for(const row of failedExamples)user+='inputs='+JSON.stringify(row.input)+' expected='+JSON.stringify(row.expected)+'\n';
    user+='\nRevise your source to address the general error while preserving the cases previously correct.';
  }
  return {model:MODEL,temperature:0.2,top_p:0.95,max_tokens:4096,stream:false,
          messages:[{role:'system',content:system},{role:'user',content:user}]};
}
export async function runStep({input,providerFetch,now=()=>Date.now()}){
  const q=admitStep(input);
  if(!q||typeof providerFetch!=='function')throw Error('evidence_status_step_unadmitted');
  const at=now();
  const out={schema:SCHEMA,stage:q.stage,model:MODEL,status:'not_started',provider_calls:0,http_status:null,
    elapsed_ms:0,source:null,source_valid_shape:false,private_input_used:false,
    model_code_executed:false,commands_executed:false,production_admitted:false};
  try{
    out.provider_calls=1;
    const response=await providerFetch(API,{method:'POST',redirect:'manual',body:JSON.stringify(requestFor(q.stage,q.source,q.failedExamples))});
    out.http_status=Number.isInteger(response?.status)&&response.status>=100&&response.status<=599?response.status:null;
    if(out.http_status!==200){out.status=out.http_status===429?'rate_limited':'provider_unavailable';return out;}
    const data=await response.json();const raw=data?.choices?.[0]?.message?.content;
    if(typeof raw!=='string'||raw.length>3500){out.status='format_rejected';return out;}
    let payload;try{payload=JSON.parse(raw.trim());}catch{out.status='format_rejected';return out;}
    if(!payload||typeof payload!=='object'||Array.isArray(payload)||Object.keys(payload).join(',')!=='source'){
      out.status='format_rejected';return out;
    }
    out.source=safeSource(payload.source);out.source_valid_shape=out.source!==null;
    out.status=out.source_valid_shape?'candidate_unexecuted':'format_rejected';
    return out;
  }catch{out.status='transport_or_decode_failure';return out;}
  finally{out.elapsed_ms=Math.max(0,Math.min(120000,now()-at));}
}
