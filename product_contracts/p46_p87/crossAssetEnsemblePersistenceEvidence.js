const ENSEMBLE_PERSISTENCE_EVIDENCE = Object.freeze({
  schema: 'mm.strategy_intelligence.crossasset_ensemble_persistence_evidence.v1',
  parent_ids: Object.freeze(['P46', 'P47', 'P89', 'P90']),
  result_identity: 'P46/P47 frozen 50-50 ensemble persistence r1',
  source_event: 'p90-ensemble-persistence-supported-incremental-vs-p46-uncertain-20260909T020100Z',
  ensemble: Object.freeze({ p46_weight: 0.5, p47_weight: 0.5, frozen: true, weight_tuning_authorized: false }),
  execution: Object.freeze({ repo: 'XoticHaze/research-compute-public-', workflow: '.github/workflows/p90-p46-p47-ensemble-persistence-r1.yml', run_id: 34301377071, job_id: 102308806978, started_at: '2026-09-09T01:59:16Z', head_sha: 'bde93e539960132d635f19b207fe88cf9d25bd78', checkout_merge_sha: 'dc64fb8864db972ad1bd802d7b75ebe5a4e62734', conclusion: 'success', artifact_id: 10085045011, artifact_sha256: '94343928b20135bd6e6a1710655d8613693271b297f8edc4b5349a7d461d80ff' }),
  window: Object.freeze({ start: '2007-03-31', end: '2026-08-31', months: 234 }),
  matched_combined_control_25bps: Object.freeze({ annualized_mean_excess: 0.0335125719902557, rolling36_positive_fraction: 0.8693467336683417, rolling60_positive_fraction: 0.9828571428571429, rolling60_median_excess_cagr: 0.027710005064484955, bootstrap_95pct: Object.freeze([0.008881260019254936, 0.05417327299911435]), bootstrap_p_excess_le_zero: 0.0022 }),
  matched_combined_control_50bps: Object.freeze({ annualized_mean_excess: 0.02513650361418733, rolling36_positive_fraction: 0.7336683417085427, rolling60_positive_fraction: 0.9657142857142857, bootstrap_95pct: Object.freeze([0.0003253286562040091, 0.0462684966374426]), bootstrap_p_excess_le_zero: 0.023 }),
  versus_p46_25bps: Object.freeze({ annualized_mean_excess: 0.0015722062998967533, rolling36_positive_fraction: 0.678391959798995, rolling60_positive_fraction: 0.8285714285714286, rolling60_median_excess_cagr: 0.01295751464293704, bootstrap_95pct: Object.freeze([-0.03694362353742044, 0.03188173213143364]), bootstrap_p_excess_le_zero: 0.508 }),
  scientific_consequence: 'The frozen 50/50 P46/P47 ensemble has persistent after-cost alpha versus its exact combined matched control, but P47 incremental value over P46 is bootstrap-unresolved. Preserve this as diversification evidence only.',
  product_boundary: Object.freeze({ research_only: true, portfolio_ranking_authority: false, allocation_authority: false, position_sizing_authority: false, promotion_authority: false, strategy_spec_mutation: false, runtime_mutation: false, broker_action: false, live_trading_change: false }),
})
export function crossAssetEnsemblePersistenceEvidence() { return ENSEMBLE_PERSISTENCE_EVIDENCE }
export function crossAssetEnsemblePersistenceDiagnostic(evidence = ENSEMBLE_PERSISTENCE_EVIDENCE) {
  const c25 = evidence.matched_combined_control_25bps, c50 = evidence.matched_combined_control_50bps, p46 = evidence.versus_p46_25bps
  const matchedAlphaResolved = c25.bootstrap_95pct[0] > 0 && c50.bootstrap_95pct[0] > 0
  const incrementalP46Resolved = p46.bootstrap_95pct[0] > 0 || p46.bootstrap_95pct[1] < 0
  return Object.freeze({ state: matchedAlphaResolved && !incrementalP46Resolved ? 'DIVERSIFICATION_EVIDENCE_SUPPORTED_INCREMENTAL_P46_UNRESOLVED' : incrementalP46Resolved ? 'ENSEMBLE_INCREMENTAL_EVIDENCE_RESOLVED' : 'ENSEMBLE_PERSISTENCE_GATE_OPEN', matched_alpha_resolved: matchedAlphaResolved, incremental_vs_p46_resolved: incrementalP46Resolved, operator_consequence: 'Use the ensemble result to expose diversification evidence and its uncertainty. Do not promote P47, tune ensemble weights, rank portfolios, allocate capital, size positions, or change runtime behavior from this result.', next_product_boundary: 'Await coordinator/portfolio-authority consumption if diversification evidence becomes relevant to an allocation review; Trading Product keeps this evidence descriptive and fail-closed.' })
}
