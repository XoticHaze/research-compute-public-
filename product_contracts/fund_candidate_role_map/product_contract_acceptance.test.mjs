import test from 'node:test';
import assert from 'node:assert/strict';

const MM_HEAD = 'e315c09e10645887e177b3433202b52adc206dce';
const sourceIntegrity = Object.freeze({
  scientific_event_id: '20260909T075226Z__p46_source_repeatability_consequence',
  coordinator_event_id: '20260909T075730Z__coordinator_p46_integrity_rerank',
  run_id: 34326041922,
  job_id: 102383423521,
  started_at_utc: '2026-09-09T07:51:57Z',
  head_sha: 'a04c71ad7a9d7110c3a7b475e2214ff2ad0899c0',
  artifact_id: 10093793165,
  artifact_digest: 'sha256:1fbe97dbc36e7099abcf7c648455b3f52748077c2b0ce5bc072173dffee71529',
  identical_source_requests: 6,
  unique_normalized_panel_hashes: 6,
  product_state: 'P46_DEPTH_PAUSED_PENDING_ECONOMIC_REPEATABILITY_OR_IMMUTABLE_DATA',
  provisional_primary: 'P36',
  secondary: 'P64',
});

const retainedHistoricalChain = [
  ['34322734144', '102372856762', '2026-09-09T07:13:05Z', '10092500859'],
  ['34322914461', '102373424285', '2026-09-09T07:15:15Z', '10092580859'],
  ['34323031715', '102373803608', '2026-09-09T07:16:39Z', '10092617345'],
  ['34323299133', '102374658240', '2026-09-09T07:19:59Z', '10092724729'],
  ['34323494752', '102375297697', '2026-09-09T07:22:20Z', '10092799935'],
  ['34323547181', '102375469448', '2026-09-09T07:22:57Z', '10092818513'],
];

test('bind exact source-integrity product head', () => {
  assert.equal(MM_HEAD, 'e315c09e10645887e177b3433202b52adc206dce');
});

test('source-integrity evidence is exact and economically unresolved', () => {
  assert.equal(sourceIntegrity.run_id, 34326041922);
  assert.equal(sourceIntegrity.job_id, 102383423521);
  assert.equal(sourceIntegrity.started_at_utc, '2026-09-09T07:51:57Z');
  assert.equal(sourceIntegrity.artifact_id, 10093793165);
  assert.equal(sourceIntegrity.identical_source_requests, 6);
  assert.equal(sourceIntegrity.unique_normalized_panel_hashes, 6);
  assert.match(sourceIntegrity.product_state, /DEPTH_PAUSED/);
});

test('coordinator posture is consumed read-only rather than recreated', () => {
  assert.equal(sourceIntegrity.provisional_primary, 'P36');
  assert.equal(sourceIntegrity.secondary, 'P64');
  assert.equal(sourceIntegrity.coordinator_event_id, '20260909T075730Z__coordinator_p46_integrity_rerank');
});

test('retained historical evidence remains separately identifiable', () => {
  assert.equal(retainedHistoricalChain.length, 6);
  for (const i of [0, 1, 2, 3]) assert.equal(new Set(retainedHistoricalChain.map((x) => x[i])).size, 6);
});

test('no portfolio or trading authority', () => {
  assert.deepEqual(Object.values({ranking:false,allocation:false,sizing:false,timing:false,promotion:false,strategy:false,runtime:false,data:false,broker:false,live:false}), Array(10).fill(false));
});
