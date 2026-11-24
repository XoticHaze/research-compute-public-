// Operator-side deterministic config renderer. Never reads/prints secret values.
// This file does not connect to Cloudflare or deploy anything.
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve, dirname, basename } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const source = resolve(root, "wrangler.jsonc");
const bindingName = "NVIDIA_API_KEY";

export function prepareBoundManifest(config, storeId) {
  if (!/^[0-9a-f]{32}$/i.test(String(storeId || ""))) {
    throw new Error("invalid_secrets_store_id");
  }
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    throw new Error("invalid_worker_manifest");
  }
  if (config.name !== "cc-shared-nvidia-inference"
      || config.workers_dev !== false
      || config.preview_urls !== false
      || config.vars?.CC_NVIDIA_DIAGNOSTIC_ENABLED !== "0") {
    throw new Error("private_worker_safety_gate_failed");
  }
  if (config.routes || config.route || config.triggers?.crons
      || config.secrets_store_secrets || config.services) {
    throw new Error("manifest_has_existing_or_unsafe_bindings");
  }
  return {
    ...config,
    secrets_store_secrets: [{
      binding: bindingName,
      store_id: storeId.toLowerCase(),
      secret_name: bindingName,
    }],
  };
}

export async function prepareFile(storeId, outputPath) {
  const original = JSON.parse(await readFile(source, "utf8"));
  const prepared = prepareBoundManifest(original, storeId);
  const target = resolve(outputPath);
  if (basename(target) !== "wrangler.bound.jsonc" || dirname(target) !== root) {
    throw new Error("binding_manifest_output_must_be_project_local");
  }
  await writeFile(target, JSON.stringify(prepared, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  return target;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const idAt = args.indexOf("--store-id");
  if (idAt < 0 || idAt + 1 >= args.length || args.length !== 2) {
    process.stderr.write("Usage: node scripts/render-secret-binding.mjs --store-id <Cloudflare Secrets Store ID>\n");
    process.exitCode = 2;
  } else {
    prepareFile(args[idAt+1], resolve(root, "wrangler.bound.jsonc"))
      .then(() => process.stdout.write("BINDING_MANIFEST=CREATED_PRIVATE_WORKER_ONLY\nLIVE_SECRET_BINDING=NOT_YET_DEPLOYED\n"))
      .catch(err => {
        const codes = new Set([
          "invalid_secrets_store_id", "invalid_worker_manifest",
          "private_worker_safety_gate_failed",
          "manifest_has_existing_or_unsafe_bindings",
          "binding_manifest_output_must_be_project_local",
        ]);
        const kind = codes.has(err.message) ? err.message : "manifest_generation_failed_or_output_exists";
        process.stderr.write("BINDING_MANIFEST=" + kind + "\n");
        process.exitCode = 1;
      });
  }
}
