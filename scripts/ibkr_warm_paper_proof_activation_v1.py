from __future__ import annotations

"""Join the accepted warm Gateway lifecycle to one MM-authorized paper proof.

This module does not own strategy intent, sizing, contract selection, execution
policy, broker credentials, or live authority.  It performs two narrow phases:

``prepare``
    Mint and publish the run-bound X25519 recipient used by private MM-IBKR to
    send one credential-free selected-runtime command capsule.

``execute``
    Wait for that exact capsule, decrypt/materialize its exact private MM-IBKR
    source, build the canonical bot target, run the already-validated HTTP-only
    proof driver against the *existing* authenticated warm Gateway, encrypt the
    proof receipt to the private one-run return recipient, publish encrypted
    return chunks, and destroy the private source/runtime material.

The surrounding admitted workflow remains responsible for Fleet Authority,
controller-native warm-state restore, Gateway startup, graceful stop, reseal,
and final runner cleanup.
"""

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

import ibkr_remote_paper_proof_return_v1 as proof_return
import ibkr_remote_selected_runtime_command_capsule_v2 as command_capsule
import ibkr_remote_selected_runtime_paper_proof_v1 as proof_v1
import ibkr_remote_selected_runtime_paper_proof_v2 as proof_v2
from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

EXCHANGE_REF = "rendezvous-exchange"
RECIPIENT_ROOT = "rendezvous/recipients"
RESPONSE_ROOT = "rendezvous/responses"
RETURN_ROOT = "rendezvous/returns"
COMMAND_RECIPIENT_SCHEMA = "ibkr-remote-paper-recipient-v1"
ACTIVATION_SCHEMA = "mmibkr.ibkr_warm_paper_proof_activation.v1"
BOT_CONTAINER = "mmibkr-remote-bot"


def _safe_run_id(value: Any) -> str:
    run_id = str(value or "").strip()
    if not run_id.isdigit():
        raise RuntimeError("numeric GitHub run id required")
    return run_id


def _api_url(repository: str, path: str, *, ref: str | None = None) -> str:
    base = f"https://api.github.com/repos/{repository}/contents/{quote(path, safe='/')}"
    return base if not ref else base + "?ref=" + quote(ref, safe="")


def _github_raw(token: str, repository: str, path: str, *, ref: str) -> bytes:
    req = Request(
        _api_url(repository, path, ref=ref),
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github.raw+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(req, timeout=30) as response:
        return response.read()


def _publish_new_text(token: str, repository: str, path: str, text: str, *, branch: str, message: str) -> None:
    raw = text.encode("utf-8")
    body = json.dumps(
        {
            "message": message,
            "content": base64.b64encode(raw).decode("ascii"),
            "branch": branch,
        }
    ).encode("utf-8")
    req = Request(
        _api_url(repository, path),
        data=body,
        method="PUT",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(req, timeout=30) as response:
            if int(response.status) not in {200, 201}:
                raise RuntimeError(f"GitHub publish failed with HTTP {response.status}")
    except HTTPError as exc:
        if exc.code == 422:
            raise RuntimeError(f"run-bound rendezvous path already exists: {path}") from exc
        raise


def generate_command_recipient(*, run_id: str, private_key_path: Path) -> dict[str, str]:
    run_id = _safe_run_id(run_id)
    private = x25519.X25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key_path.write_text(base64.b64encode(private_raw).decode("ascii") + "\n", encoding="ascii")
    try:
        os.chmod(private_key_path, 0o600)
    except OSError:
        pass
    return {
        "schema": COMMAND_RECIPIENT_SCHEMA,
        "run_id": run_id,
        "recipient_b64": base64.b64encode(public_raw).decode("ascii"),
        "recipient_key_id": "sha256:" + hashlib.sha256(public_raw).hexdigest(),
        "authority": command_capsule.AUTHORITY,
        "harness": command_capsule.HARNESS,
    }


def prepare_command_exchange(*, token: str, repository: str, run_id: str, runner_temp: Path, exchange_ref: str = EXCHANGE_REF) -> dict[str, Any]:
    run_id = _safe_run_id(run_id)
    private_key_path = runner_temp / "ibkr-remote-private.b64"
    recipient = generate_command_recipient(run_id=run_id, private_key_path=private_key_path)
    recipient_path = f"{RECIPIENT_ROOT}/{run_id}-ibkr-remote-paper.json"
    _publish_new_text(
        token,
        repository,
        recipient_path,
        json.dumps(recipient, sort_keys=True) + "\n",
        branch=exchange_ref,
        message="rendezvous: publish one-run warm IBKR paper recipient",
    )
    return {
        "schema": ACTIVATION_SCHEMA,
        "phase": "prepare",
        "run_id": run_id,
        "recipient_path": recipient_path,
        "recipient_key_id": recipient["recipient_key_id"],
        "private_key_path": str(private_key_path),
        "paper_only": True,
        "gateway_auth_source": "fleet_authority_warm_state",
        "broker_action": False,
    }


def _wait_for_command_envelope(*, token: str, repository: str, run_id: str, exchange_ref: str, timeout_sec: int) -> tuple[dict[str, Any], bytes]:
    run_id = _safe_run_id(run_id)
    response_root = f"{RESPONSE_ROOT}/{run_id}"
    envelope_path = f"{response_root}/ibkr-remote-paper-envelope.json"
    deadline = time.time() + max(5, int(timeout_sec))
    raw: bytes | None = None
    while time.time() < deadline:
        try:
            raw = _github_raw(token, repository, envelope_path, ref=exchange_ref)
            break
        except HTTPError as exc:
            if exc.code != 404:
                raise
            time.sleep(5)
    if raw is None:
        raise RuntimeError("run-bound selected-runtime command capsule did not arrive")
    envelope = json.loads(raw.decode("utf-8"))
    chunks = envelope.get("chunks") if isinstance(envelope, Mapping) else None
    if not isinstance(chunks, list) or not chunks or len(chunks) > 64:
        raise RuntimeError("selected-runtime command chunk manifest invalid")
    prefix = response_root.rstrip("/") + "/"
    pieces: list[str] = []
    seen: set[str] = set()
    for node in chunks:
        if not isinstance(node, Mapping) or set(node) != {"path", "sha256", "chars"}:
            raise RuntimeError("selected-runtime command chunk descriptor invalid")
        path = str(node["path"])
        if not path.startswith(prefix) or path in seen or ".." in path.split("/"):
            raise RuntimeError("selected-runtime command chunk path rejected")
        seen.add(path)
        chunk_raw = _github_raw(token, repository, path, ref=exchange_ref)
        if len(chunk_raw) != int(node["chars"]) or hashlib.sha256(chunk_raw).hexdigest() != str(node["sha256"]):
            raise RuntimeError("selected-runtime command chunk identity mismatch")
        pieces.append(chunk_raw.decode("ascii"))
    ciphertext = base64.b64decode("".join(pieces).encode("ascii"), validate=True)
    if hashlib.sha256(ciphertext).hexdigest() != str(envelope.get("ciphertext_sha256") or ""):
        raise RuntimeError("selected-runtime command assembled ciphertext digest mismatch")
    return dict(envelope), ciphertext


def materialize_command(*, envelope: Mapping[str, Any], ciphertext: bytes, run_id: str, runner_temp: Path) -> dict[str, Any]:
    private_key_path = runner_temp / "ibkr-remote-private.b64"
    if not private_key_path.is_file():
        raise RuntimeError("run-bound command private key missing")
    plaintext = decrypt_assembled_ciphertext(
        envelope=dict(envelope),
        ciphertext=ciphertext,
        private_key_path=private_key_path,
        expected_schema=command_capsule.ENVELOPE_SCHEMA,
        expected_run_id=_safe_run_id(run_id),
        expected_harness=command_capsule.HARNESS,
        response_root=f"{RESPONSE_ROOT}/{run_id}",
        expected_authority=command_capsule.AUTHORITY,
    )
    capsule = command_capsule.validate_capsule(plaintext)
    runtime = command_capsule.materialize(capsule, runner_temp=runner_temp)
    proof_v2.validate_fleet_authority_runtime(runtime)
    return runtime


def canonical_bot_environment() -> dict[str, str]:
    """Only route enablement lives here; all operator acks remain in the command."""
    return {
        "IB_HOST": "127.0.0.1",
        "IB_PORT": "4004",
        "CLIENT_ID": "84",
        "ENABLE_LIVE_TRADING": "0",
        "CONTROL_API_ENABLED": "true",
        "CONTROL_API_HOST": "0.0.0.0",
        "CONTROL_API_PORT": "8001",
        "CONTROL_RUNTIME_PORT": "8001",
        "BOT_SELECTED_RUNTIME_NATURAL_CANDIDATE_14TH31BV_ENABLED": "0",
        "FUTURES_AUTO_ENABLED": "0",
        "STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53": "1",
        "STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37": "1",
        "STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D": "0",
        "STRATEGY_IBKR_PAPER_FLATTEN_ENABLED_13Z39": "1",
    }


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _build_and_start_bot(*, runtime: Mapping[str, Any], run_id: str, runner_temp: Path, gateway_container: str) -> tuple[str, Path]:
    source_root = Path(str(runtime.get("source_root") or ""))
    if not source_root.is_dir():
        raise RuntimeError("materialized MM-IBKR source root missing")
    image = f"mmibkr-remote:{run_id}"
    _run(["docker", "build", "--target", "bot", "-t", image, str(source_root)])
    data_root = runner_temp / "mmibkr-data"
    data_root.mkdir(parents=True, exist_ok=True)
    _run(["docker", "rm", "-f", BOT_CONTAINER], check=False)
    args = [
        "docker", "run", "-d", "--name", BOT_CONTAINER,
        "--network", f"container:{gateway_container}",
    ]
    for key, value in canonical_bot_environment().items():
        args.extend(["-e", f"{key}={value}"])
    args.extend(["-v", f"{data_root}:/app/data", image])
    _run(args)
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            status, body = proof_v1._http_json("http://127.0.0.1:8001", "GET", "/healthz", timeout=4.0)
            if status == 200 and body.get("ok") is not False:
                return image, data_root
        except Exception:
            pass
        time.sleep(3)
    logs = _run(["docker", "logs", BOT_CONTAINER], check=False).stdout[-4000:]
    raise RuntimeError("canonical MM-IBKR control runtime did not become healthy: " + logs)


def _publish_encrypted_return(*, token: str, repository: str, run_id: str, envelope: Mapping[str, Any], output_dir: Path, exchange_ref: str) -> None:
    prefix = f"{RETURN_ROOT}/{run_id}/"
    chunks = envelope.get("chunks") if isinstance(envelope, Mapping) else None
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError("encrypted proof return chunk manifest missing")
    for node in chunks:
        if not isinstance(node, Mapping) or set(node) != {"path", "local_name", "sha256", "chars"}:
            raise RuntimeError("encrypted proof return chunk descriptor invalid")
        remote_path = str(node["path"])
        local_name = str(node["local_name"])
        if not remote_path.startswith(prefix) or ".." in remote_path.split("/") or "/" in local_name:
            raise RuntimeError("encrypted proof return path rejected")
        raw = (output_dir / local_name).read_bytes()
        if len(raw) != int(node["chars"]) or hashlib.sha256(raw).hexdigest() != str(node["sha256"]):
            raise RuntimeError("encrypted proof return local chunk identity mismatch")
        _publish_new_text(
            token,
            repository,
            remote_path,
            raw.decode("ascii"),
            branch=exchange_ref,
            message="rendezvous: publish encrypted selected-runtime proof chunk",
        )
    _publish_new_text(
        token,
        repository,
        f"{RETURN_ROOT}/{run_id}/ibkr-paper-proof-envelope.json",
        json.dumps(dict(envelope), sort_keys=True) + "\n",
        branch=exchange_ref,
        message="rendezvous: publish encrypted selected-runtime proof envelope",
    )


def execute_proof_exchange(
    *,
    token: str,
    repository: str,
    run_id: str,
    public_head: str,
    runner_temp: Path,
    gateway_container: str,
    exchange_ref: str = EXCHANGE_REF,
    wait_timeout_sec: int = 900,
) -> dict[str, Any]:
    run_id = _safe_run_id(run_id)
    envelope, ciphertext = _wait_for_command_envelope(
        token=token,
        repository=repository,
        run_id=run_id,
        exchange_ref=exchange_ref,
        timeout_sec=wait_timeout_sec,
    )
    runtime = materialize_command(
        envelope=envelope,
        ciphertext=ciphertext,
        run_id=run_id,
        runner_temp=runner_temp,
    )
    request = json.loads(Path(str(runtime["request_path"])).read_text(encoding="utf-8"))
    image = f"mmibkr-remote:{run_id}"
    data_root = runner_temp / "mmibkr-data"
    receipt_path = runner_temp / "ibkr-paper-proof-receipt.json"
    encrypted_dir = runner_temp / "ibkr-paper-proof-encrypted"
    summary_path = runner_temp / "ibkr-paper-proof-summary.json"
    try:
        image, data_root = _build_and_start_bot(
            runtime=runtime,
            run_id=run_id,
            runner_temp=runner_temp,
            gateway_container=gateway_container,
        )
        receipt = proof_v2.execute_paper_proof_v2(
            runtime=runtime,
            request=request,
            send=proof_v1._request_sender("http://127.0.0.1:8001"),
            run_id=run_id,
            public_head=public_head,
        )
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        recipient_path = Path(str(runtime.get("return_recipient_path") or ""))
        if runtime.get("encrypted_return_requested") is not True or not recipient_path.is_file():
            raise RuntimeError("selected-runtime proof encrypted return was not materialized")
        recipient = json.loads(recipient_path.read_text(encoding="utf-8"))
        return_envelope = proof_return.encrypt_receipt(
            receipt=receipt,
            runtime=runtime,
            recipient=recipient,
            run_id=run_id,
            output_dir=encrypted_dir,
        )
        _publish_encrypted_return(
            token=token,
            repository=repository,
            run_id=run_id,
            envelope=return_envelope,
            output_dir=encrypted_dir,
            exchange_ref=exchange_ref,
        )
        summary = {
            "schema": ACTIVATION_SCHEMA,
            "phase": "execute",
            "run_id": run_id,
            "ok": receipt.get("ok") is True,
            "status": receipt.get("status"),
            "command_id": (receipt.get("command") or {}).get("command_id"),
            "runtime_id": (receipt.get("command") or {}).get("runtime_id"),
            "symbol": (receipt.get("command") or {}).get("symbol"),
            "exact_cancel_called": bool((receipt.get("cleanup") or {}).get("exact_cancel_called")),
            "flatten_called": bool((receipt.get("cleanup") or {}).get("flatten_called")),
            "global_cancel_called": False,
            "live_execution_allowed": False,
            "gateway_auth_source": "fleet_authority_warm_state",
            "gateway_credentials_in_capsule": False,
            "encrypted_return_published": True,
            "plaintext_receipt_published": False,
        }
        summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return summary
    finally:
        _run(["docker", "rm", "-f", BOT_CONTAINER], check=False)
        _run(["docker", "image", "rm", image], check=False)
        source_root = Path(str(runtime.get("source_root") or ""))
        if source_root.exists():
            shutil.rmtree(source_root, ignore_errors=True)
        shutil.rmtree(data_root, ignore_errors=True)
        # Plaintext receipt is needed only long enough to encrypt the return.
        try:
            receipt_path.unlink()
        except FileNotFoundError:
            pass


def _required_env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"required environment variable missing: {name}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="phase", required=True)

    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--run-id", required=True)
    p_prepare.add_argument("--runner-temp", required=True)
    p_prepare.add_argument("--repository", default="")
    p_prepare.add_argument("--exchange-ref", default=EXCHANGE_REF)

    p_execute = sub.add_parser("execute")
    p_execute.add_argument("--run-id", required=True)
    p_execute.add_argument("--public-head", required=True)
    p_execute.add_argument("--runner-temp", required=True)
    p_execute.add_argument("--repository", default="")
    p_execute.add_argument("--exchange-ref", default=EXCHANGE_REF)
    p_execute.add_argument("--gateway-container", default="ibkr-cloudflare-b1")
    p_execute.add_argument("--wait-timeout-sec", type=int, default=900)

    args = parser.parse_args()
    token = _required_env("GH_TOKEN")
    repository = str(args.repository or os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not repository or "/" not in repository:
        raise RuntimeError("GitHub repository identity required")
    runner_temp = Path(args.runner_temp)
    runner_temp.mkdir(parents=True, exist_ok=True)

    if args.phase == "prepare":
        result = prepare_command_exchange(
            token=token,
            repository=repository,
            run_id=args.run_id,
            runner_temp=runner_temp,
            exchange_ref=args.exchange_ref,
        )
        print("IBKR_WARM_PAPER_PROOF_PREPARED=" + json.dumps({
            key: result[key]
            for key in ("run_id", "recipient_path", "recipient_key_id", "paper_only", "gateway_auth_source", "broker_action")
        }, sort_keys=True))
        return

    result = execute_proof_exchange(
        token=token,
        repository=repository,
        run_id=args.run_id,
        public_head=args.public_head,
        runner_temp=runner_temp,
        gateway_container=args.gateway_container,
        exchange_ref=args.exchange_ref,
        wait_timeout_sec=args.wait_timeout_sec,
    )
    print("IBKR_WARM_PAPER_PROOF_RESULT=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
