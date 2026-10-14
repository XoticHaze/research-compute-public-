import fs from 'node:fs';
import {
  callerIdentitySha256,
  callerPolicySha256,
  validateOidcCallerPolicy,
  validateClaims,
  generateSigningKeypair,
  signReleaseTicket,
} from '../cloudflare/reference-release-broker/src/ticket.js';

const now = 100000;
const harnessSha = '155e3120494ddb0f81b88cb901c3dffc96e687f7';
const policy = {
  audience: 'secure-compute-reference-v1',
  job_workflow_ref: 'XoticHaze/research-compute-public-/.github/workflows/secure-compute-harness-v1.yml@155e3120494ddb0f81b88cb901c3dffc96e687f7',
  job_workflow_sha: harnessSha,
  max_admission_seconds: 900,
};
const grant = {
  grant_id: 'grant_0123456789abcdef',
  run_id: '36177988341',
  run_attempt: '1',
  harness_sha: harnessSha,
  identity_sha256: '',
  worker_key_id: 'sha256:' + '2'.repeat(64),
  admission_not_after: now + 300,
};
const claims = {
  iss: 'https://token.actions.githubusercontent.com',
  aud: 'secure-compute-reference-v1',
  repository_id: '1358005162',
  repository_owner_id: '152584286',
  repository_visibility: 'public',
  ref: 'refs/heads/main',
  event_name: 'push',
  job_workflow_ref: policy.job_workflow_ref,
  job_workflow_sha: policy.job_workflow_sha,
  run_id: grant.run_id,
  run_attempt: grant.run_attempt,
  runner_environment: 'github-hosted',
  iat: now - 10,
  nbf: now - 10,
  exp: now + 300,
};
grant.identity_sha256 = await callerIdentitySha256(claims);

await validateClaims(claims, policy, grant, now);

await validateOidcCallerPolicy(claims, policy, now);

// Immutable repository identity is signed into the independently provisioned
// caller policy, not derived from mutable names or synthetic job success.
const cleanClaims = {
  ...claims,
  repository_id: '1416551057',
  run_id: '38371793948',
  run_attempt: '1',
  event_name: 'workflow_dispatch',
};
await validateOidcCallerPolicy(cleanClaims, policy, now);
const legacyPolicyHash = await callerPolicySha256(claims);
const cleanPolicyHash = await callerPolicySha256(cleanClaims);
if (legacyPolicyHash === cleanPolicyHash) {
  throw new Error('clean_repo_id_not_bound_to_caller_policy');
}
const cleanGrant = {
  ...grant,
  run_id: cleanClaims.run_id,
  run_attempt: cleanClaims.run_attempt,
  identity_sha256: await callerIdentitySha256(cleanClaims),
};
await validateClaims(cleanClaims, policy, cleanGrant, now);
let crossRepoRejected = false;
try { await validateClaims(claims, policy, cleanGrant, now); }
catch { crossRepoRejected = true; }
if (!crossRepoRejected) throw new Error('old_repository_replayed_clean_grant');

for (const [label, mutate] of [
  ['missing_immutable_repository_id', c => { delete c.repository_id; }],
  ['missing_owner_id', c => { delete c.repository_owner_id; }],
  ['non_decimal_immutable_id', c => { c.repository_id = '1A16551057'; }],
  ['zero_repository_id', c => { c.repository_id = '0'; }],
  ['negative_owner_id', c => { c.repository_owner_id = '-1'; }],
  ['private_visibility', c => { c.repository_visibility = 'private'; }],
  ['untrusted_pull_ref', c => { c.ref = 'refs/pull/1/merge'; }],
  ['invalid_event_name', c => { c.event_name = 'a/b'; }],
  ['empty_run_id', c => { c.run_id = ''; }],
  ['zero_attempt', c => { c.run_attempt = '0'; }],
  ['wrong_harness_sha', c => { c.job_workflow_sha = '0'.repeat(40); }],
  ['wrong_reusable_harness', c => { c.job_workflow_ref = 'XoticHaze/fake/.github/workflows/f.yml@' + harnessSha; }],
  ['unexpected_local_runner', c => { c.runner_environment = 'self-hosted'; }],
  ['claim_iat_not_integer', c => { c.iat = String(now - 10); }],
  ['inverted_expiry', c => { c.exp = c.iat; }],
  ['future_nbf', c => { c.nbf = now + 90; }],
  ['stale_exp', c => { c.exp = now - 31; }],
]) {
  const modified = structuredClone(cleanClaims);
  mutate(modified);
  let rejected = false;
  try { await validateOidcCallerPolicy(modified, policy, now); }
  catch { rejected = true; }
  if (!rejected) throw new Error('invalid_caller_accepted_' + label);
}
console.log('REFERENCE_CLEAN_IMMUTABLE_OIDC_PRINCIPAL_NEGATIVES_PASS=17');


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
  try { await validateClaims(bad, policy, grant, now); } catch { rejected = true; }
  if (!rejected) throw new Error('negative_oidc_case_not_rejected');
}

const longGrant = structuredClone(grant);
longGrant.admission_not_after = now + 5 * 60 * 60;
let longRejected = false;
try { await validateClaims(claims, policy, longGrant, now); } catch { longRejected = true; }
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
