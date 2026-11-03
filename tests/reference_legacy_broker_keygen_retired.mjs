import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const root = path.resolve(import.meta.dirname, '..');
const retiredPowerShell = fs.readFileSync(
  path.join(root, 'scripts/operator/bootstrap_reference_release_broker.ps1'),
  'utf8'
);
const activeStatements = retiredPowerShell.split(/\r?\n/)
  .map(line => line.trim())
  .filter(line => line.length && !line.startsWith('#'));
// This retired shell entrypoint must not gain any executable pre-throw
// deployment, keygen, network or secret mutation statements in a future edit.
assert.deepEqual(activeStatements, [
  'param([string]$KeyDir = "")',
  '$ErrorActionPreference = "Stop"',
  'throw "RETIRED_UNSAFE_BOOTSTRAP: no key generation or Cloudflare action. Read the neutral initial-seal handoff and obtain independent administrator approval."'
]);
console.log('REFERENCE_LEGACY_POWERSHELL_BOOTSTRAP_RETIRED_PASS=1');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'legacy-broker-keygen-retired-'));
try {
  const marker = path.join(tmp, 'existing-key-sentinel');
  fs.writeFileSync(marker, 'preserve existing identity\n', { mode: 0o600 });
  const before = fs.readFileSync(marker);
  const result = spawnSync(process.execPath, [
    path.join(root, 'scripts/operator/reference_broker_keygen.mjs'), tmp
  ], { cwd: root, encoding: 'utf8' });
  assert.notEqual(result.status, 0, 'retired helper must never generate keys');
  assert.match(result.stderr, /RETIRED_UNSAFE_KEYGEN/);
  assert.equal(result.stdout, '');
  assert.deepEqual(fs.readFileSync(marker), before);
  assert.deepEqual(fs.readdirSync(tmp), ['existing-key-sentinel']);
  console.log('REFERENCE_LEGACY_KEYGEN_RETIREMENT_PASS=1');
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
