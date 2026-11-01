// Private, fixed-choice micro-worker benchmark. Every prompt/model comes from
// the reviewed 24-case fixture. No general model proxy or command execution.
import {MICRO_MODELS,MICRO_CASES,microRequest,scoreMicro} from "./micro_worker_fixtures.js";
const API="https://integrate.api.nvidia.com";
const SCHEMA="commandcenter.nvidia_micro_worker_synthetic.v1";
export async function runMicroWorkerBatch({modelIndex,batch,providerFetch,now=()=>Date.now()}){
 if(!Number.isInteger(modelIndex)||modelIndex<0||modelIndex>1||
    !Number.isInteger(batch)||batch<0||batch>5||
    typeof providerFetch!=="function")throw Error("invalid_micro_benchmark_request");
 const start=now(),out={schema:SCHEMA,model:MICRO_MODELS[modelIndex],model_index:modelIndex,batch,
    status:"not_started",calls:0,elapsed_ms:0,results:[],raw_response_exposed:false,
    private_input_used:false,command_executed:false,credential_exposed:false};
 try{
  const model=MICRO_MODELS[modelIndex];
  for(let i=0;i<4;i++){
   if(out.calls>=4 || now()-start>115000){out.status="limit_reached";return out;}
   const fixture=MICRO_CASES[batch*4+i];
   const t0=now();
   const row={id:fixture.id,category:fixture.category,http_status:null,latency_ms:null,
      format_valid:false,passed:false,error:null};
   try{
    out.calls++;
    const r=await providerFetch(API+"/v1/chat/completions",{
       method:"POST",redirect:"manual",body:JSON.stringify(microRequest(modelIndex,batch,i))});
    row.http_status=Number.isInteger(r?.status)&&r.status>=100&&r.status<=599?r.status:null;
    row.latency_ms=Math.min(120000,Math.max(0,now()-t0));
    if(row.http_status===200){
      const data=await r.json();
      const decision=scoreMicro(data?.choices?.[0]?.message,fixture);
      row.format_valid=decision.valid;row.passed=decision.passed;
    }
   }catch(e){
    row.error=e?.name==="AbortError"?"aborted":e?.name==="TimeoutError"?"timeout":"transport_error";
    row.latency_ms=Math.min(120000,Math.max(0,now()-t0));
   }
   out.results.push(row);
   if(row.http_status===401 || row.http_status===402 || row.http_status===429){
      out.status=row.http_status===429?"rate_limited":"account_gate";return out;
   }
   // On model/endpoint unavailable, preserve the first result and do not
   // falsely score remaining fixtures; caller can classify incomplete.
   if([403,404,410].includes(row.http_status) || row.error){
      out.status="model_unavailable_or_transport";return out;
   }
  }
  out.status="batch_complete";
  return out;
 }finally{out.elapsed_ms=Math.min(120000,Math.max(0,now()-start));}
}
