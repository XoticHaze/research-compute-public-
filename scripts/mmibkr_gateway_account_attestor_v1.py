from __future__ import annotations

"""One-owner, loopback-only account identity oracle for pinned SSH readers.

The canonical Gateway owner alone reads its sealed expected-account value.
Authenticated readers send the live account they saw through the *existing*
Cloudflare Access/pinned SSH transport, on a second exact permitted loopback
forward. The oracle answers only match/no-match, never the actual account.
No broker credentials, login, execution, or arbitrary commands in this service.
"""

import argparse
import hmac
import json
from pathlib import Path
import socket
import socketserver
import threading


SCHEMA = "mmibkr.gateway_expected_account_match.v1"
HOST = "127.0.0.1"
PORT = 4002
READER_PORT = 14002
MAX_REQUESTS = 32


def read_expected(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if len(lines) != 1 or not lines[0].startswith("MMIBKR_PRODUCTION_LIVE_ACCOUNT="):
        raise ValueError("exact_owner_account_env_shape_required")
    account = lines[0].partition("=")[2]
    if not account or account.upper().startswith("DU") or len(account) > 24:
        raise ValueError("live_expected_account_required")
    return account


def matched(request: dict, *, run_id: str, expected: str) -> bool:
    if not isinstance(request, dict) or set(request) != {"schema", "gateway_run_id", "candidate"}:
        return False
    candidate = request.get("candidate")
    if not isinstance(candidate, str) or not 1 <= len(candidate) <= 24:
        return False
    if candidate.upper().startswith("DU"):
        return False
    return (
        request.get("schema") == SCHEMA
        and request.get("gateway_run_id") == run_id
        and hmac.compare_digest(candidate, expected)
    )


class AccountOracle(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], *, expected: str, run_id: str):
        self.expected = expected
        self.run_id = run_id
        self._requests = 0
        self._lock = threading.Lock()
        super().__init__(address, OracleHandler)


class OracleHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(4)
        try:
            raw = self.rfile.readline(257)
            if not raw.endswith(b"\n") or len(raw) > 256:
                return
            request = json.loads(raw)
            with self.server._lock:
                self.server._requests += 1
                under_limit = self.server._requests <= MAX_REQUESTS
            ok = under_limit and matched(
                request, run_id=self.server.run_id, expected=self.server.expected
            )
            reply = {"schema": SCHEMA, "gateway_run_id": self.server.run_id, "match": ok}
            self.wfile.write((json.dumps(reply, separators=(",", ":")) + "\n").encode())
        except (OSError, ValueError, TypeError):
            # Never log a candidate account or return the expected value.
            return


def attest_account(candidate: str, run_id: str, *, port: int = READER_PORT) -> None:
    if not run_id.isascii() or not run_id.isdigit():
        raise RuntimeError("account_attestor_exact_owner_run_required")
    request = {"schema": SCHEMA, "gateway_run_id": run_id, "candidate": candidate}
    with socket.create_connection((HOST, port), timeout=7) as sock:
        sock.settimeout(7)
        sock.sendall((json.dumps(request, separators=(",", ":")) + "\n").encode())
        with sock.makefile("rb") as stream:
            raw = stream.readline(512)
    if len(raw) > 511 or not raw.endswith(b"\n"):
        raise RuntimeError("account_attestor_response_invalid")
    try:
        response = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("account_attestor_response_invalid") from exc
    if not isinstance(response, dict) or response != {
        "schema": SCHEMA, "gateway_run_id": run_id, "match": True
    }:
        raise RuntimeError("gateway_pool_expected_live_account_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-env", required=True)
    parser.add_argument("--gateway-run-id", required=True)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    if args.port != PORT or not args.gateway_run_id.isascii() or not args.gateway_run_id.isdigit():
        raise SystemExit("account_attestor_exact_owner_scope_required")
    expected = read_expected(Path(args.expected_env))
    with AccountOracle((HOST, PORT), expected=expected, run_id=args.gateway_run_id) as server:
        print("MMIBKR_GATEWAY_ACCOUNT_ATTESTOR_LOOPBACK_ONLY=1", flush=True)
        server.serve_forever(poll_interval=0.25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
