from __future__ import annotations

"""Append-only compact history for the common forward market scoreboard.

The history is keyed by the actual latest observed market close, preferring the
P249/P266 tape's explicit forward.latest_close. Full daily scoreboard/allocator
payloads are published separately by the workflow; this file is the compact
cross-day analytical index.

This module is reporting-only. It does not change signals, horizons, sizing,
allocation, promotion, broker, or live-trading authority.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "research.forward_market_scoreboard_history_r1"
SCOREBOARD_SCHEMA = "research.forward_market_scoreboard_r1"
ALLOCATOR_SCHEMA = "research.forward_deterministic_allocator_r1"


def _read(path: Path | None) -> tuple[dict[str, Any] | None, bytes | None]:
    if path is None or not path.is_file():
        return None, None
    raw = path.read_bytes()
    return json.loads(raw), raw


def _sha(raw: bytes | None) -> str | None:
    return None if raw is None else hashlib.sha256(raw).hexdigest()


def _session_date(scoreboard: dict[str, Any], p249: dict[str, Any] | None) -> tuple[str, str]:
    latest = (((p249 or {}).get("forward") or {}).get("latest_close"))
    if latest:
        return str(latest)[:10], "P249_P266.forward.latest_close"

    candidates: list[tuple[str, str]] = []
    coverage = scoreboard.get("coverage") or {}
    for key in ("prospective_ledger", "largecap_transport_observer"):
        value = ((coverage.get(key) or {}).get("market_data_asof"))
        if value:
            candidates.append((str(value)[:10], f"coverage.{key}.market_data_asof"))

    for lane in scoreboard.get("lanes") or []:
        pid = str(lane.get("program_id") or "UNKNOWN")
        prospective = lane.get("prospective_evidence") or {}
        if prospective.get("market_data_asof"):
            candidates.append((str(prospective["market_data_asof"])[:10], f"lane.{pid}.prospective_evidence.market_data_asof"))
        forward = lane.get("forward_observation") or {}
        if forward.get("market_data_asof"):
            candidates.append((str(forward["market_data_asof"])[:10], f"lane.{pid}.forward_observation.market_data_asof"))

    if candidates:
        day = max(x[0] for x in candidates)
        authority = ",".join(sorted({a for d, a in candidates if d == day}))
        return day, authority

    generated = str(scoreboard.get("generated_at") or "")
    if len(generated) >= 10:
        return generated[:10], "scoreboard.generated_at_fallback"
    raise RuntimeError("unable to determine history session date")


def _lane_row(lane: dict[str, Any], allocator_actions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pid = str(lane.get("program_id") or "")
    forward = lane.get("forward_observation") or {}
    return {
        "program_id": pid,
        "observation_status": lane.get("observation_status"),
        "validation_grade": lane.get("validation_grade"),
        "evidence_grade": lane.get("evidence_grade"),
        "scientific_forward_credit": lane.get("scientific_forward_credit"),
        "signal_date": lane.get("signal_date"),
        "forward_days": lane.get("forward_days"),
        "action_text": lane.get("action_text"),
        "timing": lane.get("timing"),
        "signal": lane.get("signal"),
        "scorecard": lane.get("scorecard"),
        "prospective_evidence": lane.get("prospective_evidence"),
        "forward_observation": None if not forward else {
            "state": forward.get("state"),
            "entry_date": forward.get("entry_date"),
            "evaluation_date": forward.get("evaluation_date"),
            "market_data_asof": forward.get("market_data_asof"),
            "sessions_completed": forward.get("sessions_completed"),
            "summary": forward.get("summary"),
        },
        "allocator_action": allocator_actions.get(pid),
    }


def make_entry(
    scoreboard: dict[str, Any],
    scoreboard_raw: bytes,
    allocator: dict[str, Any],
    allocator_raw: bytes,
    p249: dict[str, Any] | None = None,
    p249_raw: bytes | None = None,
) -> dict[str, Any]:
    if scoreboard.get("schema") != SCOREBOARD_SCHEMA:
        raise RuntimeError(f"unexpected scoreboard schema {scoreboard.get('schema')}")
    if allocator.get("schema") != ALLOCATOR_SCHEMA:
        raise RuntimeError(f"unexpected allocator schema {allocator.get('schema')}")

    session_date, date_authority = _session_date(scoreboard, p249)
    by_program = {
        str(row.get("source_program_id") or ""): row
        for row in (allocator.get("sleeve_actions") or [])
        if row.get("source_program_id")
    }
    lanes = [_lane_row(lane, by_program) for lane in (scoreboard.get("lanes") or [])]

    return {
        "session_date": session_date,
        "session_date_authority": date_authority,
        "scoreboard_generated_at": scoreboard.get("generated_at"),
        "allocator_generated_at": allocator.get("generated_at"),
        "source_scoreboard_sha256": _sha(scoreboard_raw),
        "source_allocator_sha256": _sha(allocator_raw),
        "source_p249_sha256": _sha(p249_raw),
        "models": lanes,
        "combined_portfolio": {
            "target_weights": allocator.get("final_target_weights"),
            "cash_weight": allocator.get("cash_weight"),
            "sector_exposure": allocator.get("sector_exposure"),
            "position_actions_vs_prior": allocator.get("position_actions_vs_prior_allocator_target"),
            "prior_allocator_target_available": allocator.get("prior_allocator_target_available"),
        },
    }


def append_history(prior: dict[str, Any] | None, entry: dict[str, Any]) -> dict[str, Any]:
    if prior is None:
        sessions: list[dict[str, Any]] = []
    else:
        if prior.get("schema") != SCHEMA:
            raise RuntimeError(f"unexpected prior history schema {prior.get('schema')}")
        sessions = list(prior.get("sessions") or [])

    by_date = {str(row["session_date"]): row for row in sessions}
    day = str(entry["session_date"])
    existing = by_date.get(day)
    if existing is None or str(entry.get("scoreboard_generated_at") or "") >= str(existing.get("scoreboard_generated_at") or ""):
        by_date[day] = entry

    ordered = [by_date[d] for d in sorted(by_date)]
    result = {
        "schema": SCHEMA,
        "session_count": len(ordered),
        "first_session_date": ordered[0]["session_date"] if ordered else None,
        "latest_session_date": ordered[-1]["session_date"] if ordered else None,
        "sessions": ordered,
        "boundaries": {
            "reporting_only": True,
            "allocation_authority": False,
            "promotion_authority": False,
            "broker_action": False,
            "live_trading_change": False,
        },
    }
    if prior is not None:
        for key in ("git_history_bootstrap_complete", "git_history_bootstrap_ref"):
            if key in prior:
                result[key] = prior[key]
    return result


def attach_session_coverage(
    history: dict[str, Any],
    p249: dict[str, Any] | None,
) -> dict[str, Any]:
    observations = (((p249 or {}).get("forward") or {}).get("observations") or [])
    expected = sorted({
        str(row.get("date"))[:10]
        for row in observations
        if isinstance(row, dict) and row.get("date")
    })
    snapshots = sorted({
        str(row.get("session_date"))[:10]
        for row in (history.get("sessions") or [])
        if isinstance(row, dict) and row.get("session_date")
    })
    missing = [d for d in expected if d not in snapshots]
    extra = [d for d in snapshots if expected and d not in expected]
    history["session_coverage"] = {
        "authority": "P249_P266.forward.observations[].date",
        "expected_market_sessions": expected,
        "persisted_scoreboard_snapshot_sessions": snapshots,
        "expected_market_session_count": len(expected),
        "persisted_scoreboard_snapshot_count": len(snapshots),
        "missing_scoreboard_snapshot_sessions": missing,
        "snapshot_coverage_complete": not missing,
        "snapshot_sessions_outside_current_p249_tape": extra,
    }
    return history



def _git_show(repo: Path, ref: str, path: str) -> tuple[dict[str, Any] | None, bytes | None]:
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode != 0:
        return None, None
    raw = proc.stdout
    return json.loads(raw), raw


def bootstrap_from_git(
    repo: Path,
    ref: str,
    snapshot_dir: Path | None = None,
) -> dict[str, Any] | None:
    path = "research/current/forward_market_scoreboard_r1.json"
    proc = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%H", "--reverse", ref, "--", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git history lookup failed ref={ref}: {proc.stderr.strip()}")

    history: dict[str, Any] | None = None
    for commit in [x.strip() for x in proc.stdout.splitlines() if x.strip()]:
        scoreboard, scoreboard_raw = _git_show(repo, commit, path)
        allocator, allocator_raw = _git_show(
            repo, commit, "research/current/forward_deterministic_allocator_r1.json"
        )
        p249, p249_raw = _git_show(
            repo, commit, "research/current/forward_p249_p266_shadow_r1.json"
        )
        if scoreboard is None or scoreboard_raw is None or allocator is None or allocator_raw is None:
            continue
        try:
            entry = make_entry(
                scoreboard,
                scoreboard_raw,
                allocator,
                allocator_raw,
                p249,
                p249_raw,
            )
        except RuntimeError:
            continue
        entry["bootstrap_source_commit"] = commit
        history = append_history(history, entry)
        if snapshot_dir is not None:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            day = entry["session_date"]
            (snapshot_dir / f"{day}.json").write_bytes(scoreboard_raw)
            (snapshot_dir / f"{day}.allocator.json").write_bytes(allocator_raw)
    if history is not None:
        history["git_history_bootstrap_complete"] = True
        history["git_history_bootstrap_ref"] = ref
    return history


def self_test() -> None:
    score = {
        "schema": SCOREBOARD_SCHEMA,
        "generated_at": "2026-09-18T02:00:00+00:00",
        "lanes": [{
            "program_id": "TEST",
            "observation_status": "ACTIVE",
            "signal": {"direction": "UP"},
            "scorecard": {"hit_rate": 0.5},
        }],
        "coverage": {},
    }
    alloc = {
        "schema": ALLOCATOR_SCHEMA,
        "generated_at": "2026-09-18T02:01:00+00:00",
        "final_target_weights": {"CASH": 1.0},
        "cash_weight": 1.0,
        "sleeve_actions": [{
            "source_program_id": "TEST",
            "sleeve": "TEST",
            "action": "NO_ACTION",
            "target_weight": 0.0,
        }],
    }
    p249 = {"forward": {"latest_close": "2026-09-17", "observations": [
        {"date": "2026-09-16"}, {"date": "2026-09-17"}
    ]}}
    raw_s = (json.dumps(score, sort_keys=True) + "\n").encode()
    raw_a = (json.dumps(alloc, sort_keys=True) + "\n").encode()
    raw_p = (json.dumps(p249, sort_keys=True) + "\n").encode()
    first = make_entry(score, raw_s, alloc, raw_a, p249, raw_p)
    assert first["session_date"] == "2026-09-17"
    assert first["session_date_authority"] == "P249_P266.forward.latest_close"
    hist = attach_session_coverage(append_history(None, first), p249)
    assert hist["session_count"] == 1
    assert hist["session_coverage"]["missing_scoreboard_snapshot_sessions"] == ["2026-09-16"]
    assert hist["session_coverage"]["snapshot_coverage_complete"] is False
    assert hist["sessions"][0]["models"][0]["allocator_action"]["target_weight"] == 0.0

    score2 = dict(score)
    score2["generated_at"] = "2026-09-19T02:00:00+00:00"
    score2["lanes"] = [dict(score["lanes"][0], scorecard={"hit_rate": 0.75})]
    raw_s2 = (json.dumps(score2, sort_keys=True) + "\n").encode()
    p249_2 = {"forward": {"latest_close": "2026-09-18", "observations": [
        {"date": "2026-09-16"}, {"date": "2026-09-17"}, {"date": "2026-09-18"}
    ]}}
    raw_p2 = (json.dumps(p249_2, sort_keys=True) + "\n").encode()
    second = make_entry(score2, raw_s2, alloc, raw_a, p249_2, raw_p2)
    hist = attach_session_coverage(append_history(hist, second), p249_2)
    assert hist["session_count"] == 2
    assert hist["session_coverage"]["missing_scoreboard_snapshot_sessions"] == ["2026-09-16"]
    assert hist["session_coverage"]["expected_market_session_count"] == 3
    assert hist["latest_session_date"] == "2026-09-18"

    same_day_newer = dict(second)
    same_day_newer["scoreboard_generated_at"] = "2026-09-19T03:00:00+00:00"
    same_day_newer["models"] = [dict(second["models"][0], scorecard={"hit_rate": 0.8})]
    hist = attach_session_coverage(append_history(hist, same_day_newer), p249_2)
    assert hist["session_count"] == 2
    assert hist["sessions"][-1]["models"][0]["scorecard"]["hit_rate"] == 0.8
    print("FORWARD_SCOREBOARD_HISTORY_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scoreboard")
    p.add_argument("--allocator")
    p.add_argument("--p249")
    p.add_argument("--prior")
    p.add_argument("--bootstrap-repo")
    p.add_argument("--bootstrap-ref", default="origin/main")
    p.add_argument("--bootstrap-snapshot-dir")
    p.add_argument("--output")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.scoreboard or not args.allocator or not args.output:
        p.error("--scoreboard, --allocator and --output are required unless --self-test")

    scoreboard, scoreboard_raw = _read(Path(args.scoreboard))
    allocator, allocator_raw = _read(Path(args.allocator))
    p249, p249_raw = _read(Path(args.p249)) if args.p249 else (None, None)
    prior, _ = _read(Path(args.prior)) if args.prior else (None, None)
    if args.bootstrap_repo and not bool((prior or {}).get("git_history_bootstrap_complete")):
        boot = bootstrap_from_git(
            Path(args.bootstrap_repo),
            args.bootstrap_ref,
            Path(args.bootstrap_snapshot_dir) if args.bootstrap_snapshot_dir else None,
        )
        if boot is not None:
            if prior is None:
                prior = boot
            else:
                for historical_entry in boot.get("sessions") or []:
                    prior = append_history(prior, historical_entry)
                prior["git_history_bootstrap_complete"] = True
                prior["git_history_bootstrap_ref"] = args.bootstrap_ref
    assert scoreboard is not None and scoreboard_raw is not None
    assert allocator is not None and allocator_raw is not None

    entry = make_entry(scoreboard, scoreboard_raw, allocator, allocator_raw, p249, p249_raw)
    history = attach_session_coverage(append_history(prior, entry), p249)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(history, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "session_date": entry["session_date"],
        "session_date_authority": entry["session_date_authority"],
        "session_count": history["session_count"],
        "latest_session_date": history["latest_session_date"],
        "session_coverage": history.get("session_coverage"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
