import test from 'node:test'
import assert from 'node:assert/strict'
import { crossAssetParsimoniousPersistenceEvidence, crossAssetParsimoniousPersistenceDiagnostic } from './crossAssetParsimoniousPersistenceEvidence.js'
import { crossAssetEnsemblePersistenceEvidence, crossAssetEnsemblePersistenceDiagnostic } from './crossAssetEnsemblePersistenceEvidence.js'

const EXPECTED_MM_HEAD = '3711b94fe20f2c828e8c72db65fa412b5d3c269a'
const EXPECTED_MM_SOURCE_BLOBS = Object.freeze({
  parsimonious: 'f86128f9b29ba08b85e74c82899b39c5ac53bbba',
  ensemble: '71fbb618ca879d1ef03a46e66be5563ff936b7a8',
})

test('public product-contract acceptance is bound to the MM candidate head and source blobs', () => {
  assert.equal(EXPECTED_MM_HEAD, '3711b94fe20f2c828e8c72db65fa412b5d3c269a')
  assert.equal(EXPECTED_MM_SOURCE_BLOBS.parsimonious, 'f86128f9b29ba08b85e74c82899b39c5ac53bbba')
  assert.equal(EXPECTED_MM_SOURCE_BLOBS.ensemble, '71fbb618ca879d1ef03a46e66be5563ff936b7a8')
})

test('P87 product diagnostic preserves serial support and bootstrap uncertainty', () => {
  const e = crossAssetParsimoniousPersistenceEvidence()
  const d = crossAssetParsimoniousPersistenceDiagnostic(e)
  assert.equal(e.execution.run_id, 34301426988)
  assert.equal(e.execution.job_id, 102308956275)
  assert.equal(e.execution.artifact_id, 10085060097)
  assert.equal(e.execution.artifact_sha256, 'b2d4453be38057f720af5f6f1bf599da79bf7181419c5d82fefbc40995f1b5ac')
  assert.equal(d.state, 'PARSIMONIOUS_SERIAL_SUPPORT_BOOTSTRAP_UNRESOLVED')
  assert.equal(d.serial_support, true)
  assert.equal(d.bootstrap_resolved, false)
  assert.ok(e.matched_equal_weight_25bps.annualized_mean_excess > 0)
  assert.ok(e.matched_equal_weight_50bps.annualized_mean_excess > 0)
  assert.equal(e.product_boundary.portfolio_ranking_authority, false)
  assert.equal(e.product_boundary.allocation_authority, false)
  assert.equal(e.product_boundary.live_trading_change, false)
})

test('P90 product diagnostic separates matched alpha from unresolved incremental P46 value', () => {
  const e = crossAssetEnsemblePersistenceEvidence()
  const d = crossAssetEnsemblePersistenceDiagnostic(e)
  assert.equal(e.execution.run_id, 34301377071)
  assert.equal(e.execution.job_id, 102308806978)
  assert.equal(e.execution.artifact_id, 10085045011)
  assert.equal(e.execution.artifact_sha256, '94343928b20135bd6e6a1710655d8613693271b297f8edc4b5349a7d461d80ff')
  assert.equal(d.state, 'DIVERSIFICATION_EVIDENCE_SUPPORTED_INCREMENTAL_P46_UNRESOLVED')
  assert.equal(d.matched_alpha_resolved, true)
  assert.equal(d.incremental_vs_p46_resolved, false)
  assert.equal(e.versus_p46_25bps.bootstrap_p_excess_le_zero, 0.508)
  assert.equal(e.product_boundary.portfolio_ranking_authority, false)
  assert.equal(e.product_boundary.allocation_authority, false)
  assert.equal(e.product_boundary.live_trading_change, false)
})
