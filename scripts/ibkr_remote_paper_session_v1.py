from __future__ import annotations

"""Fixed paper-session reconciliation driver for the remote MM-IBKR runtime.

This R1 driver is intentionally read-only. It proves that the private MM-IBKR
source can boot against the ephemeral paper gateway and read broker truth through
its existing canonical control surface. It never calls submit/cancel/flatten.
"""

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _json_request(url: str, *, method: str = "GET", payload: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            status = int(response.getcode())
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body) if body.strip() else {}
    except Exception:
        parsed = {"ok": False, "error": "non_json_response"}
    return status, parsed if isinstance(parsed, dict) else {"ok": False, "raw_type": type(parsed).__name__}


def build_receipt(*, run_id: str, job: str, public_head: str, runtime: dict, health: tuple[int, dict], open_orders: tuple[int, dict], positions: tuple[int, dict]) -> dict:
    health_status, health_body = health
    open_status, open_body = open_orders
    pos_status, pos_body = positions
    account_identity = open_body.get("account_identity") if isinstance(open_body.get("account_identity"), dict) else {}

    paper_account_ok = bool(account_identity.get("selected_account_is_paper_du")) and int(account_identity.get("du_account_count") or 0) == 1
    broker_reads_ok = bool(open_status == 200 and open_body.get("ok") is True and pos_status == 200 and pos_body.get("ok") is True)
    session_ready = bool(health_status == 200 and broker_reads_ok and paper_account_ok)

    return {
        "schema": "mm-ibkr-remote-paper-session-receipt-v1",
        "ok": session_ready,
        "status": "REMOTE_PAPER_SESSION_RECONCILED" if session_ready else "REMOTE_PAPER_SESSION_NOT_READY",
        "github": {
            "run_id": str(run_id),
            "job": str(job),
            "public_head": str(public_head),
        },
        "mmibkr": {
            "repository": runtime.get("mmibkr_repository"),
            "head": runtime.get("mmibkr_head"),
            "source_archive_sha256": runtime.get("source_archive_sha256"),
        },
        "mode": runtime.get("mode"),
        "paper_only": runtime.get("paper_only") is True,
        "read_only_api": runtime.get("read_only_api") == "yes",
        "host_dependency": runtime.get("host_dependency") is True,
        "live_trading_change": runtime.get("live_trading_change") is True,
        "broker_session": {
            "health_http_status": health_status,
            "health_ok": health_body.get("ok") is not False,
            "open_orders_http_status": open_status,
            "open_orders_ok": open_body.get("ok") is True,
            "positions_http_status": pos_status,
            "positions_ok": pos_body.get("ok") is True,
            "managed_account_count": int(account_identity.get("managed_account_count") or 0),
            "du_account_count": int(account_identity.get("du_account_count") or 0),
            "single_paper_du_account": paper_account_ok,
            "open_order_count": int(open_body.get("open_order_count") or 0),
            "unresolved_open_order_count": int(open_body.get("unresolved_open_order_count") or 0),
            "position_count": int(pos_body.get("position_count") or 0),
        },
        "side_effects": {
            "submit_called": False,
            "cancel_called": False,
            "flatten_called": False,
            "broker_order_placed": False,
        },
        "secrets_published": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--public-head", required=True)
    args = parser.parse_args()

    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
    if runtime.get("mode") != "session_reconcile" or runtime.get("read_only_api") != "yes":
        raise SystemExit("R1 session driver admits only session_reconcile with READ_ONLY_API=yes")

    base = args.base_url.rstrip("/")
    health = _json_request(base + "/healthz", timeout=15)
    open_orders = _json_request(base + "/strategy/ibkr-paper-open-orders", timeout=45)
    positions = _json_request(
        base + "/strategy/ibkr-paper-flatten-preview-suite",
        method="POST",
        payload={"candidate_limit": 50, "preview_limit": 1, "batch_limit": 1},
        timeout=60,
    )
    receipt = build_receipt(
        run_id=args.run_id,
        job=args.job,
        public_head=args.public_head,
        runtime=runtime,
        health=health,
        open_orders=open_orders,
        positions=positions,
    )
    out = Path(args.receipt)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("IBKR_REMOTE_PAPER_SESSION=" + json.dumps(receipt, sort_keys=True))
    if not receipt["ok"]:
        raise SystemExit(43)


if __name__ == "__main__":
    main()
