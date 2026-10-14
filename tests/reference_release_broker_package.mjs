import fs from 'node:fs';

const index = fs.readFileSync('cloudflare/reference-release-broker/src/index.js', 'utf8');
const ticket = fs.readFileSync('cloudflare/reference-release-broker/src/ticket.js', 'utf8');
const intent = fs.readFileSync('cloudflare/reference-release-broker/src/intent.js', 'utf8');
const brokerSource = index + '\n' + ticket + '\n' + intent;
const wrangler = fs.readFileSync('cloudflare/reference-release-broker/wrangler.jsonc', 'utf8');
const deploy = fs.readFileSync('cloudflare/reference-release-broker/DEPLOYMENT_BOUNDARY.md', 'utf8');

for (const needle of [
  "verifyGithubOidc",
  "job_workflow_sha",
  "verifyAuthorityIntent",
  "callerPolicySha256",
  "GRANT_LEDGER",
  "BROKER_SIGNING_PRIVATE_JWK",
  "AUTHORITY_PUBLIC_B64",
  "intentWrapper",
  "signReleaseTicket",
  "grant_already_consumed",
]) {
  if (!brokerSource.includes(needle)) throw new Error('broker_contract_missing_' + needle);
}
// An independently signed intent may name a clean repository, but the
// broker must validate a verified JWT's immutable principal before deriving
// that policy hash or consuming a grant; a public ACK never satisfies it.
const validateIndex = index.indexOf('validateOidcCallerPolicy(claims, policy, now)');
const policyDigestIndex = index.indexOf('const policyDigest = await callerPolicySha256(claims)');
const grantConsumeIndex = index.indexOf("const consumeResponse = await stub.fetch");
if (validateIndex < 0 || policyDigestIndex <= validateIndex || grantConsumeIndex <= policyDigestIndex) {
  throw new Error('oidc_immutable_principal_validation_order_rejected');
}
if (!ticket.includes('function validateOidcCallerPolicy(claims, policy, nowSeconds)')) {
  throw new Error('oidc_strict_claim_validation_missing');
}
if (!wrangler.includes('"workers_dev": true')) throw new Error('neutral_workers_dev_endpoint_required');
if (!wrangler.includes('"preview_urls": false')) throw new Error('preview_urls_must_be_false');
if (!wrangler.includes('"keep_vars": false')) throw new Error('keep_vars_must_be_false');
if (!deploy.includes('not deployed by a GitHub Actions workflow')) throw new Error('independent_deploy_boundary_missing');
if (/CLOUDFLARE_API_TOKEN|github\.token|secrets\./.test(wrangler)) throw new Error('github_deploy_credential_reference_rejected');

console.log('REFERENCE_BROKER_PACKAGE_CONTRACT_PASS=1');
