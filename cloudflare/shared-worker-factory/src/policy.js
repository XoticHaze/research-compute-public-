// Shared Compute Worker Factory: bounded request contract. No credentials.
export const SCHEMA = 'commandcenter.cloudflare.factory_request.v1';
export const OPERATIONS = Object.freeze(['ordinary_worker.create', 'existing_worker.editor_token.issue', 'existing_worker.inspect']);
const NAME = /^[a-z][a-z0-9-]{5,57}[a-z0-9]$/;
const HEX32 = /^[a-f0-9]{32}$/;
const RESERVED = [
  'reference-release-', 'reference-maintenance-', 'ccpi-owner-',
  'shared-compute-worker-factory', 'shared-compute-neutral-', 'fleet-authority',
  'mmibkr-operator-console', 'cc-shared-nvidia-inference',
];
export function isOrdinaryWorker(name) {
  return typeof name === 'string' && NAME.test(name)
    && !name.includes('--')
    && !RESERVED.some(p => name === p || name.startsWith(p));
}
export function validateRequest(req, now = Math.floor(Date.now() / 1000)) {
  if (!req || typeof req !== 'object' || Array.isArray(req))
    throw Error('bad_request');
  const base = ['schema', 'operation', 'request_id', 'worker_name', 'expires_at'];
  const extra = req.operation === 'existing_worker.editor_token.issue'
    ? ['worker_id', 'token_ttl_hours']
    : req.operation === 'existing_worker.inspect' ? ['worker_id'] : [];
  const expected = [...base, ...extra].sort();
  if (Object.keys(req).sort().join(',') !== expected.join(',')
      || req.schema !== SCHEMA || !OPERATIONS.includes(req.operation)
      || !HEX32.test(req.request_id) || !isOrdinaryWorker(req.worker_name))
    throw Error('request_contract_rejected');
  if (!Number.isInteger(req.expires_at) || req.expires_at < now
      || req.expires_at > now + 300) throw Error('request_expiry_rejected');
  if (req.operation === 'existing_worker.editor_token.issue'
      && (!HEX32.test(req.worker_id) || !Number.isInteger(req.token_ttl_hours)
      || req.token_ttl_hours < 1 || req.token_ttl_hours > 168))
    throw Error('scoped_token_contract_rejected');
  if (req.operation === 'existing_worker.inspect' && !HEX32.test(req.worker_id))
    throw Error('worker_identity_rejected');
  return req;
}
export function workerEditorPolicy(account, workerId) {
  if (!HEX32.test(account) || !HEX32.test(workerId))
    throw Error('resource_scope_rejected');
  // Individual Worker Editor, never Workers product Admin or token-admin.
  return [{
    effect: 'allow',
    permission_groups: [{ id: '7e79ec33834341f28dd431ab73884400' }],
    resources: {
      ['com.cloudflare.api.account.' + account]: {
        ['com.cloudflare.edge.worker.script.' + workerId]: '*',
      },
    },
  }];
}
