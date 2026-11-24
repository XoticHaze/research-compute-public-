// Independently administered neutral Worker permit. Git proposals cannot mint it.
const SHA = /^[0-9a-f]{40}$/;
const GEN = /^r[0-9a-f]{12}$/;
const ID = /^[0-9a-f]{32}$/;
const RID = /^ccpi2-([0-9a-f]{64})-[0-9a-f]{16}$/;
const UTC = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/;
const FIELDS = ['schema','permit_id','request_id','manifest_sha256','source_sha','expected_release','not_before','expires_at'];
export function scheduledRootPermit(env, request, now = Date.now()) {
  if (env.PI_OWNER_SCHEDULED_ROOT_ENABLED !== '1'
      || env.PI_OWNER_SIGNER_ENABLED !== '1'
      || env.PI_OWNER_NORMAL_RELEASE_ENABLED !== '1') throw Error('scheduled_root_not_admitted');
  const raw=env.PI_OWNER_SCHEDULED_ROOT_PERMIT;
  if(typeof raw!=='string'||raw.length>1024) throw Error('scheduled_root_permit_missing');
  const p=JSON.parse(raw);
  if(!p||Array.isArray(p)||Object.keys(p).length!==FIELDS.length
      ||!FIELDS.every(k=>Object.hasOwn(p,k))
      ||p.schema!=='commandcenter.pi.scheduled_root_permit.v2'
      ||!RID.test(p.request_id)||RID.exec(p.request_id)[1]!==p.manifest_sha256
      ||!ID.test(p.permit_id)||!SHA.test(p.source_sha)||!GEN.test(p.expected_release)
      ||!UTC.test(p.not_before)||!UTC.test(p.expires_at)) throw Error('scheduled_root_permit_invalid');
  const start=Date.parse(p.not_before), end=Date.parse(p.expires_at);
  if(!Number.isFinite(start)||!Number.isFinite(end)||start>now||end<=now
      ||new Date(start).toISOString()!==p.not_before.replace('Z','.000Z')
      ||new Date(end).toISOString()!==p.expires_at.replace('Z','.000Z')
      ||end-start>24*3600000) throw Error('scheduled_root_permit_not_fresh');
  const requestEnd=Date.parse(request?.expires_at);
  if(!Number.isFinite(requestEnd)||requestEnd<=now||requestEnd>end
      ||request?.schema!=='commandcenter.pi.release_request.v1'
      ||request.action!=='pi.release.apply'||request.node_id!=='cc-pi4'
      ||request.source_repo!=='XoticHaze/CommandCenter'||request.source_sha!==p.source_sha
      ||request.expected_release!==p.expected_release||request.request_id!==p.request_id)
    throw Error('scheduled_root_request_not_permitted');
  return p;
}
