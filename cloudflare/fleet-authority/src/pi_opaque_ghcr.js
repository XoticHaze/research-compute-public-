// GHCR image-only source selection from the existing private MM repository.
// Trigger, public GitHub logs and public artifacts contain no private source SHA.
export const PI_GHCR_OPAQUE_PUBLISH_IDENTITY = Object.freeze({
  repository: 'XoticHaze/mm-ibkr-runtime',
  ref: 'refs/heads/main',
  workflow_ref:
    'XoticHaze/mm-ibkr-runtime/.github/workflows/mmibkr-ghcr-opaque-publish-r1.yml@refs/heads/main',
});

const PRIVATE_REPO = 'XoticHaze/mm-IBKR';
const CANDIDATE = 'deploy/pi-bot/ghcr_release_candidate_current.v1.json';
const SUITES = Object.freeze([
  'test_pi_root_external_baseline_owner_epoch_20261106',
  'test_pi_canonical_live_fill_commit_bridge_20261106',
  'test_pi_canonical_pending_live_fill_recovery_20261106',
  'test_pi_canonical_account_margin_cap_bridge_20261106',
  'test_pi_canonical_margin_call_binding_20261106',
  'test_selected_runtime_live_execution_ledger_v1',
]);

export async function resolvePiImageCandidate(env, {
  fetchImpl = fetch, nowMs = Date.now(),
} = {}) {
  const token = String(env.MMIBKR_PRIVATE_SOURCE_TOKEN || '');
  if (!token || token.length > 512 || /[\r\n\0]/.test(token)) {
    throw new Error('private_pi_candidate_credential_missing');
  }
  const base = 'https://api.github.com/repos/' + PRIVATE_REPO;
  const get = async (path) => {
    let response;
    try {
      response = await fetchImpl(base + path, {
        method: 'GET',
        headers: {
          Accept: 'application/vnd.github+json',
          Authorization: 'Bearer ' + token,
          'User-Agent': 'mmibkr-pi-opaque-ghcr-publisher-r1',
        },
      });
    } catch {
      throw new Error('private_pi_candidate_github_unavailable');
    }
    if (!response.ok) throw new Error('private_pi_candidate_github_denied');
    return response.json();
  };
  const file = await get('/contents/' + CANDIDATE + '?ref=main');
  if (file.encoding !== 'base64' || typeof file.content !== 'string'
      || file.content.length > 32768) {
    throw new Error('private_pi_candidate_file_invalid');
  }
  let doc;
  try {
    doc = JSON.parse(atob(file.content.replace(/\s/g, '')));
  } catch {
    throw new Error('private_pi_candidate_json_invalid');
  }
  const sha = doc && doc.source_sha;
  const branch = doc && doc.source_branch_at_review;
  const expiry = Date.parse(doc && doc.release_expiry_utc);
  if (!doc || doc.schema !== 'mmibkr.pi_ghcr_release_candidate.v1'
      || doc.approval_level !== 'GHCR_PRIVATE_IMAGE_BUILD_AND_PUBLISH_ONLY_NOT_RUNTIME_OR_BROKER_APPROVAL'
      || doc.source_repository !== PRIVATE_REPO
      || !/^[a-f0-9]{40}$/.test(String(sha || ''))
      || doc.source_branch_head_at_review !== sha
      || typeof branch !== 'string' || !/^release\/pi-bot-[a-z0-9-]+$/.test(branch)
      || doc.require_exact_commit_sha !== true
      || doc.target_registry !== 'ghcr.io/xotichaze/mmibkr-pi-canonical-private-20261030'
      || doc.target_visibility !== 'private' || doc.platform !== 'linux/arm64'
      || doc.dockerfile !== 'deploy/pi-bot/Dockerfile'
      || doc.approval_not_sufficient_for_live !== true
      || !Array.isArray(doc.native_brokerless_suites)
      || doc.native_brokerless_suites.length !== SUITES.length
      || !SUITES.every((suite, i) => doc.native_brokerless_suites[i] === suite)
      || !Number.isFinite(expiry) || expiry <= nowMs) {
    throw new Error('private_pi_candidate_policy_invalid');
  }
  const ref = await get('/git/ref/heads/' + branch);
  if (!ref || !ref.object || ref.object.sha !== sha) {
    throw new Error('private_pi_candidate_branch_drift');
  }
  return { source_sha: sha, native_brokerless_suites: [...SUITES],
    image_only: true, broker_authorized: false };
}
