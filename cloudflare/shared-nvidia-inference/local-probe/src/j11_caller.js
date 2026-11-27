// Loopback-only, single J11 Service Binding call; never deploy this caller.
// The only configurable payload is a fixed fictional task selector; the
// private Worker owns all model prompts, credentials and provider I/O.
const PATH='/j11-once';
const TARGET='https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia-j11';
const HEADERS={'Content-Type':'application/json','Cache-Control':'no-store'};
const FIXTURE='a459d065e6188ea8b01ab1a5b2c721789587982d';
function reply(status,body){return new Response(JSON.stringify(body),{status,headers:HEADERS});}
const exactKeys=(x,s)=>x&&typeof x==='object'&&!Array.isArray(x)&&Object.keys(x).sort().join(',')===s.split(',').sort().join(',');
export function createJ11Caller(){
  let used=false;
  return {async fetch(request,env){
    const u=new URL(request.url);
    if(request.method!=='POST'||u.pathname!==PATH||u.search ||
       !['localhost','127.0.0.1','[::1]'].includes(u.hostname))
      return reply(404,{classification:'local_route_unavailable'});
    const n=Number(request.headers.get('content-length'));
    if(used || !Number.isInteger(n) || n<1 || n>192 || request.headers.get('content-type')!=='application/json')
      return reply(used?409:400,{classification:used?'j11_replay_denied':'j11_selector_rejected'});
    let selector;
    try{selector=await request.json();}catch{return reply(400,{classification:'j11_selector_rejected'});}
    if(!exactKeys(selector,'fixture_blob,task_id,observed_routes')||selector.fixture_blob!==FIXTURE||
       !/^[A-G]$/.test(selector.task_id)||!Array.isArray(selector.observed_routes)||selector.observed_routes.length>3||
       new Set(selector.observed_routes).size!==selector.observed_routes.length||
       !selector.observed_routes.every(x=>typeof x==='string'&&/^[a-z]{3,15}$/.test(x)))
      return reply(400,{classification:'j11_selector_rejected'});
    if(typeof env?.NVIDIA_SERVICE?.fetch!=='function')return reply(503,{classification:'private_binding_unavailable'});
    used=true; // One attempt even for indeterminate transport; no blind replay.
    let upstream;
    try{upstream=await env.NVIDIA_SERVICE.fetch(new Request(TARGET,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selector)}));}
    catch{return reply(503,{classification:'j11_service_transport_unknown'});}
    let d;
    try{d=await upstream.json();}catch{return reply(502,{classification:'j11_service_result_invalid'});}
    if(!d||d.schema!=='commandcenter.nvidia.j11_candidate_turn.v1'||d.fixture_blob!==FIXTURE||
       d.task_id!==selector.task_id||JSON.stringify(d.observed_routes)!==JSON.stringify(selector.observed_routes)||
       d.private_input_used!==false||d.model_action_executed!==false||d.production_admitted!==false||
       d.provider_attempt_upper_bound!==1||!['candidate_unexecuted','format_or_boundary_rejected',
         'rate_limited','provider_unavailable','transport_or_decode_failure'].includes(d.status))
      return reply(502,{classification:'j11_service_result_untrusted'});
    // Reproduce only the narrow candidate envelope and independent receipt data.
    const safe={schema:d.schema,fixture_blob:d.fixture_blob,task_id:d.task_id,
      observed_routes:d.observed_routes,model:d.model,status:d.status,http_status:d.http_status,
      provider_attempt_upper_bound:1,prompt_tokens:d.prompt_tokens,completion_tokens:d.completion_tokens,
      elapsed_ms:d.elapsed_ms,action:d.action,private_input_used:false,
      model_action_executed:false,production_admitted:false};
    if(safe.model!=='poolside/laguna-xs-2.1'||
       !Number.isInteger(safe.elapsed_ms)||safe.elapsed_ms<0||safe.elapsed_ms>120000||
       (safe.prompt_tokens!==null&&(!Number.isInteger(safe.prompt_tokens)||safe.prompt_tokens<0||safe.prompt_tokens>1000000))||
       (safe.completion_tokens!==null&&(!Number.isInteger(safe.completion_tokens)||safe.completion_tokens<0||safe.completion_tokens>1000000)))
      return reply(502,{classification:'j11_service_result_untrusted'});
    return reply(d.status==='candidate_unexecuted'?200:d.status==='rate_limited'?429:503,safe);
  }};
}
export default createJ11Caller();
