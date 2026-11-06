// AI Lab M1 chat state for the incumbent Access-verified operator Durable Object.
// Store only bounded explicit user/model text. No arbitrary tools, GitHub actions,
// device controls, broker authority, raw model reasoning or provider credentials.
export const CHAT_SCHEMA = "operator.ai_lab.chat.v1";
export const CHAT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b";
const MAX_USER = 1200, MAX_REPLY = 3000, MAX_MESSAGES = 32, MAX_CALLS_PER_DAY = 8;
const EXPIRY_MS = 30 * 86400_000;
const PENDING_MS = 70_000;
const INPUT_KEYS = "id,schema,text";

function json(data, status=200) {
  return new Response(JSON.stringify(data), { status, headers: {
    "content-type": "application/json; charset=utf-8", "cache-control": "private, no-store",
    "x-content-type-options": "nosniff"
  }});
}
const isUuid = value => typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const dateUtc = ms => new Date(ms).toISOString().slice(0, 10);
const safeText = (v, max) => typeof v === "string" && v.trim().length > 0 && v.length <= max
  && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(v);
export function validateChatInput(body) {
  if (!body || Array.isArray(body) || typeof body !== "object"
      || Object.keys(body).sort().join(",") !== INPUT_KEYS || body.schema !== CHAT_SCHEMA
      || !isUuid(body.id) || !safeText(body.text, MAX_USER)) throw Error("chat_input_invalid");
  return { id: body.id, content: body.text.trim() };
}
function cleanSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object" || !Array.isArray(snapshot.entries)
      || snapshot.entries.length > MAX_MESSAGES
      || !Number.isInteger(snapshot.calls) || snapshot.calls < 0 || snapshot.calls > MAX_CALLS_PER_DAY
      || !/^\d{4}-\d\d-\d\d$/.test(snapshot.day)
      || !Number.isFinite(snapshot.last_call_ms) || snapshot.last_call_ms < 0) return null;
  if (!snapshot.entries.every(x => x && typeof x === "object"
      && typeof x.id === "string" && ["user","assistant"].includes(x.role)
      && ["complete","pending","failed"].includes(x.status)
      && safeText(x.content,x.role === "user" ? MAX_USER : MAX_REPLY)
      && typeof x.created_at === "string" && Number.isFinite(Date.parse(x.created_at)))) return null;
  if (snapshot.pending !== null && !isUuid(snapshot.pending?.id)) return null;
  if (snapshot.pending && !Number.isFinite(snapshot.pending.started_ms)) return null;
  return snapshot;
}
function empty(now) {return { schema: CHAT_SCHEMA, entries: [], pending: null, day: dateUtc(now), calls: 0, last_call_ms: 0 };}
async function state(storage, now) {
  const current = await storage.get("ai_lab_chat_v1");
  if (current === undefined) return empty(now);
  const loaded = cleanSnapshot(current);
  if (!loaded || loaded.schema !== CHAT_SCHEMA) throw Error("chat_state_invalid");
  const today = dateUtc(now);
  if (loaded.day !== today) {loaded.day = today; loaded.calls = 0;}
  // Purge older transcript entries, but never reset quota or replay accounting by clearing.
  loaded.entries = loaded.entries.filter(x => now - Date.parse(x.created_at) < EXPIRY_MS);
  if (loaded.pending && now - loaded.pending.started_ms > PENDING_MS) {
    const pending = loaded.entries.find(x => x.id === loaded.pending.id && x.role === "user");
    if (pending) pending.status = "failed";
    loaded.pending = null;
  }
  return loaded;
}
function publicView(x) {
  return { ok: true, schema: CHAT_SCHEMA, model: CHAT_MODEL,
    entries: x.entries, pending: Boolean(x.pending), daily_calls_used: x.calls,
    daily_call_limit: MAX_CALLS_PER_DAY, storage: "operator_partitioned_durable_object" };
}
export async function aiChatStateFetch(request, storage, now=Date.now()) {
  const path = new URL(request.url).pathname;
  if (request.method === "GET" && path === "/chat/latest") {
    try { return json(publicView(await state(storage, now))); }
    catch { return json({error:"chat_state_unavailable"},503); }
  }
  if (request.method === "POST" && path === "/chat/prepare") {
    let input;
    try { input = validateChatInput(await request.json()); }
    catch { return json({error:"chat_input_rejected"},400); }
    const outcome = await storage.transaction(async txn => {
      let s; try { s = await state(txn,now); } catch { return {error:"chat_state_unavailable",code:503}; }
      const repeat = s.entries.find(x => x.id === input.id && x.role === "user");
      if (repeat) return {error:"chat_request_already_recorded",code:409};
      if (s.pending) return {error:"chat_request_in_progress",code:409};
      if (s.calls >= MAX_CALLS_PER_DAY) return {error:"chat_daily_limit_reached",code:429};
      if (now - s.last_call_ms < 3000) return {error:"chat_cooldown",code:429};
      s.entries.push({id:input.id,role:"user",content:input.content,status:"pending",
        created_at:new Date(now).toISOString()});
      s.entries = s.entries.slice(-MAX_MESSAGES);
      s.pending = {id:input.id,started_ms:now};
      s.calls += 1; s.last_call_ms = now;
      await txn.put("ai_lab_chat_v1",s);
      const messages = s.entries.filter(x => x.status === "complete" || x.id === input.id)
        .slice(-12).map(x => ({role:x.role,content:x.content}));
      return {id:input.id,messages};
    });
    if (outcome.error) return json({error:outcome.error},outcome.code);
    return json({ok:true,id:outcome.id,messages:outcome.messages},201);
  }
  if (request.method === "POST" && path === "/chat/settle") {
    let result; try {result=await request.json();} catch {return json({error:"chat_settlement_invalid"},400);}
    if (!result || Object.keys(result).sort().join(",")!=="id,reply"
        || !isUuid(result.id) || (result.reply !== null && !safeText(result.reply, MAX_REPLY))) {
      return json({error:"chat_settlement_invalid"},400);
    }
    const outcome = await storage.transaction(async txn => {
      let s; try {s=await state(txn,now);} catch{return {error:"chat_state_unavailable",code:503};}
      if (s.pending?.id !== result.id) return {error:"chat_settlement_not_pending",code:409};
      const user = s.entries.find(x => x.id === result.id && x.role==="user");
      if (!user || user.status !== "pending") return {error:"chat_settlement_conflict",code:409};
      user.status = result.reply === null ? "failed" : "complete";
      if (result.reply !== null) s.entries.push({
        id:result.id+":assistant",role:"assistant",content:result.reply.trim(),
        status:"complete",created_at:new Date(now).toISOString()
      });
      s.entries=s.entries.slice(-MAX_MESSAGES); s.pending=null;
      await txn.put("ai_lab_chat_v1",s);
      return {receipt:result.reply !== null ? "completed" : "failed"};
    });
    if (outcome.error) return json({error:outcome.error},outcome.code);
    try {
      const observed=await state(storage,now);
      const user=observed.entries.find(x=>x.id===result.id&&x.role==="user");
      if (observed.pending || !user ||
          user.status !== (outcome.receipt==="completed" ? "complete" : "failed") ||
          (outcome.receipt==="completed" && !observed.entries.some(x=>
            x.id===result.id+":assistant" && x.role==="assistant"))) {
        return json({error:"chat_settlement_readback_failed"},502);
      }
      return json({ok:true,status:outcome.receipt,durable_readback_verified:true},200);
    } catch {return json({error:"chat_settlement_readback_failed"},502);}
  }
  if (request.method === "DELETE" && path === "/chat/clear") {
    const outcome = await storage.transaction(async txn => {
      let s;try{s=await state(txn,now);}catch{return {error:"chat_state_unavailable",code:503};}
      if (s.pending) return {error:"chat_request_in_progress",code:409};
      s.entries=[];
      await txn.put("ai_lab_chat_v1",s);
      return {ok:true};
    });
    if (outcome.error) return json({error:outcome.error},outcome.code);
    try { const readback=await state(storage,now);
      if (readback.entries.length) return json({error:"chat_clear_readback_failed"},502);
      return json({ok:true,cleared:true,durable_readback_verified:true});
    } catch {return json({error:"chat_clear_readback_failed"},502);}
  }
  return json({error:"chat_route_not_supported"},404);
}

export async function callAiLabModel(binding, messages) {
  if (typeof binding?.fetch !== "function") throw Error("model_binding_unavailable");
  if (!Array.isArray(messages) || !messages.length || messages.length > 12 ||
      messages.at(-1)?.role !== "user" || !messages.every(x =>
        x && ["user","assistant"].includes(x.role) && safeText(x.content,x.role==="user"?MAX_USER:MAX_REPLY))) {
    throw Error("chat_context_invalid");
  }
  const request = new Request("https://cc-shared-nvidia-inference.invalid/internal/ai-lab/chat",{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({schema:"operator.ai_lab.inference.v1",messages})
  });
  const response = await binding.fetch(request);
  if (!response.ok) throw Error("model_provider_unavailable");
  const raw = await response.text();
  if (raw.length > 4800) throw Error("model_response_oversize");
  let parsed;try{parsed=JSON.parse(raw);}catch{throw Error("model_response_invalid");}
  if (!parsed || parsed.schema!=="operator.ai_lab.inference_result.v1" || parsed.model!==CHAT_MODEL
      || !safeText(parsed.reply,MAX_REPLY) || parsed.tools_executed!==false) throw Error("model_response_invalid");
  return parsed.reply.trim();
}
