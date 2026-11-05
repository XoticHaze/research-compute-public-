// Authenticated, isolated AI Lab session substrate. This module has no model,
// public-compute, GitHub, broker, device, or privileged execution capability.
export const AI_LAB_SCHEMA = "operator.ai_lab.session.v1";
export const AI_LAB_MAX_NOTES = 40;
const MAX_TEXT = 1200;

function reply(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

export function validateLabNote(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)
      || Object.keys(body).sort().join(",") !== "id,schema,text"
      || body.schema !== AI_LAB_SCHEMA) throw new Error("lab_note_schema_rejected");
  if (typeof body.id !== "string"
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(body.id)) {
    throw new Error("lab_note_id_rejected");
  }
  if (typeof body.text !== "string"
      || !body.text.trim()
      || body.text.length > MAX_TEXT
      || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(body.text)) {
    throw new Error("lab_note_text_rejected");
  }
  return { id: body.id, text: body.text.trim(), created_at: new Date().toISOString() };
}

function validRecords(rows) {
  if (!Array.isArray(rows) || rows.length > AI_LAB_MAX_NOTES) return false;
  return rows.every(row => row && typeof row.id === "string"
    && typeof row.text === "string" && row.text.length <= MAX_TEXT
    && typeof row.created_at === "string");
}

export async function labStateFetch(request, storage) {
  const { pathname } = new URL(request.url);
  if (request.method === "GET" && pathname === "/lab/latest") {
    const rows = (await storage.get("lab_notes_v1")) || [];
    if (!validRecords(rows)) return reply({ error: "lab_state_invalid" }, 503);
    return reply({ ok: true, schema: AI_LAB_SCHEMA, model_status: "NOT_CONNECTED",
      storage: "per_operator_durable_object", notes: rows });
  }
  if (request.method === "POST" && pathname === "/lab/append") {
    let note;
    try { note = validateLabNote(await request.json()); }
    catch { return reply({ error: "lab_note_rejected" }, 400); }
    const saved = await storage.transaction(async txn => {
      const before = (await txn.get("lab_notes_v1")) || [];
      if (!validRecords(before)) return { invalid: true };
      const already = before.find(row => row.id === note.id);
      if (already) return { note: already, repeated: true };
      const after = [...before, note].slice(-AI_LAB_MAX_NOTES);
      await txn.put("lab_notes_v1", after);
      return { note, repeated: false };
    });
    if (saved.invalid) return reply({ error: "lab_state_invalid" }, 503);
    const rows = (await storage.get("lab_notes_v1")) || [];
    if (!validRecords(rows) || !rows.some(row => row.id === saved.note.id)) {
      return reply({ error: "lab_readback_failed" }, 502);
    }
    return reply({ ok: true, schema: AI_LAB_SCHEMA, note: saved.note,
      durable_readback_verified: true, repeated: saved.repeated }, saved.repeated ? 200 : 201);
  }
  if (request.method === "DELETE" && pathname === "/lab/clear") {
    await storage.delete("lab_notes_v1");
    if ((await storage.get("lab_notes_v1")) !== undefined) {
      return reply({ error: "lab_clear_readback_failed" }, 502);
    }
    return reply({ ok: true, schema: AI_LAB_SCHEMA, notes_cleared: true });
  }
  return reply({ error: "not_found" }, 404);
}

// A separate operator identity creates a distinct Durable Object instance.
// The hash is a partition key, not a signed authorization token.
export async function aiLabStub(env, accessIdentity) {
  if (!env.OPERATOR_STATE) throw new Error("operator_state_binding_missing");
  const identity = String(accessIdentity?.email || "") + "\u0000"
    + String(accessIdentity?.sub || "");
  if (!accessIdentity?.email || !accessIdentity?.sub) {
    throw new Error("operator_identity_incomplete");
  }
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(identity));
  const partition = Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, "0")).join("");
  return env.OPERATOR_STATE.get(env.OPERATOR_STATE.idFromName("ai-lab/v1/" + partition));
}

const HTML = [
  "<!doctype html>",
  "<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
  "<title>AI Lab | Operator Console</title>",
  "<style>body{margin:0;background:#0b1020;color:#e8edf5;font:16px system-ui,sans-serif}",
  "main{max-width:760px;margin:3rem auto;padding:1rem}a{color:#93c5fd}",
  "section{border:1px solid #334155;border-radius:14px;padding:1.2rem;margin:1rem 0;background:#121a2a}",
  "textarea{box-sizing:border-box;width:100%;min-height:110px;padding:.75rem;background:#070c18;color:#fff;border:1px solid #64748b;border-radius:8px}",
  "button{padding:.65rem 1rem;margin:.5rem .5rem .5rem 0;border:1px solid #64748b;border-radius:8px;background:#273449;color:#fff;cursor:pointer}",
  "button:disabled{opacity:.5}li{white-space:pre-wrap;overflow-wrap:anywhere;margin:1rem 0}",
  ".muted{color:#a4b3c7}.error{color:#ffb4ae}</style></head><body><main>",
  "<nav><a href='/bot-console'>Operator Console</a></nav><h1>AI Lab</h1>",
  "<p class='muted'>Isolated Access-locked session preview. NVIDIA inference is NOT CONNECTED. No code, device or broker tools.</p>",
  "<section><h2>Session notes</h2><p class='muted'>Only store fictional test notes here during the pilot. These notes stay in an operator-partitioned Cloudflare Durable Object and are not sent to NVIDIA or GitHub.</p>",
  "<form id='lab-form'><label for='note'>Test note</label><textarea id='note' maxlength='1200' required></textarea>",
  "<div><button type='submit'>Save note</button><button type='button' id='refresh'>Refresh</button>",
  "<button type='button' id='clear'>Clear all notes</button></div></form>",
  "<p id='status' role='status' aria-live='polite'></p></section>",
  "<section><h2>Saved history</h2><ol id='history'></ol></section>",
  "<p class='muted'>Model chat, scheduling, tools and private-input compute require separate admission. This preview does not simulate model replies.</p>",
  "<script src='/ai-lab/client.js' defer></script></main></body></html>",
].join("\n");

const CLIENT = [
  "'use strict';",
  "const statusNode = document.getElementById('status');",
  "const historyNode = document.getElementById('history');",
  "const noteNode = document.getElementById('note');",
  "async function request(path, options) {",
  "  const response = await fetch(path, Object.assign({ credentials: 'same-origin', cache: 'no-store' }, options || {}));",
  "  const body = await response.json();",
  "  if (!response.ok) throw new Error(body.error || 'request_failed');",
  "  return body;",
  "}",
  "async function refresh() {",
  "  const data = await request('/api/ai-lab/session');",
  "  historyNode.replaceChildren();",
  "  for (const note of data.notes) {",
  "    const li = document.createElement('li');",
  "    li.textContent = note.text;",
  "    historyNode.appendChild(li);",
  "  }",
  "  statusNode.textContent = 'Saved notes: ' + data.notes.length + '. Model: not connected.';",
  "}",
  "document.getElementById('lab-form').addEventListener('submit', async e => {",
  "  e.preventDefault();",
  "  const text = noteNode.value;",
  "  try {",
  "    await request('/api/ai-lab/note', { method: 'POST', headers: {'content-type':'application/json'},",
  "      body: JSON.stringify({ schema: 'operator.ai_lab.session.v1', id: crypto.randomUUID(), text }) });",
  "    noteNode.value = '';",
  "    await refresh();",
  "  } catch (err) { statusNode.textContent = 'Save failed: ' + err.message; statusNode.className = 'error'; }",
  "});",
  "document.getElementById('refresh').addEventListener('click', () => refresh().catch(err => statusNode.textContent = err.message));",
  "document.getElementById('clear').addEventListener('click', async () => {",
  "  if (!confirm('Delete all notes in this isolated AI Lab session?')) return;",
  "  try { await request('/api/ai-lab/session', { method: 'DELETE', headers: {'content-type':'application/json'}, body: '{}' }); await refresh(); }",
  "  catch (err) { statusNode.textContent = 'Clear failed: ' + err.message; }",
  "});",
  "refresh().catch(err => { statusNode.textContent = 'Load failed: ' + err.message; statusNode.className = 'error'; });",
].join("\n");

export function aiLabAsset(pathname) {
  const isPage = pathname === "/ai-lab";
  if (!isPage && pathname !== "/ai-lab/client.js") return null;
  const headers = {
    "content-type": isPage ? "text/html; charset=utf-8" : "application/javascript; charset=utf-8",
    "cache-control": "private, no-store",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  };
  return new Response(isPage ? HTML : CLIENT, { status: 200, headers });
}
