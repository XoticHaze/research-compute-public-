// No generated draft text crosses this local Service Binding caller.
const ids=["OP01","OP02","CX01","CX02"];
const kinds=["operator","operator","customer","customer"];
const statuses=new Set(["completed_not_human_reviewed","rate_limited","provider_or_transport_held","time_limit"]);
export function sanitizeDraftReceipt(input){
 if(!input||input.schema!=="commandcenter.nvidia_fixed_draft_pilot.v1"||
    input.model!=="poolside/laguna-xs-2.1"||
    !statuses.has(input.status)||!Number.isInteger(input.attempted)||
    input.attempted<0||input.attempted>4||
    !Array.isArray(input.results)||input.results.length!==input.attempted)
   return null;
 const rows=input.results.map((r,i)=>{
  if(!r||r.id!==ids[i]||r.kind!==kinds[i])return null;
  if(r.http_status!==null&&(!Number.isInteger(r.http_status)||r.http_status<100||r.http_status>599))return null;
  if(!Number.isInteger(r.latency_ms)||r.latency_ms<0||r.latency_ms>120000||
     !Number.isInteger(r.anchor_groups)||r.anchor_groups<1||r.anchor_groups>8||
     !Number.isInteger(r.anchor_groups_met)||r.anchor_groups_met<0||r.anchor_groups_met>r.anchor_groups)
    return null;
  return {id:ids[i],kind:kinds[i],http_status:r.http_status,
   latency_ms:r.latency_ms,format_valid:r.format_valid===true,
   anchor_groups:r.anchor_groups,anchor_groups_met:r.anchor_groups_met,
   unsupported_claim_flag:r.unsupported_claim_flag===true,
   human_review_flag:r.human_review_flag===true,
   draft_length_ok:r.draft_length_ok===true,
   draft_passed:r.draft_passed===true,
   template_passed:r.template_passed===true,
   error:["aborted","transport_error"].includes(r.error)?r.error:null};
 });
 if(rows.some(x=>!x)||input.status==="completed_not_human_reviewed"&&rows.length!==4)return null;
 return {schema:input.schema,model:"poolside/laguna-xs-2.1",
    status:input.status,attempted:input.attempted,results:rows,
    model_text_exposed:false,private_input_used:false,commands_executed:false,
    customer_messages_sent:false,template_only_baseline:true};
}
