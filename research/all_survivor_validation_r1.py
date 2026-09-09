#!/usr/bin/env python3
import argparse, json
from pathlib import Path

REQUIRED_COMMON={
    'implementation_and_time_alignment_verified',
    'appropriate_matched_control',
    'chronological_or_forward_validation',
    'realistic_cost_and_execution_model',
    'concentration_and_stability_reported',
    'independent_confirmation_when_claim_implies_transport',
    'portfolio_opportunity_cost_reported',
}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--lane', required=True)
    ap.add_argument('--contract', required=True)
    ap.add_argument('--out', required=True)
    a=ap.parse_args()
    c=json.loads(Path(a.contract).read_text())
    lanes={x['id']:x for x in c['lanes']}
    if a.lane not in lanes:
        raise SystemExit(f'unknown lane {a.lane}')
    missing=sorted(REQUIRED_COMMON-set(c['common_gates']))
    if missing:
        raise SystemExit(f'common gate drift: {missing}')
    lane=lanes[a.lane]
    if not lane.get('claim') or not lane.get('next_tests') or not lane.get('do_not'):
        raise SystemExit('lane missing claim/tests/do_not boundary')
    out={
        'schema':'research.all_survivor_lane_execution_request.v1',
        'lane':a.lane,
        'claim':lane['claim'],
        'next_tests':lane['next_tests'],
        'do_not':lane['do_not'],
        'state':'READY_FOR_CANDIDATE_SPECIFIC_EXECUTION',
        'scientific_result':None,
        'fresh_run_claim':False,
        'note':'This gate proves the frozen validation request only. It is intentionally not scientific evidence. The owning lane must execute the listed candidate-specific tests and bind exact run/result provenance.'
    }
    Path(a.out).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__': main()
