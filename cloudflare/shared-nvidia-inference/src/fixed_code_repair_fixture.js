// One source-owned synthetic Python bug, not arbitrary repository code or prompts.
// Model code may be returned only after shape/character/length sanitation;
// it is never executed by this Worker or authorized as a real command.
export const MODELS=Object.freeze(["poolside/laguna-xs-2.1","minimaxai/minimax-m3.1-flash"]);
export const TASK_ID="RETRY_DEADLINE_01";
export const BROKEN=Object.freeze({
  path:"synthetic/retry_schedule.py",
  source:"def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):\n    if attempt > max_attempts:\n        return None\n    return min(cap_ms, base_ms * (2 ** attempt))\n",
  requirements:"The function retry_delay_ms(attempt, max_attempts, base_ms, cap_ms) receives the count of completed attempts (1-based). It returns None for attempt <= 0, max_attempts <= 0, attempt >= max_attempts, base_ms <= 0 or cap_ms <= 0. Otherwise return the capped exponential backoff min(cap_ms, base_ms * 2 ** (attempt - 1)). For example attempt=1,max_attempts=3,base_ms=100,cap_ms=500 returns 100; attempt=2 returns 200; attempt=3 returns None. Preserve function name and exactly four parameters. Pure Python standard built-ins only; no imports, loops, assignment, globals, I/O, network, calls other than min, and no side effects."
});
export function fixedRepairRequest(modelIndex){
 if(!Number.isInteger(modelIndex)||modelIndex<0||modelIndex>=MODELS.length)
  throw Error("invalid_fixed_code_model_index");
 return {
  model:MODELS[modelIndex],temperature:0,max_tokens:500,stream:false,
  messages:[
   {role:"system",content:"You are an offline code-repair worker. Return ONLY a compact JSON object with exactly one key source, containing the complete corrected Python function source as a string. No markdown, prose, comments, imports, type annotations, strings, I/O, tool calls, or external libraries. Only if statements, return statements, integer arithmetic, comparisons, boolean conditions, and min() are needed. Do not modify any files or request tools."},
   {role:"user",content:"Repair this exact synthetic function, preserving its signature. Known bug is off-by-one retries and missing input validation.\nPATH: "+BROKEN.path+"\nSOURCE:\n"+BROKEN.source+"\nREQUIRED BEHAVIOR:\n"+BROKEN.requirements}
  ]
 };
}
export function sanitizeCodeCandidate(message){
 if(typeof message!=="string"||message.length>1600)return null;
 let obj;
 try{obj=JSON.parse(message.trim());}catch{return null;}
 if(!obj||typeof obj!=="object"||Array.isArray(obj)||Object.keys(obj).join(",")!=="source")
  return null;
 const src=obj.source;
 if(typeof src!=="string"||src.length<75||src.length>1050||
    src.split("\n").length>24||
    !/^def retry_delay_ms\(attempt, max_attempts, base_ms, cap_ms\):\n/.test(src)||
    !/^[A-Za-z0-9_ ()*,+\-<>=:\n]+$/.test(src)||
    /\b(?:import|exec|eval|open|globals|locals|lambda|class|del|while|for|yield|async|await|print|input|NVIDIA|secret|key|token)\b/i.test(src)||
    src.includes("__")||src.includes("\r"))return null;
 return src.endsWith("\n")?src:src+"\n";
}
