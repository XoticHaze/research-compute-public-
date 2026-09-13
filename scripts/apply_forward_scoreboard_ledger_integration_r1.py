from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def patch_scoreboard() -> None:
    p = Path("research/forward_market_scoreboard_r1.py")
    s = p.read_text()

    s = replace_once(
        s,
        'ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"\nEXPECTED_PRIVATE_ADAPTERS = (',
        'ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"\nLEDGER_SCHEMA = "research.forward_prospective_cohort_ledger_r1"\nEXPECTED_PRIVATE_ADAPTERS = (',
        "ledger schema constant",
    )

    marker = '\ndef _native_lane(x: dict[str, Any]) -> dict[str, Any]:\n'
    helper = '''
def _prospective_state(ledger: dict[str, Any] | None, program_id: str) -> dict[str, Any]:
    if ledger is None:
        return {"ledger_status": "NOT_SUPPLIED", "program_id": program_id}
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise RuntimeError(f"unexpected prospective ledger schema {ledger.get('schema')}")
    rows = [c for c in (ledger.get("cohorts") or []) if c.get("program_id") == program_id]
    summary = dict((ledger.get("summary") or {}).get(program_id) or {})
    current = max(
        rows,
        key=lambda c: (str(c.get("signal_date") or ""), str(c.get("first_registered_at") or "")),
        default=None,
    )
    out = {
        "ledger_status": "PRESENT",
        "program_id": program_id,
        "market_data_asof": ledger.get("market_data_asof"),
        "registered_cohorts": int(summary.get("registered_cohorts", len(rows)) or 0),
        "resolved_cohorts": int(summary.get("resolved_cohorts", 0) or 0),
        "open_cohorts": int(summary.get("open_cohorts", 0) or 0),
        "late_registration_rejections": int(summary.get("late_registration_rejections", 0) or 0),
        "minimum_resolved_for_promotion": summary.get("minimum_resolved_for_promotion"),
        "promotion_authority": False,
    }
    for key in (
        "resolved_observations",
        "positive_hit_rate",
        "mean_excess_vs_itb_bps",
        "mean_ticker_book_excess_vs_smh_bps",
        "mean_ticker_positive_hit_rate",
    ):
        if key in summary:
            out[key] = summary.get(key)
    if current:
        out.update(
            {
                "current_cohort_id": current.get("cohort_id"),
                "current_signal_date": current.get("signal_date"),
                "current_cohort_status": current.get("status"),
            }
        )
        resolution = current.get("resolution") or {}
        compact = {}
        for key in (
            "entry_date",
            "exit_date",
            "horizon_sessions",
            "sessions_completed",
            "ticker_book_net_return_bps",
            "ticker_book_excess_vs_smh_bps",
            "ticker_book_excess_vs_qqq_bps",
            "ticker_positive_hit_rate",
            "prediction_mae_bps",
        ):
            if key in resolution:
                compact[key] = resolution.get(key)
        if resolution.get("summary") is not None:
            compact["summary"] = resolution.get("summary")
        if compact:
            out["current_resolution"] = compact
    return out


def _prospective_evidence_grade(state: dict[str, Any]) -> str:
    if state.get("ledger_status") != "PRESENT":
        return "NO_PROSPECTIVE_LEDGER"
    if int(state.get("late_registration_rejections", 0) or 0) > 0:
        return "CHRONOLOGY_REJECTION_PRESENT"
    if int(state.get("registered_cohorts", 0) or 0) <= 0:
        return "NO_REGISTERED_PROSPECTIVE_COHORT"
    status = str(state.get("current_cohort_status") or "")
    if status in {"REGISTERED", "AWAITING_ENTRY_SESSION", "OPEN", "PARTIALLY_RESOLVED"}:
        return f"PROSPECTIVE_{status}"
    resolved = int(state.get("resolved_cohorts", 0) or 0)
    floor = state.get("minimum_resolved_for_promotion")
    if floor is not None and resolved < int(floor):
        return "PROSPECTIVE_EVIDENCE_ACCUMULATING"
    if floor is not None and resolved >= int(floor):
        return "SAMPLE_FLOOR_REACHED_NOT_PROMOTED"
    if resolved > 0:
        return "PROSPECTIVE_RESULTS_AVAILABLE"
    return "PROSPECTIVE_REGISTERED"


def _native_lane(x: dict[str, Any], prospective: dict[str, Any] | None = None) -> dict[str, Any]:
'''
    s = replace_once(s, marker, "\n" + helper, "native lane helper insertion")

    s = replace_once(
        s,
        '        "validation": validation,\n        "validation_grade": grade,\n        "decision_use": x.get("decision_use"),',
        '        "validation": validation,\n        "validation_grade": grade,\n        "prospective_evidence": prospective or {"ledger_status": "NOT_SUPPLIED", "program_id": program_id},\n        "evidence_grade": _prospective_evidence_grade(prospective or {}),\n        "decision_use": x.get("decision_use"),',
        "native lane evidence fields",
    )

    s = replace_once(
        s,
        'def build(root: Path) -> dict[str, Any]:\n    lanes = [',
        'def build(root: Path) -> dict[str, Any]:\n    ledger = _load(root, "forward_prospective_cohort_ledger_r1.json")\n    lanes = [',
        "load prospective ledger",
    )
    s = replace_once(
        s,
        '            lanes.append(_native_lane(payload))',
        '            lanes.append(_native_lane(payload, _prospective_state(ledger, program_id)))',
        "attach prospective state",
    )

    s = replace_once(
        s,
        '''            "semiconductor": {
                "positive_breadth": (semi.get("signal") or {}).get("positive_breadth"),
                "action": (semi.get("paper_action") or {}).get("status"),
            },
            "homebuilders": {
                "admitted": (hb.get("signal") or {}).get("admitted_symbols", []),
                "horizons": (hb.get("signal") or {}).get("duration_horizon_sessions_by_symbol", {}),
            },''',
        '''            "semiconductor": {
                "positive_breadth": (semi.get("signal") or {}).get("positive_breadth"),
                "action": (semi.get("paper_action") or {}).get("status"),
                "prospective_evidence": semi.get("prospective_evidence", {}),
                "evidence_grade": semi.get("evidence_grade"),
            },
            "homebuilders": {
                "admitted": (hb.get("signal") or {}).get("admitted_symbols", []),
                "horizons": (hb.get("signal") or {}).get("duration_horizon_sessions_by_symbol", {}),
                "prospective_evidence": hb.get("prospective_evidence", {}),
                "evidence_grade": hb.get("evidence_grade"),
            },''',
        "decision chain prospective state",
    )

    s = replace_once(
        s,
        '            "JAAA_vs_cash_control_bps": (clo.get("scorecard") or {}).get("excess_vs_matched_cash_control_bps"),\n        },',
        '            "JAAA_vs_cash_control_bps": (clo.get("scorecard") or {}).get("excess_vs_matched_cash_control_bps"),\n            "semiconductor_mean_ticker_book_excess_vs_smh_bps": (semi.get("prospective_evidence") or {}).get("mean_ticker_book_excess_vs_smh_bps"),\n            "homebuilders_mean_excess_vs_itb_bps": (hb.get("prospective_evidence") or {}).get("mean_excess_vs_itb_bps"),\n        },',
        "decision chain realized excess",
    )

    s = replace_once(
        s,
        '''        "coverage": {
            "scored_now": [x.get("program_id") for x in lanes if x.get("signal")],
            "adapter_contracts_ready": list(EXPECTED_PRIVATE_ADAPTERS),
            "native_result_gaps": missing,
        },''',
        '''        "coverage": {
            "scored_now": [x.get("program_id") for x in lanes if x.get("signal")],
            "adapter_contracts_ready": list(EXPECTED_PRIVATE_ADAPTERS),
            "native_result_gaps": missing,
            "prospective_ledger": {
                "present": ledger is not None,
                "market_data_asof": None if ledger is None else ledger.get("market_data_asof"),
                "programs": [] if ledger is None else sorted((ledger.get("summary") or {}).keys()),
            },
        },''',
        "coverage prospective ledger",
    )

    s = replace_once(
        s,
        '            "daily_score_does_not_imply_daily_turnover": True,\n            "broker_or_live_authority": False,',
        '            "daily_score_does_not_imply_daily_turnover": True,\n            "prospective_evidence_does_not_grant_allocation_authority": True,\n            "broker_or_live_authority": False,',
        "interpretation boundary",
    )

    s = replace_once(
        s,
        '        for i, payload in enumerate((semi, hb, large)):\n            (root / f"forward_program_adapter_{i}.json").write_text(json.dumps(payload))\n        out = build(root)',
        '''        for i, payload in enumerate((semi, hb, large)):
            (root / f"forward_program_adapter_{i}.json").write_text(json.dumps(payload))
        (root / "forward_prospective_cohort_ledger_r1.json").write_text(json.dumps({
            "schema": LEDGER_SCHEMA,
            "market_data_asof": "2026-09-13",
            "cohorts": [
                {"cohort_id": "HOMEBUILDERS:2026-09-10:test", "program_id": "HOMEBUILDERS", "signal_date": "2026-09-10", "first_registered_at": "2026-09-11T00:00:00+00:00", "status": "OPEN", "resolution": {"entry_date": "2026-09-11", "sessions_completed": 1}},
                {"cohort_id": "SEMICONDUCTOR_SHARED_RIDGE:2026-09-10:test", "program_id": "SEMICONDUCTOR_SHARED_RIDGE", "signal_date": "2026-09-10", "first_registered_at": "2026-09-11T00:00:00+00:00", "status": "AWAITING_ENTRY_SESSION", "resolution": None},
            ],
            "summary": {
                "HOMEBUILDERS": {"registered_cohorts": 1, "resolved_cohorts": 0, "open_cohorts": 1, "late_registration_rejections": 0, "minimum_resolved_for_promotion": None, "resolved_observations": 0, "mean_excess_vs_itb_bps": None},
                "SEMICONDUCTOR_SHARED_RIDGE": {"registered_cohorts": 1, "resolved_cohorts": 0, "open_cohorts": 1, "late_registration_rejections": 0, "minimum_resolved_for_promotion": 20, "mean_ticker_book_excess_vs_smh_bps": None},
            },
        }))
        out = build(root)''',
        "self-test ledger fixture",
    )

    s = replace_once(
        s,
        '        assert out["decision_chain"]["sectors"]["homebuilders"]["horizons"] == {"CCS": 5}\n        assert out["interpretation"]["daily_score_does_not_imply_daily_turnover"] is True',
        '''        assert out["decision_chain"]["sectors"]["homebuilders"]["horizons"] == {"CCS": 5}
        native_by_id = {x["program_id"]: x for x in out["lanes"]}
        assert native_by_id["HOMEBUILDERS"]["evidence_grade"] == "PROSPECTIVE_OPEN"
        assert native_by_id["SEMICONDUCTOR_SHARED_RIDGE"]["evidence_grade"] == "PROSPECTIVE_AWAITING_ENTRY_SESSION"
        assert native_by_id["SEMICONDUCTOR_SHARED_RIDGE"]["validation_grade"] == "PROSPECTIVE_SIGNAL_READY"
        assert out["coverage"]["prospective_ledger"]["present"] is True
        assert out["interpretation"]["daily_score_does_not_imply_daily_turnover"] is True
        assert out["interpretation"]["prospective_evidence_does_not_grant_allocation_authority"] is True''',
        "self-test prospective assertions",
    )

    p.write_text(s)


def patch_workflow() -> None:
    p = Path(".github/workflows/forward-market-scoreboard-r1.yml")
    s = p.read_text()

    old = "      - 'research/current/native_adapters/*.json'\n      - '.github/workflows/forward-market-scoreboard-r1.yml'"
    new = "      - 'research/current/native_adapters/*.json'\n      - 'research/current/forward_prospective_cohort_ledger_r1.json'\n      - '.github/workflows/forward-market-scoreboard-r1.yml'"
    if s.count(old) != 2:
        raise RuntimeError(f"workflow trigger insertion expected 2 matches, got {s.count(old)}")
    s = s.replace(old, new, 2)

    s = replace_once(
        s,
        '''            cp "$src" score-inputs/native-current/
          done
      - run: python research/forward_market_scoreboard_r1.py --input-root score-inputs --output artifacts/forward_market_scoreboard_r1.json''',
        '''            cp "$src" score-inputs/native-current/
          done
          if test -f research/current/forward_prospective_cohort_ledger_r1.json; then
            mkdir -p score-inputs/prospective-current
            cp research/current/forward_prospective_cohort_ledger_r1.json score-inputs/prospective-current/
          fi
      - run: python research/forward_market_scoreboard_r1.py --input-root score-inputs --output artifacts/forward_market_scoreboard_r1.json''',
        "workflow copy ledger",
    )

    s = replace_once(
        s,
        '''              if lane.get('scorecard'):
                  print('  scorecard=', json.dumps(lane['scorecard'], sort_keys=True))
          print('native_result_gaps=', ','.join(x['coverage']['native_result_gaps']))''',
        '''              if lane.get('scorecard'):
                  print('  scorecard=', json.dumps(lane['scorecard'], sort_keys=True))
              if lane.get('prospective_evidence'):
                  print('  prospective_evidence=', json.dumps(lane['prospective_evidence'], sort_keys=True))
                  print('  evidence_grade=', lane.get('evidence_grade'))
          print('native_result_gaps=', ','.join(x['coverage']['native_result_gaps']))
          print('prospective_ledger=', json.dumps(x['coverage']['prospective_ledger'], sort_keys=True))''',
        "workflow print prospective state",
    )

    p.write_text(s)


if __name__ == "__main__":
    patch_scoreboard()
    patch_workflow()
    print("FORWARD_SCOREBOARD_LEDGER_INTEGRATION_PATCH=PASS")
