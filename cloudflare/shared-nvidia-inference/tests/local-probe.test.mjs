import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createCaller } from "../local-probe/src/index.js";

const url = "http://127.0.0.1:8787/run-once";
const call = (target = url, body) => new Request(target, { method: "POST", ...(body === undefined ? {} : { body }) });

test("local caller configuration is private and has only the intended remote service binding", async () => {
  const config = JSON.parse(await readFile(new URL("../local-probe/wrangler.jsonc", import.meta.url), "utf8"));
  assert.equal(config.name, "cc-shared-nvidia-operator-local-caller");
  assert.equal(config.workers_dev, false);
  assert.equal(config.preview_urls, false);
  assert.equal(config.routes, undefined);
  assert.equal(config.route, undefined);
  assert.equal(config.secrets_store_secrets, undefined);
  assert.equal(config.vars, undefined);
  assert.deepEqual(config.services, [{ binding: "NVIDIA_SERVICE", service: "cc-shared-nvidia-inference", remote: true }]);
});

test("local caller rejects wrong ingress and body without invoking the service", async () => {
  const caller = createCaller();
  let calls = 0;
  const env = { NVIDIA_SERVICE: { async fetch() { calls++; return new Response(); } } };
  assert.equal((await caller.fetch(call("http://example.com/run-once"), env)).status, 404);
  assert.equal((await caller.fetch(call("http://127.0.0.1:8787/run-once?model=anything"), env)).status, 404);
  assert.equal((await caller.fetch(call(url, "secret payload"), env)).status, 400);
  assert.equal(calls, 0);
});

test("a zero-byte POST stream is admissible but no request data is forwarded", async () => {
  const caller = createCaller();
  const received = [];
  const empty = new Request(url, {
    method: "POST",
    body: "",
    headers: { "content-length": "0" },
  });
  const env = { NVIDIA_SERVICE: { async fetch(request) {
    received.push({ url: request.url, method: request.method, body: request.body });
    return new Response(JSON.stringify({ error: "diagnostic_not_admitted" }), { status: 503 });
  } } };
  const reply = await caller.fetch(empty, env);
  assert.equal(reply.status, 502);
  assert.equal((await reply.json()).classification, "unexpected_upstream_receipt");
  assert.deepEqual(received, [{
    url: "https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia",
    method: "POST", body: null,
  }]);
  assert.equal((await caller.fetch(call(), env)).status, 409);
});

test("missing service binding fails closed and does not consume one-shot slot", async () => {
  const caller = createCaller();
  assert.equal((await caller.fetch(call(), {})).status, 503);
  const env = { NVIDIA_SERVICE: { async fetch() { return new Response(JSON.stringify({
    schema: "commandcenter.shared_nvidia_private_diagnostic.v1",
    classification: "completion_http_200", calls_made: 2,
  }), { status: 200 }); } } };
  assert.equal((await caller.fetch(call(), env)).status, 200);
});

test("one bound call only, fixed private destination, unexpected fields dropped", async () => {
  const caller = createCaller();
  const called = [];
  const env = { NVIDIA_SERVICE: { async fetch(request) {
    called.push({ url: request.url, method: request.method, body: request.body });
    return new Response(JSON.stringify({
      schema: "commandcenter.shared_nvidia_private_diagnostic.v1",
      catalog_http_status: 200, completion_http_status: 403,
      catalog_includes_model: true, catalog_count: 20,
      completion_response_valid: false, exact_reply_observed: false,
      elapsed_ms: 102, calls_made: 2, classification: "provider_access_rejected",
      API_KEY: "DO_NOT_EXPOSE", raw_provider_body: "DO_NOT_EXPOSE",
    }), { status: 503 });
  } } };
  const response = await caller.fetch(call(), env);
  assert.equal(response.status, 502);
  const content = await response.text();
  assert.equal(content.includes("DO_NOT_EXPOSE"), false);
  const receipt = JSON.parse(content);
  assert.equal(receipt.completion_http_status, 403);
  assert.equal(receipt.classification, "provider_access_rejected");
  assert.deepEqual(called, [{
    url: "https://cc-shared-nvidia-inference.invalid/internal/diagnostics/nvidia",
    method: "POST", body: null,
  }]);
  assert.equal((await caller.fetch(call(), env)).status, 409);
  assert.equal(called.length, 1);
});
