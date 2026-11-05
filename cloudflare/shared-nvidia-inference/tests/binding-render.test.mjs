import test from "node:test";
import assert from "node:assert/strict";
import { prepareBoundManifest } from "../scripts/render-secret-binding.mjs";

const storeId = "abcdef0123456789abcdef0123456789";
function source() {
  return {
    name: "cc-shared-nvidia-inference",
    main: "src/index.js",
    compatibility_date: "2026-10-18",
    workers_dev: false,
    preview_urls: false,
    keep_vars: true,
    vars: { CC_NVIDIA_DIAGNOSTIC_ENABLED: "0" },
  };
}

test("emits only secret reference, never a key or public route", () => {
  const doc = prepareBoundManifest(source(), storeId.toUpperCase());
  assert.deepEqual(doc.secrets_store_secrets, [{
    binding: "NVIDIA_API_KEY",
    store_id: storeId,
    secret_name: "NVIDIA_API_KEY",
  }]);
  assert.equal(doc.workers_dev, false);
  assert.equal(doc.preview_urls, false);
  assert.equal(doc.vars.CC_NVIDIA_DIAGNOSTIC_ENABLED, "0");
  assert.equal(doc.routes, undefined);
  assert.equal(JSON.stringify(doc).includes("sk-"), false);
});

test("rejects missing or malformed store IDs", () => {
  for (const id of ["", "unknown", "abc", "foo" + storeId, storeId + "g"]) {
    assert.throws(() => prepareBoundManifest(source(), id),
      /invalid_secrets_store_id/);
  }
});

test("rejects changed worker name or public ingress", () => {
  const unsafe = [
    { name: "fleet-authority" },
    { workers_dev: true },
    { preview_urls: true },
    { vars: {CC_NVIDIA_DIAGNOSTIC_ENABLED: "1"} },
    { route: "*.example.com/*" },
    { routes: [{pattern:"*/*"}] },
    { services: [{binding:"TRADING", service:"fleet-authority"}] },
    { secrets_store_secrets: [] },
  ];
  for (const mutation of unsafe) {
    const candidate = { ...source(), ...mutation };
    assert.throws(() => prepareBoundManifest(candidate, storeId),
      /private_worker_safety_gate_failed|manifest_has_existing_or_unsafe_bindings/);
  }
});
