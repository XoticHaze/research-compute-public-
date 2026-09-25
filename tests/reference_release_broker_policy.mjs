import fs from 'node:fs';
import {
  validateClaims,
  generateSigningKeypair,
  signReleaseTicket,
} from '../cloudflare/reference-release-broker/src/ticket.js';

const now = 100000;
const harnessSha = '155e3120494ddb0f81b88cb901c3dffc96e687f7';
const policy = {
  audience: 'secure-compute-reference-v1',
  repository_id: '1358005162',
  repository_owner_id: '152584286',
  job_workflow_ref: 'XoticHaze/research-compute-public-/.github/workflows/secure-compute-harness-v1.yml@155e3120494ddb0f81b88cb901c3dffc96e687f7',
  job_workflow_sha: harnessSha,
  max_admission_seconds: 900,
};
const grant = {
  grant_id: 'grant_0123456789abcdef',
  run_id: '36177988341',
  run_attempt: '1',
  harness_sha: harnessSha,
  worker_key_id: 'sha256:' + '2'.repeat(64),
  admission_not_after: now + 300,
};
const claims = {
  iss: 'https://token.actions.githubusercontent.com',
  aud: 'secure-compute-reference-v1',
  repository_id: policy.repository_id,
  repository_owner_id: policy.repository_owner_id,
  job_workflow_ref: policy.job_workflow_ref,
  job_workflow_sha: policy.job_workflow_sha,
  run_id: grant.run_id,
  run_attempt: grant.run_attempt,
  runner_environment: 'github-hosted',
  iat: now - 10,
  nbf: now - 10,
  exp: now + 300,
};

validateClaims(claims, policy, grant, now);

for (const mutate of [
  c => { c.job_workflow_sha = '9'.repeat(40); },
  c => { c.repository_id = '999'; },
  c => { c.repository_owner_id = '999'; },
  c => { c.run_id = '99999'; },
  c => { c.exp = now - 31; },
]) {
  const bad = structuredClone(claims);
  mutate(bad);
  let rejected = false;
  try { validateClaims(bad, policy, grant, now); } catch { rejected = true; }
  if (!rejected) throw new Error('negative_oidc_case_not_rejected');
}

const longGrant = structuredClone(grant);
longGrant.admission_not_after = now + 5 * 60 * 60;
let longRejected = false;
try { validateClaims(claims, policy, longGrant, now); } catch { longRejected = true; }
if (!longRejected) throw new Error('five_hour_admission_ticket_not_rejected');

const signer = await generateSigningKeypair();
const wrapper = await signReleaseTicket(signer.privateKey, signer.keyId, grant, now);

fs.writeFileSync('reference-release-ticket.json', JSON.stringify(wrapper) + '\n');
fs.writeFileSync('reference-release-signer-public.txt', signer.publicB64 + '\n');
fs.writeFileSync('reference-release-expected.json', JSON.stringify({
  grant_id: grant.grant_id,
  run_id: grant.run_id,
  run_attempt: grant.run_attempt,
  harness_sha: grant.harness_sha,
  worker_key_id: grant.worker_key_id,
  now: now + 1,
}) + '\n');
console.log('REFERENCE_RELEASE_BROKER_POLICY_PASS=1');
