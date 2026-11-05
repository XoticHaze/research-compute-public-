import test from "node:test";
import assert from "node:assert/strict";
import worker, { probeNvidia } from "../src/index.js";

const SECRET = "PRIVATE_SECRET_SHOULD_NOT_BE_EXPORTED";
const binding = { NVIDIA_API_KEY: { async get() { return SECRET; } } };

test("missing Secrets Store binding fails closed without network", async () => {
  const receipt = await probeNvidia({}, () => { throw new Error("should not call"); });
  assert.equal(receipt.classification, "secrets_store_binding_missing");
  assert.equal(receipt.calls_made, 0);
});

test("public/default handler cannot execute until explicit admission", async () => {
  const response = await worker.fetch(
    new Request("https://internal.invalid/internal/diagnostics/nvidia", { method: "POST" }),
    binding,
  );
  assert.equal(response.status, 503);
  assert.equal((await response.json()).error, "diagnostic_not_admitted");
});

test("input paths and arbitrary model requests are rejected", async () => {
  const env = { ...binding, CC_NVIDIA_DIAGNOSTIC_ENABLED: "1" };
  const response = await worker.fetch(
    new Request("https://internal.invalid/internal/diagnostics/nvidia?model=SECRET", { method: "POST" }),
    env,
  );
  assert.equal(response.status, 404);
});

test("provider catalog 200 but chat 403 is classified privately", async () => {
  const calls = [];
  const requester = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/models")) {
      return { ok: true, status: 200,
        async json() { return { data: [{ id: "openai/gpt-oss-20b" }] }; } };
    }
    return { ok: false, status: 403,
      async json() { throw new Error("must not read provider denial body"); } };
  };
  const receipt = await probeNvidia(binding, requester);
  assert.equal(receipt.catalog_http_status, 200);
  assert.equal(receipt.catalog_includes_model, true);
  assert.equal(receipt.completion_http_status, 403);
  assert.equal(receipt.classification, "provider_access_rejected");
  assert.equal(receipt.calls_made, 2);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].options.redirect, "manual");
  assert.equal(calls[1].options.redirect, "manual");
  assert.equal(calls[1].url, "https://integrate.api.nvidia.com/v1/chat/completions");
  assert.equal(JSON.parse(calls[1].options.body).model, "openai/gpt-oss-20b");
  assert.equal(JSON.stringify(receipt).includes(SECRET), false);
});

test("one successful synthetic completion is recognized without exposing text", async () => {
  const requester = async (url) => url.endsWith("/models")
    ? { ok: true, status: 200, async json() { return { data: [{id:"openai/gpt-oss-20b"}] }; } }
    : { ok: true, status: 200, async json() { return {
      choices: [{ message: { content:"PING_OK" } }], marker:SECRET,
    }; } };
  const receipt = await probeNvidia(binding, requester);
  assert.equal(receipt.classification, "completion_http_200");
  assert.equal(receipt.completion_response_valid, true);
  assert.equal(receipt.exact_reply_observed, true);
  assert.equal(JSON.stringify(receipt).includes(SECRET), false);
});

test("transport failure gets fixed safe category without exporting exception data", async () => {
  const leak = "Bearer PRIVATE_SECRET_SHOULD_NOT_BE_EXPORTED";
  const receipt = await probeNvidia(binding, async () => {
    throw new TypeError("fetch failed " + leak);
  });
  assert.equal(receipt.catalog_attempt_started, true);
  assert.equal(receipt.catalog_failure_stage, "outbound_fetch");
  assert.equal(receipt.catalog_failure_kind, "fetch_type_error");
  assert.equal(receipt.calls_made, 0);
  assert.equal(receipt.classification, "catalog_transport_or_response_failure");
  assert.equal(JSON.stringify(receipt).includes(leak), false);
});

test("JSON decode failure is distinguished from outbound transport failure", async () => {
  const receipt = await probeNvidia(binding, async () => ({
    ok: true, status: 200, async json() { throw new SyntaxError("PRIVATE_SECRET_SHOULD_NOT_BE_EXPORTED"); }
  }));
  assert.equal(receipt.catalog_attempt_started, true);
  assert.equal(receipt.catalog_http_status, 200);
  assert.equal(receipt.calls_made, 1);
  assert.equal(receipt.catalog_failure_stage, "catalog_json");
  assert.equal(receipt.catalog_failure_kind, "other_runtime_exception");
  assert.equal(JSON.stringify(receipt).includes(SECRET), false);
});

test("HTTP 200 without usable completion content is not an inference success", async () => {
  for (const content of [undefined, "", "   ", null]) {
    const requester = async (url) => url.endsWith("/models")
      ? { ok: true, status: 200, async json() { return { data: [] }; } }
      : { ok: true, status: 200, async json() {
        return { choices: [{ message: { content } }] };
      } };
    const receipt = await probeNvidia(binding, requester);
    assert.equal(receipt.completion_http_status, 200);
    assert.equal(receipt.completion_response_valid, false);
    assert.equal(receipt.exact_reply_observed, false);
    assert.equal(receipt.classification, "completion_response_invalid");
    assert.equal(receipt.calls_made, 2);
    assert.equal(JSON.stringify(receipt).includes(SECRET), false);
  }
});
