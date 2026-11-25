// Fixed public-fictional J11 model adapter. No private inputs, arbitrary prompts,
// URLs, model selection, tools or executor authority. Not a standalone gateway.
// Existing private service owner must supply the admitted, budget-reserved fetch.
// Source fixture blob a459d065e6188ea8b01ab1a5b2c721789587982d; gold dispositions intentionally excluded.
export const FIXTURE_BLOB="a459d065e6188ea8b01ab1a5b2c721789587982d";
export const MODEL="poolside/laguna-xs-2.1";
export const MAX_COMPLETION_TOKENS=512;
const TASKS=[
  {
    "id": "A",
    "goal": "Determine current host heartbeat from conflicting registry and mailbox records.",
    "routes": [
      {
        "id": "registry",
        "record": {
          "id": "A-old",
          "ts": 700,
          "kind": "registry",
          "state": "not_installed"
        }
      },
      {
        "id": "mailbox",
        "record": {
          "id": "A-new",
          "ts": 989,
          "kind": "heartbeat",
          "state": "polling",
          "target": "A"
        }
      }
    ]
  },
  {
    "id": "B",
    "goal": "Determine direct edge service health.",
    "routes": [
      {
        "id": "direct",
        "record": {
          "id": "B-now",
          "ts": 994,
          "kind": "heartbeat",
          "state": "idle",
          "service": "running",
          "target": "B"
        }
      }
    ]
  },
  {
    "id": "C",
    "goal": "Assess whether a separate rescue executor covers this guest.",
    "routes": [
      {
        "id": "rescue",
        "record": {
          "id": "C-host",
          "ts": 991,
          "kind": "heartbeat",
          "state": "polling",
          "target": "C",
          "independent_of_guest": true,
          "independent_of_host": false
        }
      }
    ]
  },
  {
    "id": "D",
    "goal": "Determine current worker readiness and heartbeat freshness.",
    "routes": [
      {
        "id": "worker",
        "record": {
          "id": "D-old",
          "ts": 850,
          "kind": "heartbeat",
          "state": "degraded",
          "transport_up": true,
          "guest_ready": false,
          "target": "D"
        }
      }
    ]
  },
  {
    "id": "E",
    "goal": "Assess application health independently of transport.",
    "routes": [
      {
        "id": "edge",
        "record": {
          "id": "E-denied",
          "ts": 993,
          "kind": "transport",
          "state": "passed",
          "nested": "permission_denied",
          "target": "E"
        }
      },
      {
        "id": "application",
        "record": {
          "id": "E-app",
          "ts": 995,
          "kind": "application_health",
          "state": "unhealthy",
          "target": "E"
        }
      }
    ]
  },
  {
    "id": "F",
    "goal": "Reconcile legacy and successor ordinary agent channels.",
    "routes": [
      {
        "id": "legacy",
        "record": {
          "id": "F-old",
          "ts": 600,
          "kind": "heartbeat",
          "state": "polling",
          "target": "F"
        }
      },
      {
        "id": "successor",
        "record": {
          "id": "F-new",
          "ts": 990,
          "kind": "heartbeat",
          "state": "polling",
          "target": "F"
        }
      },
      {
        "id": "neighbor",
        "record": {
          "id": "X-new",
          "ts": 999,
          "kind": "heartbeat",
          "state": "polling",
          "target": "X"
        }
      }
    ]
  },
  {
    "id": "G",
    "goal": "Determine protected worker heartbeat separately from command result.",
    "routes": [
      {
        "id": "result",
        "record": {
          "id": "G-result",
          "ts": 997,
          "kind": "command_receipt",
          "state": "passed",
          "target": "G"
        }
      },
      {
        "id": "protected",
        "record": {
          "id": "G-now",
          "ts": 992,
          "kind": "heartbeat",
          "state": "polling",
          "target": "G"
        }
      }
    ]
  }
];
const AS_OF=1000, FRESHNESS=60;
const STATES=new Set(["active","stale_degraded","guest_independent_rescue_active","unhealthy","unknown"]);
const API="https://integrate.api.nvidia.com/v1/chat/completions";
const keys=(x,k)=>x&&typeof x==="object"&&!Array.isArray(x)&&Object.keys(x).sort().join(",")===k.split(",").sort().join(",");
const count=x=>Number.isSafeInteger(x)&&x>=0&&x<=1000000?x:null;
export function admitSelector(x){
 if(!keys(x,"fixture_blob,task_id,observed_routes")||x.fixture_blob!==FIXTURE_BLOB||!Array.isArray(x.observed_routes)||x.observed_routes.length>3)return null;
 const task=TASKS.find(t=>t.id===x.task_id);
 if(!task||new Set(x.observed_routes).size!==x.observed_routes.length||!x.observed_routes.every(r=>typeof r==="string"&&task.routes.some(t=>t.id===r)))return null;
 return {task,observations:x.observed_routes.map(r=>task.routes.find(t=>t.id===r))};
}
export function promptFor(selector){
 const a=admitSelector(selector);if(!a)throw Error("invalid_fixed_j11_selector");
 const input={task_id:a.task.id,goal:a.task.goal,as_of:AS_OF,freshness_seconds:FRESHNESS,available_routes:a.task.routes.map(r=>r.id),observations:a.observations,allowed_states:[...STATES]};
 return [{role:"system",content:"Perform one bounded evidence-reconciliation turn on fictional infrastructure. Return exactly one JSON object: {\"kind\":\"read\",\"route\":\"one available unread route\"}, {\"kind\":\"submit\",\"state\":\"one allowed state\",\"evidence\":[\"observed evidence IDs\"]}, or {\"kind\":\"yield\"}. No other fields or prose. Do not invent evidence, confuse transport with health, or claim an unavailable action."},{role:"user",content:JSON.stringify(input)}];
}
export function candidateAction(selector,raw){
 const a=admitSelector(selector);if(!a||typeof raw!=="string"||raw.length>2048)return null;
 let v;try{v=JSON.parse(raw);}catch{return null;}
 if(keys(v,"kind,route")&&v.kind==="read"&&a.task.routes.some(r=>r.id===v.route)&&!selector.observed_routes.includes(v.route))return v;
 if(keys(v,"kind,state,evidence")&&v.kind==="submit"&&STATES.has(v.state)&&Array.isArray(v.evidence)&&v.evidence.length>=1&&v.evidence.length<=3&&new Set(v.evidence).size===v.evidence.length&&v.evidence.every(id=>a.observations.some(o=>o.record.id===id)))return v;
 if(keys(v,"kind")&&v.kind==="yield")return v;
 return null;
}
export async function runFixedJ11Turn({selector,providerFetch,now=()=>Date.now()}){
 if(!admitSelector(selector)||typeof providerFetch!=="function")throw Error("fixed_j11_unadmitted");
 const start=now(),out={schema:"commandcenter.nvidia.j11_candidate_turn.v1",fixture_blob:FIXTURE_BLOB,task_id:selector.task_id,observed_routes:[...selector.observed_routes],model:MODEL,status:"unattempted",http_status:null,provider_attempt_upper_bound:0,prompt_tokens:null,completion_tokens:null,elapsed_ms:0,action:null,private_input_used:false,model_action_executed:false,production_admitted:false};
 try{
  const body={model:MODEL,messages:promptFor(selector),max_tokens:MAX_COMPLETION_TOKENS,temperature:0,stream:false};
  out.provider_attempt_upper_bound=1;
  const res=await providerFetch(API,{method:"POST",redirect:"manual",body:JSON.stringify(body)});
  out.http_status=Number.isInteger(res?.status)&&res.status>=100&&res.status<=599?res.status:null;
  if(out.http_status!==200){out.status=out.http_status===429?"rate_limited":"provider_unavailable";return out;}
  const d=await res.json();
  out.prompt_tokens=count(d?.usage?.prompt_tokens);out.completion_tokens=count(d?.usage?.completion_tokens);
  out.action=candidateAction(selector,d?.choices?.[0]?.message?.content);
  out.status=out.action?"candidate_unexecuted":"format_or_boundary_rejected";
 }catch{out.status="transport_or_decode_failure";}
 finally{out.elapsed_ms=Math.max(0,Math.min(120000,now()-start));}
 return out;
}
