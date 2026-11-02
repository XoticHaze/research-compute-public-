// Immutable, fully fictional and public-safe coding roles. No private repo content.
// Task index is a fixed selector, never a caller-supplied source, prompt or URL.
export const MODELS=Object.freeze(["poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash"]);
export const TASKS=Object.freeze([
 {id:"RETRY_DEADLINE_01",name:"retry_delay_ms",args:["attempt","max_attempts","base_ms","cap_ms"],
  broken:"def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):\n    if attempt > max_attempts:\n        return None\n    return min(cap_ms, base_ms * (2 ** attempt))\n",
  requirements:"For completed 1-based attempt, return None if attempt<=0 or max_attempts<=0 or attempt>=max_attempts or base_ms<=0 or cap_ms<=0. Otherwise return min(cap_ms, base_ms * (2 ** (attempt-1))). Example attempt=1,max_attempts=3,base_ms=100,cap_ms=500 returns 100; attempt=3 returns None."},
 {id:"BOUNDED_CLAMP_02",name:"clamp_window",args:["value","low","high","fallback"],
  broken:"def clamp_window(value, low, high, fallback):\n    if value > high:\n        return high\n    return value\n",
  requirements:"If low>high, return fallback. Otherwise return low when value<low, high when value>high, and value in [low,high]. Inclusive boundaries. All inputs are integers, which can be negative. Example clamp_window(-4,0,8,99)=0; clamp_window(9,0,8,99)=8; clamp_window(5,8,2,99)=99."},
 {id:"RESERVED_BUDGET_03",name:"budget_remaining",args:["limit","spent","reserved","floor"],
  broken:"def budget_remaining(limit, spent, reserved, floor):\n    if spent > limit:\n        return None\n    return limit - spent\n",
  requirements:"Return None if any parameter is negative. Let free=limit-spent-reserved. Return None if free<floor; otherwise return free. Equality with floor is allowed. Examples budget_remaining(100,40,20,30)=40; budget_remaining(100,70,20,11)=None; budget_remaining(100,90,10,0)=0."},
 {id:"ALLOCATION_BPS_04",name:"allocation_limit",args:["equity","risk_bps","cap_usd","minimum_usd"],
  broken:"def allocation_limit(equity, risk_bps, cap_usd, minimum_usd):\n    return min(cap_usd, equity * risk_bps)\n",
  requirements:"Return None if equity<=0, risk_bps<=0, risk_bps>10000, cap_usd<=0, minimum_usd<=0 or cap_usd<minimum_usd. Compute allowed=min(cap_usd, (equity*risk_bps)//10000) using integer floor division. Return None if allowed<minimum_usd; otherwise return allowed. Examples (100000,100,1500,10)->1000; (100000,200,1500,10)->1500; (10000,1,1000,2)->None. This is a fictional arithmetic calculation, not a trading instruction."},
 {id:"STALE_HEARTBEAT_05",name:"staleness_status",args:["now_ms","last_ms","warn_ms","expire_ms"],
  broken:"def staleness_status(now_ms, last_ms, warn_ms, expire_ms):\n    if now_ms - last_ms >= warn_ms:\n        return 1\n    return 0\n",
  requirements:"Return -1 for invalid input: now_ms<0, last_ms<0, now_ms<last_ms, warn_ms<=0, expire_ms<=warn_ms. Otherwise return 0 if elapsed (now_ms-last_ms)<warn_ms, 1 if warn_ms<=elapsed<expire_ms, 2 if elapsed>=expire_ms. Examples (250,0,100,300)->1; (300,0,100,300)->2; (50,100,10,20)->-1."}
]);
export const SAFE_SOURCE=/^[A-Za-z0-9_ ()*,+\-<>=:\/\n]+$/;
const FORBIDDEN=/\b(?:import|exec|eval|open|globals|locals|lambda|class|del|while|for|yield|async|await|print|input|NVIDIA|secret|key|token|subprocess)\b/i;
export function validatedTaskIndex(index){
 if(!Number.isInteger(index)||index<0||index>=TASKS.length)throw Error("invalid_synthetic_code_task_index");
 return TASKS[index];
}
export function requestFor(modelIndex,taskIndex){
 if(!Number.isInteger(modelIndex)||modelIndex<0||modelIndex>=MODELS.length)throw Error("invalid_synthetic_code_model_index");
 const t=validatedTaskIndex(taskIndex);
 // Separate fixed synthetic experiment settings from production admission.
 // NVIDIA documents Poolside's endpoint default generation allowance as 8192,
 // temperature=1 and top_p=.95. MiniMax supports up to 65536 generated
 // tokens; 8192 is an initial DISCOVERY allowance, not a capability ceiling.
 // Only lower a model's budget in a distinct measured follow-up after
 // recording finish_reason and token usage. Provider/transport timeouts and
 // rate limits are separate, independently reported safety constraints.
 // Never accept caller-supplied model parameters, sources, tools, or budgets.
 const opts={temperature:1.0,top_p:0.95,max_tokens:8192};
 return {model:MODELS[modelIndex],...opts,stream:false,
 messages:[
  {role:"system",content:"You are an offline synthetic code repair worker. Return ONLY a JSON object with one key named source holding the complete Python function source. Preserve the exact signature. No comments, prose, markdown, imports, assigned variables, loops, type hints, string literals, tools, dependencies or side effects. Use only if/else, return, integer arithmetic, boolean comparisons, min, max."},
  {role:"user",content:"Fix this single fictional Python function. Original source:\n"+t.broken+"\nRequired behavior:\n"+t.requirements}
 ]};
}
export function sanitizeCandidate(raw,taskIndex){
 const t=validatedTaskIndex(taskIndex);
 if(typeof raw!=="string"||raw.length>3000)return null;
 let json;
 try{json=JSON.parse(raw.trim());}catch{return null;}
 if(!json||typeof json!=="object"||Array.isArray(json)||Object.keys(json).join(",")!=="source")return null;
 const source=json.source;
 if(typeof source!=="string"||source.length<55||source.length>1800||source.split("\n").length>35||
    !source.startsWith("def "+t.name+"("+t.args.join(", ")+"):\n")||
    !SAFE_SOURCE.test(source)||FORBIDDEN.test(source)||source.includes("__")||
    source.includes("\r"))return null;
 return source.endsWith("\n")?source:source+"\n";
}
