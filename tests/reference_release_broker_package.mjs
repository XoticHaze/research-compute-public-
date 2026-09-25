import fs from 'node:fs';

const index = fs.readFileSync('cloudflare/reference-release-broker/src/index.js', 'utf8');
const ticket = fs.readFileSync('cloudflare/reference-release-broker/src/ticket.js', 'utf8');
const grant = fs.readFileSync('cloudflare/reference-release-broker/src/grant.js', 'utf8');
const brokerSource = index + '\n' + ticket + '\n' + grant;
const wrangler = fs.readFileSync('cloudflare/reference-release-broker/wrangler.jsonc', 'utf8');
const deploy = fs.readFileSync('cloudflare/reference-release-broker/DEPLOYMENT_BOUNDARY.md', 'utf8');

for (const needle of [
  "verifyGithubOidc",
  "job_workflow_sha",
  "verifyAuthorityGrant",
  "grant_identity_rejected",
  "GRANT_LEDGER",
  "BROKER_SIGNING_PRIVATE_JWK",
  "AUTHORITY_PUBLIC_B64",
  "signReleaseTicket",
  "grant_already_consumed",
]) {
  if (!brokerSource.includes(needle)) throw new Error('broker_contract_missing_' + needle);
}
if (!wrangler.includes('"workers_dev": false')) throw new Error('workers_dev_must_be_false');
if (!wrangler.includes('"preview_urls": false')) throw new Error('preview_urls_must_be_false');
if (!wrangler.includes('"keep_vars": false')) throw new Error('keep_vars_must_be_false');
if (!deploy.includes('not deployed by a GitHub Actions workflow')) throw new Error('independent_deploy_boundary_missing');
if (/CLOUDFLARE_API_TOKEN|github\.token|secrets\./.test(wrangler)) throw new Error('github_deploy_credential_reference_rejected');

console.log('REFERENCE_BROKER_PACKAGE_CONTRACT_PASS=1');
