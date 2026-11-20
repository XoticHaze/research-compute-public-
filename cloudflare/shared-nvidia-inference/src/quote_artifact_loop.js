// Fixed public-fictional quote artifact repair. Advisory research only.
// Source is never executed by this Worker; no arbitrary prompts or protected work.
const API="https://integrate.api.nvidia.com/v1/chat/completions";
export const MODEL="poolside/laguna-xs-2.1";
export const ARGS=["minutes","hourly_cents","travel_cents","supplies_cents","overhead_bps","margin_bps"];
export const HEADER="def quote_price_cents("+ARGS.join(", ")+"):\n";
const SOURCE=/^[A-Za-z0-9_ ()*,+\-<>=:\/\n]+$/;
const BANNED=/\b(?:import|exec|eval|open|globals|locals|lambda|class|del|while|for|yield|async|await|print|input|secret|key|token|subprocess)\b/i;
export const TASK="Return None if any input is negative, if overhead_bps > 10000, if margin_bps >= 10000, or if computed total cost is zero. All inputs are integers. Compute labor cents by rounding UP minutes * hourly_cents / 60; base cost = labor + travel_cents + supplies_cents. Overhead cents = ROUND UP(base cost * overhead_bps / 10000). Total cost = base + overhead. Desired quote price is ROUND UP(total cost * 10000 / (10000 - margin_bps)), where margin is profit divided by customer price, not markup on cost. Return the quote price in integer cents. No float, currency strings or negative results. Example (90,3500,500,250,1000,2500) returns 8800.";
export const BROKEN=HEADER+"    base = minutes * hourly_cents // 60 + travel_cents + supplies_cents\n    cost = base + base * overhead_bps // 10000\n    return cost * (10000 + margin_bps) // 10000\n";
export function safeSource(source){
 if(typeof source!=="string"||source.length<110||source.length>1050||source.split("\n").length>24||!source.startsWith(HEADER)||!SOURCE.test(source)||BANNED.test(source)||source.includes("__")||source.includes("\r"))return null;
 return source.endsWith("\n")?source:source+"\n";
}
export function quoteOracle(input){
 if(!Array.isArray(input)||input.length!==6||input.some(x=>!Number.isSafeInteger(x)||x<0||x>100000)||input[4]>10000||input[5]>=10000)return null;
 const [minutes,hourly,travel,supplies,overhead_bps,margin_bps]=input;
 const base=Math.ceil(minutes*hourly/60)+travel+supplies;
 const cost=base+Math.ceil(base*overhead_bps/10000);
 if(cost===0)return null;
 const price=Math.ceil(cost*10000/(10000-margin_bps));
 return Number.isSafeInteger(price)&&price<=1000000000?price:null;
}
export function requestFor(stage,source,failedExamples){
 const sys="You are an offline fictional quoting code repair worker. Reply ONLY with JSON object with one key named source containing a complete Python function. Preserve the exact signature. No markdown, commentary, imports, Python builtins except min/max, type hints, strings, loops, exceptions, attributes, dictionaries, external calls or side effects. Only if/else, return, up to four scalar local assignments, integer arithmetic and comparisons.";
 let user="Repair this fictional quote pricing function.\nOriginal source:\n"+BROKEN+"\nRequirements:\n"+TASK;
 if(stage===1){
  user+="\nYour previous source candidate:\n"+source;
  user+="\nIndependently scored failed examples; update your function, not just the example outputs:\n";
  for(const row of failedExamples)user+="inputs="+JSON.stringify(row.input)+" expected="+JSON.stringify(row.expected)+"\n";
  user+="\nPreserve all correct behavior, including cost-zero and invalid-input cases.";
 }
 return {model:MODEL,temperature:0.2,top_p:0.95,max_tokens:4096,stream:false,
   messages:[{role:"system",content:sys},{role:"user",content:user}]};
}
export function admitStep(input){
 if(!input||typeof input!=="object"||Array.isArray(input)||!Number.isInteger(input.stage)||!([0,1].includes(input.stage)))return null;
 const keys=Object.keys(input).sort().join(",");
 if(input.stage===0)return keys==="stage"?{stage:0,source:null,failedExamples:[]}:null;
 if(keys!=="failed_examples,source,stage")return null;
 const source=safeSource(input.source);
 if(!source||!Array.isArray(input.failed_examples)||input.failed_examples.length<1||input.failed_examples.length>3)return null;
 const seen=new Set(),rows=[];
 for(const row of input.failed_examples){
  if(!row||typeof row!=="object"||Array.isArray(row)||Object.keys(row).sort().join(",")!=="expected,input")return null;
  const expected=quoteOracle(row.input);
  if(expected!==row.expected || (expected===null && row.expected!==null))return null;
  const id=JSON.stringify(row.input);
  if(seen.has(id))return null;seen.add(id);
  rows.push({input:row.input,expected});
 }
 return {stage:1,source,failedExamples:rows};
}
export async function runQuoteStep({input,providerFetch,now=()=>Date.now()}){
 const q=admitStep(input);
 if(!q||typeof providerFetch!=="function")throw Error("quote_step_unadmitted");
 const at=now();
 const out={schema:"commandcenter.public_synthetic_quote_artifact_step.v1",stage:q.stage,
  model:MODEL,status:"not_started",provider_calls:0,http_status:null,
  elapsed_ms:0,source:null,source_valid_shape:false,private_input_used:false,
  model_code_executed:false,commands_executed:false,production_admitted:false};
 try{
  out.provider_calls=1;
  const r=await providerFetch(API,{method:"POST",redirect:"manual",body:JSON.stringify(requestFor(q.stage,q.source,q.failedExamples))});
  out.http_status=Number.isInteger(r?.status)&&r.status>=100&&r.status<=599?r.status:null;
  if(out.http_status!==200){out.status=out.http_status===429?"rate_limited":"provider_unavailable";return out;}
  const data=await r.json();let raw=data?.choices?.[0]?.message?.content;
  if(typeof raw!=="string"||raw.length>3500){out.status="format_rejected";return out;}
  let parsed;try{parsed=JSON.parse(raw.trim());}catch{out.status="format_rejected";return out;}
  if(!parsed||typeof parsed!=="object"||Array.isArray(parsed)||Object.keys(parsed).join(",")!=="source"){out.status="format_rejected";return out;}
  out.source=safeSource(parsed.source);out.source_valid_shape=out.source!==null;
  out.status=out.source_valid_shape?"candidate_unexecuted":"format_rejected";
  return out;
 }catch{out.status="transport_or_decode_failure";return out;}
 finally{out.elapsed_ms=Math.max(0,Math.min(120000,now()-at));}
}
