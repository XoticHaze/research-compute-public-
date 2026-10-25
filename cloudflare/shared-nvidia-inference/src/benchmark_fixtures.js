// Shared Voice Engine synthetic task semantics, implemented for the existing
// private Cloudflare provider. No household inputs, credentials or raw answers.
export const TASKS = ["logic","json","math","tool_call"];
export const TOOL = {
 type:"function",function:{name:"set_demo_light",description:"Set fictional demo light brightness",
 parameters:{type:"object",properties:{
  entity_id:{type:"string"},brightness_pct:{type:"integer"}
 },required:["entity_id","brightness_pct"],additionalProperties:false}}
};
export const PROMPT = {
 logic:"All tulips are flowers. No flowers are stones. Can any tulip be a stone? Reply YES or NO only.",
 json:'Return ONLY valid JSON with exactly three keys: "event"="motion", "count"=2, "urgent"=false.',
 math:"Compute 17 multiplied by 19. Reply with digits only.",
 tool_call:"Use the provided Home Assistant tool to set the brightness of the FICTIONAL light.demo_desk to 35 percent. Do not write prose; call the tool."
};
export function modelId(value) {
 return typeof value==="string" && value.length<=160 &&
 /^[a-z0-9_.:-]+\/[a-z0-9_.:-]+$/i.test(value);
}
export function eligibleChatModel(id) {
 return modelId(id) && !/(embed|rerank|retriev|guard|safety|moderation|parakeet|canary|asr|tts|translat|speech|audio|imagegen|cosmos|ocr|parse|diffusion|vision-encoder|video|fuyu|kosmos|deplot)/i.test(id);
}
export function messages(task) {
 if(!TASKS.includes(task)) throw Error("unsupported_task");
 return [{role:"user",content:PROMPT[task]}];
}
export function request(model,task) {
 const body={model,messages:messages(task),temperature:0,max_tokens:160,stream:false};
 if(task==="tool_call"){body.tools=[TOOL];body.tool_choice="auto";}
 return body;
}
export function scored(task,msg) {
 if(task==="tool_call"){
   const calls=msg?.tool_calls;
   if(!Array.isArray(calls)||calls.length!==1||calls[0]?.type!=="function"||
     calls[0]?.function?.name!=="set_demo_light") return false;
   const argument=calls[0].function.arguments;
   if(typeof argument!=="string"||argument.length>512) return false;
   try { const obj=JSON.parse(argument);
     return obj && typeof obj==="object" && !Array.isArray(obj) &&
       Object.keys(obj).length===2 && obj.entity_id==="light.demo_desk" &&
       Number.isInteger(obj.brightness_pct) && obj.brightness_pct===35;
   } catch {return false;}
 }
 const text=msg?.content;
 if(typeof text!=="string") return false;
 if(task==="logic") return /^no[.!]?$/i.test(text.trim());
 if(task==="math") return /^323\.?$/.test(text.trim());
 if(task==="json"){try{const obj=JSON.parse(text.trim());return obj&&
   Object.keys(obj).length===3&&obj.event==="motion"&&
   obj.count===2&&obj.urgent===false;}catch{return false;}}
 return false;
}
