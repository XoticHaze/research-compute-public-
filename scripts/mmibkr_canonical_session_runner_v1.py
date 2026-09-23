from __future__ import annotations
"""Budget-aware portable session runner for canonical MM-IBKR research jobs."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

try:
    from scripts import mmibkr_canonical_workload_dispatch_v1 as dispatch
except ImportError:  # direct script execution
    import mmibkr_canonical_workload_dispatch_v1 as dispatch  # type: ignore

SESSION_SCHEMA = "mmibkr.canonical_session.v1"
SESSION_RECEIPT_SCHEMA = "mmibkr.canonical_session_receipt.v1"


class CanonicalSessionError(RuntimeError):
    pass


def _exact(node: dict, keys: set[str], label: str) -> None:
    extra = set(node) - keys
    if extra:
        raise CanonicalSessionError(f"{label} unexpected fields={sorted(extra)}")


def _int(value: Any, label: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except Exception as exc:
        raise CanonicalSessionError(f"{label} must be integer") from exc
    if not minimum <= number <= maximum:
        raise CanonicalSessionError(f"{label} must be within {minimum}..{maximum}")
    return number


def validate_session(node: dict) -> dict:
    if not isinstance(node, dict):
        raise CanonicalSessionError("session root must be object")
    _exact(
        node,
        {"schema", "session_id", "budget_seconds", "reserve_seconds", "max_parallel", "jobs"},
        "session",
    )
    if node.get("schema") != SESSION_SCHEMA:
        raise CanonicalSessionError("unsupported session schema")
    session_id = dispatch.valid_id(node.get("session_id"), "session_id")
    budget_seconds = _int(node.get("budget_seconds"), "budget_seconds", 1, 18_000)
    reserve_seconds = _int(node.get("reserve_seconds", 0), "reserve_seconds", 0, 600)
    if reserve_seconds >= budget_seconds:
        raise CanonicalSessionError("reserve_seconds must be smaller than budget_seconds")
    max_parallel = _int(node.get("max_parallel", 1), "max_parallel", 1, 8)
    raw_jobs = node.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs or len(raw_jobs) > 256:
        raise CanonicalSessionError("session jobs must contain 1..256 jobs")

    jobs: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            raise CanonicalSessionError("session job must be object")
        _exact(raw, {"job_id", "priority", "depends_on", "request"}, "session job")
        job_id = dispatch.valid_id(raw.get("job_id"))
        if job_id in ids:
            raise CanonicalSessionError(f"duplicate session job_id: {job_id}")
        deps = raw.get("depends_on")
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            raise CanonicalSessionError(f"invalid depends_on: {job_id}")
        if len(deps) != len(set(deps)):
            raise CanonicalSessionError(f"duplicate dependency: {job_id}")
        request = raw.get("request")
        if not isinstance(request, dict) or request.get("job_id") != job_id:
            raise CanonicalSessionError(f"session/request job_id mismatch: {job_id}")
        resources = request.get("resources")
        if not isinstance(resources, dict):
            raise CanonicalSessionError(f"request resources missing: {job_id}")
        max_wall = _int(resources.get("max_wall_seconds"), f"{job_id}.max_wall_seconds", 1, 18_000)
        priority = _int(raw.get("priority", 0), f"{job_id}.priority", -1000, 1000)
        ids.add(job_id)
        jobs.append(
            {
                "job_id": job_id,
                "priority": priority,
                "max_wall_seconds": max_wall,
                "depends_on": list(deps),
                "request": request,
            }
        )

    for job in jobs:
        for dep in job["depends_on"]:
            if dep not in ids or dep == job["job_id"]:
                raise CanonicalSessionError(
                    f"invalid dependency {dep!r} for {job['job_id']}"
                )

    remaining = {job["job_id"]: set(job["depends_on"]) for job in jobs}
    done: set[str] = set()
    while remaining:
        ready = [job_id for job_id, deps in remaining.items() if deps <= done]
        if not ready:
            raise CanonicalSessionError("session dependency graph contains a cycle")
        for job_id in ready:
            remaining.pop(job_id)
            done.add(job_id)

    return {
        "schema": SESSION_SCHEMA,
        "session_id": session_id,
        "budget_seconds": budget_seconds,
        "reserve_seconds": reserve_seconds,
        "max_parallel": max_parallel,
        "jobs": jobs,
    }


def _load_json(path: Path) -> dict:
    try:
        node = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CanonicalSessionError(f"invalid JSON: {path}") from exc
    if not isinstance(node, dict):
        raise CanonicalSessionError(f"JSON root must be object: {path}")
    return node


def _session_fingerprint(session: dict) -> str:
    return dispatch.sha(session)


def _request_path(receipt_dir: Path, session_id: str, job_id: str) -> Path:
    return receipt_dir / "session-inputs" / session_id / f"{job_id}.json"


def _write_request(path: Path, request: dict) -> None:
    dispatch.atomic(path, request)


def _invoke_job(
    job: dict,
    *,
    session_id: str,
    source_root: Path,
    source_receipt_path: Path,
    receipt_dir: Path,
    dispatcher_path: Path,
    input_root: Path | None,
) -> dict:
    request_path = _request_path(receipt_dir, session_id, job["job_id"])
    _write_request(request_path, job["request"])

    command = [
        sys.executable,
        str(dispatcher_path),
        "run",
        "--request",
        str(request_path),
        "--source-root",
        str(source_root),
        "--source-receipt",
        str(source_receipt_path),
        "--receipt-dir",
        str(receipt_dir),
    ]
    if input_root is not None:
        command.extend(["--input-root", str(input_root)])

    started = time.time()
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
            timeout=job["max_wall_seconds"],
        )
    except subprocess.TimeoutExpired as exc:
        stderr = (exc.stderr or "").encode("utf-8") if isinstance(exc.stderr, str) else (exc.stderr or b"")
        return {
            "state": "failed",
            "cache_hit": False,
            "error_class": "wall_timeout",
            "max_wall_seconds": job["max_wall_seconds"],
            "elapsed_seconds": round(time.time() - started, 6),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        }

    elapsed = round(time.time() - started, 6)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode != 0:
        return {
            "state": "failed",
            "cache_hit": False,
            "error_class": f"dispatcher_exit_{completed.returncode}",
            "elapsed_seconds": elapsed,
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        }
    try:
        payload = json.loads(stdout.strip().splitlines()[-1])
        receipt = payload["receipt"]
        cache_hit = payload.get("cache_hit") is True
    except Exception:
        return {
            "state": "failed",
            "cache_hit": False,
            "error_class": "dispatcher_output_invalid",
            "elapsed_seconds": elapsed,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        }
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != dispatch.RECEIPT_SCHEMA
        or receipt.get("job_id") != job["job_id"]
        or receipt.get("status") != "completed"
    ):
        return {
            "state": "failed",
            "cache_hit": False,
            "error_class": "dispatcher_receipt_invalid",
            "elapsed_seconds": elapsed,
        }
    return {
        "state": "cached" if cache_hit else "completed",
        "cache_hit": cache_hit,
        "job_fingerprint": receipt.get("job_fingerprint"),
        "receipt_sha256": dispatch.sha(receipt),
        "result_sha256": receipt.get("result_sha256"),
        "elapsed_seconds": elapsed,
    }


def execute_session(
    session_node: dict,
    *,
    source_root: Path,
    source_receipt_path: Path,
    receipt_dir: Path,
    dispatcher_path: Path | None = None,
    input_root: Path | None = None,
) -> dict:
    session = validate_session(session_node)
    receipt_dir = receipt_dir.resolve()
    source_root = source_root.resolve()
    source_receipt_path = source_receipt_path.resolve()
    dispatcher_path = (dispatcher_path or Path(dispatch.__file__)).resolve()
    input_root = input_root.resolve() if input_root is not None else None

    if not source_root.is_dir():
        raise CanonicalSessionError("source_root does not exist")
    if not source_receipt_path.is_file():
        raise CanonicalSessionError("source_receipt does not exist")
    if not dispatcher_path.is_file():
        raise CanonicalSessionError("dispatcher_path does not exist")

    fingerprint = _session_fingerprint(session)
    state_path = receipt_dir / "sessions" / f"{session['session_id']}.json"
    previous = _load_json(state_path) if state_path.is_file() else None
    if previous is not None and previous.get("session_fingerprint") != fingerprint:
        raise CanonicalSessionError("session_id already exists with different fingerprint")

    started_at = (
        float(previous.get("started_at_epoch"))
        if previous and previous.get("started_at_epoch") is not None
        else time.time()
    )
    deadline = started_at + session["budget_seconds"]
    previous_jobs = previous.get("jobs") if isinstance(previous, dict) else {}
    states: dict[str, dict] = {}
    if isinstance(previous_jobs, dict):
        for job_id, state in previous_jobs.items():
            if isinstance(state, dict) and state.get("state") in {"completed", "cached"}:
                states[job_id] = dict(state)

    jobs = {job["job_id"]: job for job in session["jobs"]}
    pending = {job_id for job_id in jobs if job_id not in states}
    waves: list[dict[str, Any]] = []
    if previous and isinstance(previous.get("waves"), list):
        waves.extend(previous["waves"])

    def checkpoint(status: str) -> dict:
        now = time.time()
        out = {
            "schema": SESSION_RECEIPT_SCHEMA,
            "session_id": session["session_id"],
            "session_fingerprint": fingerprint,
            "status": status,
            "started_at_epoch": started_at,
            "deadline_epoch": deadline,
            "updated_at_epoch": now,
            "budget_seconds": session["budget_seconds"],
            "reserve_seconds": session["reserve_seconds"],
            "remaining_seconds": round(max(0.0, deadline - now), 6),
            "max_parallel": session["max_parallel"],
            "waves": waves,
            "jobs": {job_id: states[job_id] for job_id in sorted(states)},
            "authority": {
                "research_only": True,
                **dispatch.FORBIDDEN_AUTHORITY_ASSERTIONS,
            },
        }
        dispatch.atomic(state_path, out)
        return out

    checkpoint("running")

    while pending:
        failed = {
            job_id
            for job_id, state in states.items()
            if state.get("state") in {"failed", "blocked"}
        }
        for job_id in list(pending):
            bad = [dep for dep in jobs[job_id]["depends_on"] if dep in failed]
            if bad:
                states[job_id] = {
                    "state": "blocked",
                    "cache_hit": False,
                    "blocked_by": sorted(bad),
                }
                pending.remove(job_id)

        if not pending:
            break

        good = {
            job_id
            for job_id, state in states.items()
            if state.get("state") in {"completed", "cached"}
        }
        ready = [
            jobs[job_id]
            for job_id in pending
            if set(jobs[job_id]["depends_on"]) <= good
        ]
        ready.sort(
            key=lambda job: (
                -job["priority"],
                job["max_wall_seconds"],
                job["job_id"],
            )
        )
        if not ready:
            break

        now = time.time()
        usable = deadline - now - session["reserve_seconds"]
        eligible = [job for job in ready if job["max_wall_seconds"] <= usable]
        if not eligible:
            for job in ready:
                states[job["job_id"]] = {
                    "state": "deferred_budget",
                    "cache_hit": False,
                    "priority": job["priority"],
                    "required_wall_seconds": job["max_wall_seconds"],
                    "usable_budget_seconds": round(max(0.0, usable), 6),
                }
                pending.remove(job["job_id"])
            continue

        selected = eligible[: session["max_parallel"]]
        wave = {
            "wave": len(waves) + 1,
            "started_at_epoch": time.time(),
            "remaining_before_seconds": round(max(0.0, deadline - time.time()), 6),
            "jobs": [
                {
                    "job_id": job["job_id"],
                    "priority": job["priority"],
                    "max_wall_seconds": job["max_wall_seconds"],
                }
                for job in selected
            ],
        }
        waves.append(wave)
        for job in selected:
            states[job["job_id"]] = {
                "state": "running",
                "cache_hit": False,
                "priority": job["priority"],
            }
        checkpoint("running")

        with ThreadPoolExecutor(max_workers=len(selected)) as pool:
            future_to_job = {
                pool.submit(
                    _invoke_job,
                    job,
                    session_id=session["session_id"],
                    source_root=source_root,
                    source_receipt_path=source_receipt_path,
                    receipt_dir=receipt_dir,
                    dispatcher_path=dispatcher_path,
                    input_root=input_root,
                ): job
                for job in selected
            }
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "state": "failed",
                        "cache_hit": False,
                        "error_class": f"session_worker_{type(exc).__name__}",
                    }
                result["priority"] = job["priority"]
                states[job["job_id"]] = result
                pending.discard(job["job_id"])

        wave["completed_at_epoch"] = time.time()
        wave["results"] = {
            job["job_id"]: states[job["job_id"]]["state"]
            for job in selected
        }
        checkpoint("running")

    terminal_states = {state.get("state") for state in states.values()}
    if len(states) == len(jobs) and terminal_states <= {"completed", "cached"}:
        status = "completed"
    elif "deferred_budget" in terminal_states:
        status = "budget_exhausted"
    elif terminal_states & {"failed", "blocked"}:
        status = "failed"
    else:
        status = "incomplete"
    return checkpoint(status)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--source-receipt", required=True, type=Path)
    parser.add_argument("--receipt-dir", required=True, type=Path)
    parser.add_argument("--dispatcher", type=Path)
    parser.add_argument("--input-root", type=Path)
    args = parser.parse_args()

    try:
        out = execute_session(
            _load_json(args.session),
            source_root=args.source_root,
            source_receipt_path=args.source_receipt,
            receipt_dir=args.receipt_dir,
            dispatcher_path=args.dispatcher,
            input_root=args.input_root,
        )
        print(json.dumps(out, sort_keys=True))
        return 0 if out["status"] in {"completed", "budget_exhausted"} else 2
    except (CanonicalSessionError, dispatch.CanonicalDispatchError) as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
