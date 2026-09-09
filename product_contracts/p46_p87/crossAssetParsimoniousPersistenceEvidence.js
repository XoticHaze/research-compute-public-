const PARSIMONIOUS_PERSISTENCE_EVIDENCE = Object.freeze({
  schema: 'mm.strategy_intelligence.crossasset_parsimonious_persistence_evidence.v1',
  parent_ids: Object.freeze(['P46', 'P87', 'P91']),
  result_identity: 'P87 momentum+trend+drawdown serial persistence r1',
  source_event: 'p91-p87-three-factor-persistence-supported-20260909T020200Z',
  formulation: Object.freeze({ factors: Object.freeze(['momentum', 'trend', 'drawdown']), frozen: true, factor_weight_tuning_authorized: false, horizon_tuning_authorized: false, additional_factor_removal_authorized: false }),
  execution: Object.freeze({ repo: 'XoticHaze/research-compute-public-', workflow: '.github/workflows/p91-p87-serial-persistence-r1.yml', run_id: 34301426988, job_id: 102308956275, started_at: '2026-09-09T02:00:01Z', head_sha: 'aa876e411c00e1895e9817f667d463d510e3bded', checkout_merge_sha: '35ca4308d510b63f247110cb145e8cc966526d54', conclusion: 'success', artifact_id: 10085060097, artifact_sha256: 'b2d4453be38057f720af5f6f1bf599da79bf7181419c5d82fefbc40995f1b5ac' }),
  window: Object.freeze({ start: '2008-04-30', end: '2026-08-31', months: 221 }),
  matched_equal_weight_25bps: Object.freeze({ annualized_mean_excess: 0.028522789817447554, rolling36_positive_fraction: 0.6935483870967742, rolling60_positive_fraction: 0.9012345679012346, rolling60_median_excess_cagr: 0.024138725073794554, bootstrap_95pct: Object.freeze([-0.008609670083130122, 0.06518747873834828]), bootstrap_p_excess_le_zero: 0.0692 }),
  original_four_factor_25bps: Object.freeze({ annualized_mean_excess: 0.01547009824566538, rolling36_positive_fraction: 0.6290322580645161, rolling60_positive_fraction: 0.6049382716049383, rolling60_median_excess_cagr: 0.005065952220208003, bootstrap_95pct: Object.freeze([-0.0069488000000052525, 0.034216657638028336]), bootstrap_p_excess_le_zero: 0.094 }),
  matched_equal_weight_50bps: Object.freeze({ annualized_mean_excess: 0.021735459500705476, rolling60_positive_fraction: 0.7654320987654321, bootstrap_95pct: Object.freeze([-0.015946976758887465, 0.059055431439219715]), bootstrap_p_excess_le_zero: 0.1344 }),
  scientific_consequence: 'The frozen momentum+trend+drawdown formulation has useful serial support on an independent representation, but moving-block bootstrap intervals still cross zero. Treat it as stronger parsimonious research evidence, not deterministic superiority or deployment promotion.',
  product_boundary: Object.freeze({ research_only: true, portfolio_ranking_authority: false, allocation_authority: false, position_sizing_authority: false, promotion_authority: false, strategy_spec_mutation: false, runtime_mutation: false, broker_action: false, live_trading_change: false }),
})
export function crossAssetParsimoniousPersistenceEvidence() { return PARSIMONIOUS_PERSISTENCE_EVIDENCE }
export function crossAssetParsimoniousPersistenceDiagnostic(evidence = PARSIMONIOUS_PERSISTENCE_EVIDENCE) {
  const ew25 = evidence.matched_equal_weight_25bps, four25 = evidence.original_four_factor_25bps, ew50 = evidence.matched_equal_weight_50bps
  const serialSupport = ew25.rolling60_positive_fraction >= 0.9 && ew50.rolling60_positive_fraction >= 0.75
  const bootstrapResolved = ew25.bootstrap_95pct[0] > 0 && four25.bootstrap_95pct[0] > 0 && ew50.bootstrap_95pct[0] > 0
  return Object.freeze({ state: serialSupport && !bootstrapResolved ? 'PARSIMONIOUS_SERIAL_SUPPORT_BOOTSTRAP_UNRESOLVED' : bootstrapResolved ? 'PARSIMONIOUS_SERIAL_AND_BOOTSTRAP_SUPPORT' : 'PARSIMONIOUS_PERSISTENCE_GATE_OPEN', serial_support: serialSupport, bootstrap_resolved: bootstrapResolved, improves_rolling60_frequency_vs_four_factor: ew25.rolling60_positive_fraction > four25.rolling60_positive_fraction, operator_consequence: 'Surface P87 as mechanism-quality evidence inside the P46 fund review. Do not interpret parsimonious replication as permission to rank portfolios, tune factor weights, allocate capital, promote a model, or change runtime behavior.', next_product_boundary: 'Preserve implementation-cost break-even, state/risk attribution, and genuinely independent-source evidence when those scientific results become available.' })
}
