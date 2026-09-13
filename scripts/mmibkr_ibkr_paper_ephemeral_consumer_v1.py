from __future__ import annotations

"""Fixed public-compute consumer for one explicitly approved MM-IBKR paper order.

This consumer never calls IB placeOrder itself. It boots the pinned MM-IBKR bot and
invokes the repository's canonical /strategy/ibkr-paper-order-submit route. The
remote harness adds stricter first-proof bounds: paper mode only, one LMT order,
quantity <= 1, stable idempotency key, no inactive-session override and no short
sell override. Natural selected-runtime candidate submission is disabled while the
one-shot control API is active so this process cannot create unrelated paper orders.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

from mmibkr_ephemeral_scoped_v1 import decrypt_assembled_ciphertext

ENVELOPE_SCHEMA = "mmibkr-ibkr-paper-ephemeral-x25519-v1"
PRIVATE_SCHEMA = "mmibkr-ibkr-paper-private-input-v1"
ORDER_SCHEMA = "mmibkr-ibkr-paper-order-request-v1"
AUTHORITY = "paper_execution_only"
HARNESS = "mmibkr_ibkr_canonical_paper_submit_v1"
SOURCE_REPO = "XoticHaze/mm-IBKR"
SOURCE_SHA = "5d1607f85359f4c35b2c40973086f059efeebfbe"
GATEWAY_IMAGE = "ghcr.io/gnzsnz/ib-gateway:10.49.1c"
PRIVATE_FIELDS = {
    "schema",
    "source_read_token",
    "tws_userid",
    "tws_password",
    "tws_userid_paper",
    "tws_password_paper",
    "order_request",
}
ORDER_FIELDS = {
    "schema",
    "idempotency_key",
    "symbol",
    "action",
    "quantity",
    "limit_price",
    "tif",
    "reason",
    "operator_approved",
    "ibkr_paper_order_submit_ack_13z53",
}
ALLOWED_SYMBOLS = {"AMAT", "APH", "MNQ"}


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 1800,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env=env,
    )


def _must(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1][:240] if detail else f"rc={proc.returncode}"
        raise RuntimeError(f"{label} failed: {tail}")


def _load_private(plaintext: bytes) -> tuple[dict[str, str], dict[str, Any]]:
    try:
        node = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("MM-IBKR paper private input is not valid UTF-8 JSON") from exc
    if not isinstance(node, dict) or set(node) != PRIVATE_FIELDS:
        raise RuntimeError("MM-IBKR paper private input field set mismatch")
    if node.get("schema") != PRIVATE_SCHEMA:
        raise RuntimeError("MM-IBKR paper private input schema mismatch")
    for key in ("source_read_token", "tws_userid", "tws_password"):
        if not isinstance(node.get(key), str) or not node[key].strip():
            raise RuntimeError(f"MM-IBKR paper private input missing {key}")
    for key in ("tws_userid_paper", "tws_password_paper"):
        if not isinstance(node.get(key), str):
            raise RuntimeError(f"MM-IBKR paper private input invalid {key}")
    order = node.get("order_request")
    if not isinstance(order, dict) or set(order) != ORDER_FIELDS:
        raise RuntimeError("MM-IBKR paper order request field set mismatch")
    _validate_order(order)
    private = {k: str(node[k]) for k in PRIVATE_FIELDS if k != "order_request"}
    return private, dict(order)


def _validate_order(order: dict[str, Any]) -> None:
    if order.get("schema") != ORDER_SCHEMA:
        raise RuntimeError("MM-IBKR paper order request schema mismatch")
    key = str(order.get("idempotency_key") or "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{8,64}", key):
        raise RuntimeError("MM-IBKR paper idempotency_key must be 8-64 safe characters")
    symbol = str(order.get("symbol") or "").upper()
    if symbol not in ALLOWED_SYMBOLS:
        raise RuntimeError("MM-IBKR first-proof paper symbol is not admitted")
    action = str(order.get("action") or "").upper()
    if action not in {"BUY", "SELL"}:
        raise RuntimeError("MM-IBKR paper action must be BUY or SELL")
    try:
        quantity = float(order.get("quantity"))
        limit_price = float(order.get("limit_price"))
    except Exception as exc:
        raise RuntimeError("MM-IBKR paper quantity/limit_price must be numeric") from exc
    if not (0 < quantity <= 1):
        raise RuntimeError("MM-IBKR first-proof paper quantity must be >0 and <=1")
    if limit_price <= 0:
        raise RuntimeError("MM-IBKR first-proof paper limit_price must be positive")
    if str(order.get("tif") or "").upper() not in {"DAY", "GTC"}:
        raise RuntimeError("MM-IBKR paper tif must be DAY or GTC")
    if order.get("operator_approved") is not True:
        raise RuntimeError("MM-IBKR paper operator_approved must be true")
    if str(order.get("ibkr_paper_order_submit_ack_13z53") or "") != "IBKR_PAPER_ORDER_SUBMIT_ACK_13Z53":
        raise RuntimeError("MM-IBKR canonical paper submit ACK missing")


def _clone_pinned(private: dict[str, str], root: Path) -> Path:
    repo = root / "mmibkr"
    cred = root / "git-credentials"
    gitconfig = root / "gitconfig"
    token = urllib.parse.quote(private["source_read_token"], safe="")
    cred.write_text(f"https://x-access-token:{token}@github.com\n", encoding="utf-8")
    os.chmod(cred, 0o600)
    gitconfig.write_text(f"[credential]\n\thelper = store --file={cred}\n", encoding="utf-8")
    os.chmod(gitconfig, 0o600)
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = _run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", f"https://github.com/{SOURCE_REPO}.git", str(repo)],
            timeout=600,
            env=env,
        )
        _must(proc, "private paper source clone")
        proc = _run(["git", "-C", str(repo), "checkout", "--detach", SOURCE_SHA], timeout=600, env=env)
        _must(proc, "pinned paper source checkout")
    finally:
        cred.unlink(missing_ok=True)
        gitconfig.unlink(missing_ok=True)

    head = _run(["git", "rev-parse", "HEAD"], cwd=repo, timeout=30)
    _must(head, "paper source identity")
    if head.stdout.strip() != SOURCE_SHA:
        raise RuntimeError("MM-IBKR paper source SHA mismatch")
    dirty = _run(["git", "status", "--porcelain"], cwd=repo, timeout=30)
    _must(dirty, "paper source cleanliness")
    if dirty.stdout.strip():
        raise RuntimeError("MM-IBKR paper source checkout is not clean")
    if not (repo / "main.py").is_file() or not (repo / "docker-compose.yml").is_file():
        raise RuntimeError("MM-IBKR pinned paper source missing control API files")
    return repo


def _write_gateway_env(repo: Path, private: dict[str, str]) -> Path:
    path = repo / "ibkr-gateway" / ".env.ibkr"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = {
        "TWS_USERID": private["tws_userid"],
        "TWS_PASSWORD": private["tws_password"],
        "TWS_USERID_PAPER": private["tws_userid_paper"],
        "TWS_PASSWORD_PAPER": private["tws_password_paper"],
        "TRADING_MODE": "paper",
        "READ_ONLY_API": "no",
        "TWS_ACCEPT_INCOMING": "accept",
        "TWOFA_TIMEOUT_ACTION": "exit",
        "ENABLE_VNC": "false",
    }
    if any("\n" in value or "\r" in value for value in rows.values()):
        raise RuntimeError("MM-IBKR gateway private input contains newline")
    path.write_text("".join(f"{key}={value}\n" for key, value in rows.items()), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _write_override(repo: Path) -> Path:
    path = repo / "docker-compose.remote-paper-r1.yml"
    path.write_text(
        "services:\n"
        "  bot:\n"
        "    environment:\n"
        "      ENABLE_LIVE_TRADING: '0'\n"
        "      STRATEGY_AUTO_START_LOOPS_ENABLED: 'false'\n"
        "      BOT_SELECTED_RUNTIME_NATURAL_CANDIDATE_14TH31BV_ENABLED: '0'\n"
        "      FUTURES_AUTO_ENABLED: '0'\n"
        "      STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53: '1'\n"
        "      CONTROL_RUNTIME_PORT: '8001'\n",
        encoding="utf-8",
    )
    return path


def _compose(repo: Path, project: str, override: Path, *args: str, timeout: int = 1800, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return _run(
        ["docker", "compose", "-p", project, "-f", "docker-compose.yml", "-f", override.name, *args],
        cwd=repo,
        timeout=timeout,
        input_text=input_text,
    )


def _wait_service(repo: Path, project: str, override: Path, service: str, timeout_sec: int) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        q = _compose(repo, project, override, "ps", "-q", service, timeout=30)
        if q.returncode == 0 and q.stdout.strip():
            cid = q.stdout.strip().splitlines()[0]
            health = _run(["docker", "inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", cid], timeout=15)
            if health.returncode == 0 and health.stdout.strip() == "healthy":
                return
        time.sleep(5)
    raise RuntimeError(f"MM-IBKR {service} did not become ready")


def _call_bot(repo: Path, project: str, override: Path, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    code = r'''import json,sys,urllib.request,urllib.error
payload=sys.stdin.read().encode()
req=urllib.request.Request('http://127.0.0.1:8001'+sys.argv[1],data=payload,headers={'content-type':'application/json'},method='POST')
try:
    with urllib.request.urlopen(req,timeout=30) as r:
        print(json.dumps({'status_code':r.status,'body':json.loads(r.read().decode())},separators=(',',':')))
except urllib.error.HTTPError as e:
    raw=e.read().decode()
    try: body=json.loads(raw)
    except Exception: body={'error':'non_json_http_error'}
    print(json.dumps({'status_code':e.code,'body':body},separators=(',',':')))
'''
    proc = _compose(
        repo,
        project,
        override,
        "exec",
        "-T",
        "bot",
        "python",
        "-c",
        code,
        path,
        timeout=60,
        input_text=json.dumps(payload, separators=(",", ":")),
    )
    _must(proc, f"bot route {path}")
    node = json.loads(proc.stdout.strip().splitlines()[-1])
    return int(node.get("status_code") or 0), dict(node.get("body") or {})


def _canonical_payload(order: dict[str, Any]) -> dict[str, Any]:
    key = str(order["idempotency_key"])
    return {
        "symbol": str(order["symbol"]).upper(),
        "action": str(order["action"]).upper(),
        "quantity": float(order["quantity"]),
        "order_type": "LMT",
        "limit_price": float(order["limit_price"]),
        "tif": str(order["tif"]).upper(),
        "reason": str(order.get("reason") or "gh_public_compute_paper_proof")[:120],
        "order_ref": f"MMIBKR_GH_{key}",
        "operator_approved": True,
        "ibkr_paper_order_submit_ack_13z53": "IBKR_PAPER_ORDER_SUBMIT_ACK_13Z53",
        "allow_market_order": False,
        "ibkr_paper_market_order_ack_13z53": "",
        "allow_inactive_session": False,
        "allow_short_sell_13z53": False,
        "contract_details_timeout_sec": 12.0,
    }


def _sanitize_submit(body: dict[str, Any], status_code: int) -> dict[str, Any]:
    trade = dict(body.get("trade") or body.get("trade_snapshot") or {})
    order = dict(trade.get("order") or {})
    order_status = dict(trade.get("order_status") or body.get("order_status") or {})
    guards = dict(body.get("guards") or {})
    return {
        "http_status": status_code,
        "ok": bool(body.get("ok")),
        "status": body.get("status"),
        "broker_order_placed": bool(body.get("broker_order_placed")),
        "place_order_called": bool(body.get("place_order_called")),
        "symbol": body.get("symbol") or (body.get("resolved_order") or {}).get("symbol"),
        "blockers": [str(x)[:120] for x in list(body.get("blockers") or [])],
        "warnings": [str(x)[:120] for x in list(body.get("warnings") or [])],
        "guards": {str(k): bool(v) if isinstance(v, bool) else v for k, v in guards.items()},
        "order": {
            "orderId": order.get("orderId"),
            "permId": order.get("permId"),
            "action": order.get("action"),
            "orderType": order.get("orderType"),
            "totalQuantity": order.get("totalQuantity"),
            "lmtPrice": order.get("lmtPrice"),
            "tif": order.get("tif"),
            "orderRef": order.get("orderRef"),
        },
        "order_status": {
            "status": order_status.get("status"),
            "filled": order_status.get("filled"),
            "remaining": order_status.get("remaining"),
            "avgFillPrice": order_status.get("avgFillPrice"),
        },
    }


def execute(private: dict[str, str], order: dict[str, Any], run_id: str) -> dict[str, Any]:
    project = "mmibkrpaper" + hashlib.sha256(str(run_id).encode()).hexdigest()[:10]
    with tempfile.TemporaryDirectory(prefix="mmibkr-paper-") as td:
        root = Path(td)
        repo = _clone_pinned(private, root)
        gateway_env = _write_gateway_env(repo, private)
        override = _write_override(repo)
        canonical = _canonical_payload(order)
        try:
            build = _compose(repo, project, override, "build", "bot", timeout=2400)
            _must(build, "paper bot image build")
            up = _compose(repo, project, override, "up", "-d", "ibgw", "bot", timeout=900)
            _must(up, "paper gateway/bot start")
            _wait_service(repo, project, override, "ibgw", 360)
            _wait_service(repo, project, override, "bot", 360)

            preview_code, preview = _call_bot(repo, project, override, "/strategy/ibkr-paper-order-contract-preview", canonical)
            if preview_code >= 400 or not preview.get("ok") or preview.get("blockers"):
                return {
                    "schema": "mmibkr-ibkr-paper-public-compute-receipt-v1",
                    "authority": AUTHORITY,
                    "harness": HARNESS,
                    "status": "BLOCKED_PREVIEW",
                    "run_id": str(run_id),
                    "source_repo": SOURCE_REPO,
                    "source_sha": SOURCE_SHA,
                    "gateway_image": GATEWAY_IMAGE,
                    "paper_mode_forced": True,
                    "live_trading_change": False,
                    "natural_candidate_execution_disabled": True,
                    "canonical_submit_route": "/strategy/ibkr-paper-order-submit",
                    "idempotency_key": order["idempotency_key"],
                    "order_ref": canonical["order_ref"],
                    "preview_http_status": preview_code,
                    "preview_ok": bool(preview.get("ok")),
                    "preview_blockers": [str(x)[:120] for x in list(preview.get("blockers") or [])],
                    "broker_order_placed": False,
                }

            submit_code, submit = _call_bot(repo, project, override, "/strategy/ibkr-paper-order-submit", canonical)
            sanitized = _sanitize_submit(submit, submit_code)
            return {
                "schema": "mmibkr-ibkr-paper-public-compute-receipt-v1",
                "authority": AUTHORITY,
                "harness": HARNESS,
                "status": "PASS" if sanitized["ok"] and sanitized["broker_order_placed"] else "BLOCKED_OR_FAILED",
                "run_id": str(run_id),
                "source_repo": SOURCE_REPO,
                "source_sha": SOURCE_SHA,
                "gateway_image": GATEWAY_IMAGE,
                "paper_mode_forced": True,
                "live_trading_change": False,
                "natural_candidate_execution_disabled": True,
                "canonical_submit_route": "/strategy/ibkr-paper-order-submit",
                "idempotency_key": order["idempotency_key"],
                "order_ref": canonical["order_ref"],
                "submit": sanitized,
            }
        finally:
            try:
                _compose(repo, project, override, "down", "--remove-orphans", "-v", timeout=240)
            except Exception:
                pass
            gateway_env.unlink(missing_ok=True)
            override.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--ciphertext", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--response-root", required=True)
    args = parser.parse_args()

    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    ciphertext = Path(args.ciphertext).read_bytes()
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=ciphertext,
        private_key_path=Path(args.private_key),
        expected_schema=ENVELOPE_SCHEMA,
        expected_run_id=str(args.run_id),
        expected_authority=AUTHORITY,
        expected_harness=HARNESS,
        response_root=str(args.response_root),
    )
    private, order = _load_private(plaintext)
    try:
        receipt = execute(private, order, str(args.run_id))
    finally:
        private.clear()
        order.clear()
        plaintext = b""
    print("MMIBKR_IBKR_PAPER_RECEIPT=" + json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if receipt["status"] in {"PASS", "BLOCKED_PREVIEW"} else 2)


if __name__ == "__main__":
    main()
