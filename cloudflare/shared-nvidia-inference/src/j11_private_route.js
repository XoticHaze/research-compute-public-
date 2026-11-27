// Bounded private-only J11 turn. This is a handler for the existing
// cc-shared-nvidia-inference Service Binding, not a public endpoint.
// No operator prompt/model/URL, tool execution, or credential export.
const PATH = '/internal/diagnostics/nvidia-j11';
const RESPONSE_HEADERS = {'Content-Type':'application/json','Cache-Control':'no-store'};
const SAFE_STATES = new Set([
  'candidate_unexecuted','format_or_boundary_rejected','rate_limited',
  'provider_unavailable','transport_or_decode_failure',
]);
const FIELDS = new Set([
  'schema','fixture_blob','task_id','observed_routes','model','status',
  'http_status','provider_attempt_upper_bound','prompt_tokens',
  'completion_tokens','elapsed_ms','action','private_input_used',
  'model_action_executed','production_admitted',
]);
function json(code, body) {
  return new Response(JSON.stringify(body),{status:code,headers:RESPONSE_HEADERS});
}
function safeResult(input, selector) {
  if (!input || typeof input!=='object' || Array.isArray(input) ||
      Object.keys(input).length!==FIELDS.size ||
      Object.keys(input).some(k=>!FIELDS.has(k)) ||
      input.schema!=='commandcenter.nvidia.j11_candidate_turn.v1' ||
      input.fixture_blob!==selector.fixture_blob ||
      input.task_id!==selector.task_id ||
      JSON.stringify(input.observed_routes)!==JSON.stringify(selector.observed_routes) ||
      input.private_input_used!==false ||
      input.model_action_executed!==false ||
      input.production_admitted!==false ||
      !SAFE_STATES.has(input.status) ||
      !Number.isInteger(input.provider_attempt_upper_bound) ||
      input.provider_attempt_upper_bound!==1 ||
      !Number.isInteger(input.elapsed_ms) || input.elapsed_ms<0 || input.elapsed_ms>120000 ||
      !(input.http_status===null || (Number.isInteger(input.http_status) && input.http_status>=100 && input.http_status<=599))) return null;
  const tokens=['prompt_tokens','completion_tokens'];
  if (tokens.some(k=>input[k]!==null && !(Number.isInteger(input[k]) && input[k]>=0 && input[k]<=1000000))) return null;
  if (input.model!=='poolside/laguna-xs-2.1') return null;
  const action=input.action;
  if(input.status==='candidate_unexecuted') {
    if(!action || typeof action!=='object' || Array.isArray(action))return null;
    const ks=Object.keys(action).sort().join(',');
    if (ks==='kind' && action.kind==='yield')return input;
    if (ks==='kind,route' && action.kind==='read' &&
        typeof action.route==='string' && action.route.length<=32 &&
        !selector.observed_routes.includes(action.route))return input;
    if (ks==='evidence,kind,state' && action.kind==='submit' &&
        ['active','stale_degraded','guest_independent_rescue_active','unhealthy','unknown'].includes(action.state) &&
        Array.isArray(action.evidence) && action.evidence.length<=3 &&
        action.evidence.every(x=>typeof x==='string' && x.length<=32))return input;
    return null;
  }
  return action===null ? input : null;
}
export async function handleJ11PrivateRoute(request, env, {admitSelector,runFixedJ11Turn,pacedProviderFetch}) {
  const url=new URL(request.url);
  if (url.pathname!==PATH || url.search || request.method!=='POST') return json(404,{error:'route_unavailable'});
  if (env?.CC_NVIDIA_DIAGNOSTIC_ENABLED!=='1') return json(503,{error:'diagnostic_not_admitted'});
  const length=Number(request.headers.get('content-length'));
  if (!Number.isInteger(length) || length<1 || length>192 || request.headers.get('content-type')!=='application/json')
    return json(400,{error:'j11_selector_rejected'});
  let selector;
  try {selector=await request.json();} catch{return json(400,{error:'j11_selector_rejected'});}
  const admitted=admitSelector(selector);
  if (!admitted)return json(400,{error:'j11_selector_rejected'});
  if(typeof env.NVIDIA_API_KEY?.get!=='function')return json(503,{error:'binding_unavailable'});
  let key;
  try {key=await env.NVIDIA_API_KEY.get();}catch{return json(503,{error:'secret_unavailable'});}
  if (typeof key!=='string'||key.length<8)return json(503,{error:'secret_unavailable'});
  const providerFetch=async (endpoint,options)=>{
    // The exact endpoint and model are owned by runFixedJ11Turn, not the caller.
    if(endpoint!=='https://integrate.api.nvidia.com/v1/chat/completions' ||
       options?.method!=='POST' || options.redirect!=='manual')throw Error('fixed_endpoint_only');
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),35000);
    try{return await pacedProviderFetch(endpoint,{...options,
      headers:{'Authorization':'Bearer '+key,'Content-Type':'application/json'},
      redirect:'manual',signal:controller.signal});}
    finally{clearTimeout(timer);}
  };
  let result;
  try { result=await runFixedJ11Turn({selector,providerFetch}); }
  catch{return json(503,{error:'j11_adapter_unavailable'});}
  const safe=safeResult(result,selector);
  if(!safe)return json(502,{error:'j11_untrusted_result'});
  const code=safe.status==='candidate_unexecuted'?200:safe.status==='rate_limited'?429:
    safe.status==='format_or_boundary_rejected'?422:503;
  return json(code,safe);
}
