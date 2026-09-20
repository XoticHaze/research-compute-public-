from __future__ import annotations

"""Warm Fleet-Authority activation runner for one MM-IBKR paper proof.

This module is transport/orchestration only. It does not decide strategy intent,
side, quantity, contract substitution, DCA, fallback policy, or live authority.
It admits exactly one encrypted MM-IBKR command capsule v2, launches the exact
private MM-IBKR source head against the already-authenticated paper Gateway,
delegates submit/cancel/flatten to canonical MM-IBKR HTTP routes, and publishes
only an encrypted proof return.
"""

import argparse
import base64
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_ROOT.parent
for import_root in (REPO_ROOT, SCRIPTS_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import ibkr_remote_paper_proof_return_v1 as proof_return
import mmibkr_b1_attested_source_consumer_v1 as attested_source
import ibkr_remote_selected_runtime_command_capsule_v2 as capsule_v2
import ibkr_remote_selected_runtime_paper_execute_v1 as execute_v1
import ibkr_remote_selected_runtime_paper_proof_v1 as proof_v1
import ibkr_remote_selected_runtime_paper_proof_v2 as proof_v2
from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

RECIPIENT_SCHEMA = "ibkr-remote-paper-recipient-v1"
EXCHANGE_REF = "rendezvous-exchange"
RECIPIENT_ROOT = "rendezvous/recipients"
RESPONSE_ROOT = "rendezvous/responses"
RETURN_ROOT = "rendezvous/returns"
CLOSE_MARKER_SCHEMA = "mmibkr.remote_selected_runtime_boundary_close.v1"
BOT_CONTAINER = "mmibkr-warm-selected-runtime-proof"
BOT_IMAGE_PREFIX = "mmibkr-warm-proof"


class ActivationError(RuntimeError):
    pass


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ActivationError(f"{name} required")
    return text


def _api_raw(
    url: str,
    *,
    token: str,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    accept: str = "application/vnd.github+json",
    timeout: float = 30.0,
) -> tuple[int, bytes]:
    body = None if payload is None else json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "mmibkr-warm-paper-proof-activation/1",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            return int(response.getcode()), response.read()
    except HTTPError as exc:
        return int(exc.code), exc.read()


def _contents_url(repository: str, path: str, *, ref: str | None = None) -> str:
    base = f"https://api.github.com/repos/{repository}/contents/{quote(path, safe='/')}"
    return base if ref is None else base + "?ref=" + quote(ref, safe="")


def publish_new_text(
    *,
    token: str,
    repository: str,
    branch: str,
    path: str,
    content: str,
    message: str,
    api_call: Callable[..., tuple[int, bytes]] = _api_raw,
) -> None:
    if ".." in path.split("/"):
        raise ActivationError("exchange publish path rejected")
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    status, raw = api_call(
        _contents_url(repository, path),
        token=token,
        method="PUT",
        payload=payload,
        timeout=30.0,
    )
    if status != 201:
        detail = ""
        try:
            detail = str(json.loads(raw.decode("utf-8")).get("message") or "")
        except Exception:
            detail = ""
        raise ActivationError(f"exchange path publish failed HTTP {status}: {detail}")


def fetch_raw(
    *,
    token: str,
    repository: str,
    branch: str,
    path: str,
    api_call: Callable[..., tuple[int, bytes]] = _api_raw,
) -> bytes:
    status, raw = api_call(
        _contents_url(repository, path, ref=branch),
        token=token,
        accept="application/vnd.github.raw+json",
        timeout=30.0,
    )
    if status != 200:
        raise HTTPError(_contents_url(repository, path), status, "exchange fetch failed", hdrs=None, fp=None)
    return raw


def generate_command_recipient(*, run_id: str, private_key_path: Path) -> dict[str, str]:
    run_id = _required_text(run_id, "run_id")
    private = x25519.X25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key_path.write_text(base64.b64encode(private_raw).decode("ascii"), encoding="ascii")
    os.chmod(private_key_path, stat.S_IRUSR | stat.S_IWUSR)
    return {
        "schema": RECIPIENT_SCHEMA,
        "run_id": run_id,
        "recipient_b64": base64.b64encode(public_raw).decode("ascii"),
        "recipient_key_id": "sha256:" + hashlib.sha256(public_raw).hexdigest(),
        "authority": capsule_v2.AUTHORITY,
        "harness": capsule_v2.HARNESS,
    }


def publish_command_recipient(
    *,
    token: str,
    repository: str,
    branch: str,
    run_id: str,
    recipient: Mapping[str, Any],
    publisher: Callable[..., None] = publish_new_text,
) -> str:
    expected = {
        "schema": RECIPIENT_SCHEMA,
        "run_id": str(run_id),
        "authority": capsule_v2.AUTHORITY,
        "harness": capsule_v2.HARNESS,
    }
    for key, value in expected.items():
        if recipient.get(key) != value:
            raise ActivationError(f"recipient identity mismatch: {key}")
    path = f"{RECIPIENT_ROOT}/{run_id}-ibkr-remote-paper.json"
    publisher(
        token=token,
        repository=repository,
        branch=branch,
        path=path,
        content=json.dumps(dict(recipient), sort_keys=True) + "\n",
        message="rendezvous: publish one-run IBKR selected-runtime paper-proof recipient",
    )
    return path


def wait_for_command_envelope(
    *,
    token: str,
    repository: str,
    branch: str,
    run_id: str,
    timeout_sec: int,
    expected_public_head: str,
    fetcher: Callable[..., bytes] = fetch_raw,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    path = f"{RESPONSE_ROOT}/{run_id}/ibkr-remote-paper-envelope.json"
    close_path = f"{RESPONSE_ROOT}/{run_id}/ibkr-remote-paper-close.json"
    deadline = time.monotonic() + max(1, int(timeout_sec))
    while time.monotonic() < deadline:
        try:
            raw = fetcher(token=token, repository=repository, branch=branch, path=path)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            try:
                close_raw = fetcher(
                    token=token,
                    repository=repository,
                    branch=branch,
                    path=close_path,
                )
            except HTTPError as close_exc:
                if close_exc.code == 404:
                    sleep(2.0)
                    continue
                raise
            try:
                close_node = json.loads(close_raw.decode("utf-8"))
            except Exception as close_exc:
                raise ActivationError(
                    "boundary close marker is not valid JSON"
                ) from close_exc
            if not isinstance(close_node, dict):
                raise ActivationError("boundary close marker must be an object")
            expected = {
                "schema": CLOSE_MARKER_SCHEMA,
                "run_id": str(run_id),
                "public_authority_head": str(expected_public_head).strip().lower(),
                "command_intent_present": False,
                "broker_action": False,
                "live_execution_allowed": False,
            }
            for key, value in expected.items():
                actual = close_node.get(key)
                if key == "public_authority_head":
                    actual = str(actual or "").strip().lower()
                if actual != value:
                    raise ActivationError(
                        f"boundary close marker identity mismatch: {key}"
                    )
            return {
                "_boundary_closed": True,
                "close_marker": close_node,
            }
        try:
            node = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ActivationError("encrypted command envelope is not valid JSON") from exc
        return node if isinstance(node, dict) else {}
    raise ActivationError("run-bound encrypted selected-runtime command did not arrive")


def assemble_command_ciphertext(
    *,
    envelope: Mapping[str, Any],
    token: str,
    repository: str,
    branch: str,
    run_id: str,
    fetcher: Callable[..., bytes] = fetch_raw,
) -> bytes:
    chunks = envelope.get("chunks")
    if not isinstance(chunks, list) or not chunks or len(chunks) > 64:
        raise ActivationError("encrypted command chunk list invalid")
    prefix = f"{RESPONSE_ROOT}/{run_id}/"
    pieces: list[str] = []
    seen: set[str] = set()
    for node in chunks:
        if not isinstance(node, Mapping) or set(node) != {"path", "sha256", "chars"}:
            raise ActivationError("encrypted command chunk descriptor invalid")
        path = str(node.get("path") or "")
        if not path.startswith(prefix) or path in seen or ".." in path.split("/"):
            raise ActivationError("encrypted command chunk path rejected")
        seen.add(path)
        raw = fetcher(token=token, repository=repository, branch=branch, path=path)
        if len(raw) != int(node.get("chars") or 0):
            raise ActivationError("encrypted command chunk length mismatch")
        if hashlib.sha256(raw).hexdigest() != str(node.get("sha256") or ""):
            raise ActivationError("encrypted command chunk digest mismatch")
        pieces.append(raw.decode("ascii"))
    try:
        ciphertext = base64.b64decode("".join(pieces).encode("ascii"), validate=True)
    except Exception as exc:
        raise ActivationError("encrypted command chunk assembly is not base64") from exc
    if hashlib.sha256(ciphertext).hexdigest() != str(envelope.get("ciphertext_sha256") or ""):
        raise ActivationError("encrypted command assembled ciphertext digest mismatch")
    return ciphertext


def materialize_command(
    *,
    envelope: Mapping[str, Any],
    ciphertext: bytes,
    private_key_path: Path,
    run_id: str,
    runner_temp: Path,
    fleet_authority_base: str = "https://fleet-authority.slenderiq.workers.dev",
) -> dict[str, Any]:
    response_root = f"{RESPONSE_ROOT}/{run_id}"
    plaintext = decrypt_assembled_ciphertext(
        envelope=dict(envelope),
        ciphertext=ciphertext,
        private_key_path=private_key_path,
        expected_schema=capsule_v2.ENVELOPE_SCHEMA,
        expected_run_id=str(run_id),
        expected_harness=capsule_v2.HARNESS,
        response_root=response_root,
        expected_authority=capsule_v2.AUTHORITY,
    )
    capsule = capsule_v2.validate_capsule(plaintext)
    source_ticket = (
        capsule.get("source")
        if isinstance(capsule.get("source"), Mapping)
        else {}
    )
    source_archive_bytes = None
    if source_ticket.get("transport") == capsule_v2.ATTESTED_SOURCE_TRANSPORT:
        source_result = attested_source.consume_attested_source(
            authority_base=fleet_authority_base,
            run_id=str(run_id),
            source_ticket=source_ticket,
            private_key_path=private_key_path,
        )
        if (
            source_result.get("ok") is not True
            or source_result.get("private_attestation_verified") is not True
        ):
            raise ActivationError("Fleet-attested source materialization failed")
        source_archive_bytes = source_result["archive"]
    runtime = capsule_v2.materialize(
        capsule,
        runner_temp=runner_temp,
        source_archive_bytes=source_archive_bytes,
    )
    mode = str(runtime.get("mode") or "")
    if mode == capsule_v2.PROOF_MODE:
        proof_v2.validate_fleet_authority_runtime(runtime)
    elif mode == capsule_v2.EXECUTE_MODE:
        execute_v1.validate_fleet_authority_execute_runtime(runtime)
    else:
        raise ActivationError("materialized command mode rejected")
    return runtime


def canonical_runtime_docker_command(
    *,
    image: str,
    data_dir: Path,
    gateway_host: str,
    gateway_port: int,
    container_name: str = BOT_CONTAINER,
) -> list[str]:
    env = {
        "IB_HOST": gateway_host,
        "IB_PORT": str(int(gateway_port)),
        "CLIENT_ID": "34",
        "ENABLE_LIVE_TRADING": "0",
        "CONTROL_API_ENABLED": "true",
        "CONTROL_API_HOST": "0.0.0.0",
        "CONTROL_API_PORT": "8001",
        "CONTROL_RUNTIME_PORT": "8001",
        "BOT_SELECTED_RUNTIME_NATURAL_CANDIDATE_14TH31BV_ENABLED": "0",
        "FUTURES_AUTO_ENABLED": "0",
        "STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53": "1",
        "STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37": "1",
        "STRATEGY_IBKR_PAPER_FLATTEN_ENABLED_13Z39": "1",
        "STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D": "0",
        "STRATEGY_IBKR_PAPER_SUBMIT_ENABLED": "0",
        "STRATEGY_IBKR_PAPER_PLACE_ORDER_ENABLED_13Z27": "0",
        "STRATEGY_IBKR_PAPER_ALLOW_UNRELATED_OPEN_ORDERS_13Z36B": "0",
        "MMIBKR_ARTIFACT_ROOT": "/app/data/artifacts",
    }
    cmd = ["docker", "run", "-d", "--name", container_name, "--network", "host"]
    for key, value in env.items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.extend(["-v", f"{data_dir}:/app/data", image])
    return cmd


def start_canonical_runtime(
    *,
    runtime: Mapping[str, Any],
    run_id: str,
    runner_temp: Path,
    gateway_host: str,
    gateway_port: int,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, Path]:
    source_root = Path(_required_text(runtime.get("source_root"), "runtime.source_root"))
    if not source_root.is_dir():
        raise ActivationError("materialized MM-IBKR source root missing")
    image = f"{BOT_IMAGE_PREFIX}:{run_id}"
    data_dir = runner_temp / "mmibkr-proof-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dockerfile = source_root / "Dockerfile.bot"
    if not dockerfile.is_file():
        raise ActivationError("canonical MM-IBKR Dockerfile.bot missing")
    run(
        [
            "docker",
            "build",
            "-f",
            str(dockerfile),
            "--target",
            "bot",
            "-t",
            image,
            str(source_root),
        ],
        check=True,
    )
    run(["docker", "rm", "-f", BOT_CONTAINER], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run(canonical_runtime_docker_command(
        image=image,
        data_dir=data_dir,
        gateway_host=gateway_host,
        gateway_port=gateway_port,
    ), check=True)

    deadline = time.monotonic() + 180.0
    while time.monotonic() < deadline:
        try:
            status, body = proof_v1._http_json("http://127.0.0.1:8001", "GET", "/healthz", timeout=4.0)
        except Exception:
            status, body = 0, {}
        if status == 200 and body.get("ok") is not False:
            return image, data_dir
        sleep(2.0)
    raise ActivationError("canonical MM-IBKR proof runtime did not become healthy")


def execute_proof(
    *,
    runtime: Mapping[str, Any],
    run_id: str,
    public_head: str,
    receipt_path: Path,
    base_url: str = "http://127.0.0.1:8001",
) -> dict[str, Any]:
    request_path = Path(_required_text(runtime.get("request_path"), "runtime.request_path"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    receipt = proof_v2.execute_paper_proof_v2(
        runtime=runtime,
        request=request,
        send=proof_v1._request_sender(base_url),
        run_id=str(run_id),
        public_head=str(public_head),
    )
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(receipt_path, stat.S_IRUSR | stat.S_IWUSR)
    return receipt


def execute_command(
    *,
    runtime: Mapping[str, Any],
    run_id: str,
    public_head: str,
    receipt_path: Path,
    base_url: str = "http://127.0.0.1:8001",
) -> dict[str, Any]:
    mode = str(runtime.get("mode") or "")
    if mode == capsule_v2.PROOF_MODE:
        return execute_proof(
            runtime=runtime,
            run_id=run_id,
            public_head=public_head,
            receipt_path=receipt_path,
            base_url=base_url,
        )
    if mode == capsule_v2.EXECUTE_MODE:
        request_path = Path(_required_text(runtime.get("request_path"), "runtime.request_path"))
        request = json.loads(request_path.read_text(encoding="utf-8"))
        receipt = execute_v1.execute_paper_execute(
            runtime=runtime,
            request=request,
            send=proof_v1._request_sender(base_url),
            run_id=str(run_id),
            public_head=str(public_head),
        )
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(receipt_path, stat.S_IRUSR | stat.S_IWUSR)
        return receipt
    raise ActivationError("unsupported selected-runtime command mode")


def publish_encrypted_return(
    *,
    token: str,
    repository: str,
    branch: str,
    run_id: str,
    output_dir: Path,
    envelope: Mapping[str, Any],
    publisher: Callable[..., None] = publish_new_text,
) -> None:
    prefix = f"{RETURN_ROOT}/{run_id}/"
    chunks = envelope.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ActivationError("proof return chunks missing")
    for node in chunks:
        if not isinstance(node, Mapping):
            raise ActivationError("proof return chunk descriptor invalid")
        path = str(node.get("path") or "")
        local_name = str(node.get("local_name") or "")
        if not path.startswith(prefix) or ".." in path.split("/") or not local_name:
            raise ActivationError("proof return publish path rejected")
        text = (output_dir / local_name).read_text(encoding="ascii")
        if len(text) != int(node.get("chars") or 0):
            raise ActivationError("proof return chunk length mismatch")
        if hashlib.sha256(text.encode("ascii")).hexdigest() != str(node.get("sha256") or ""):
            raise ActivationError("proof return chunk digest mismatch")
        publisher(
            token=token,
            repository=repository,
            branch=branch,
            path=path,
            content=text,
            message="rendezvous: publish encrypted selected-runtime paper-proof return chunk",
        )
    envelope_path = prefix + "ibkr-paper-proof-envelope.json"
    publisher(
        token=token,
        repository=repository,
        branch=branch,
        path=envelope_path,
        content=json.dumps(dict(envelope), sort_keys=True) + "\n",
        message="rendezvous: publish encrypted selected-runtime paper-proof return envelope",
    )


def cleanup_private_material(*, image: str | None, runner_temp: Path) -> None:
    subprocess.run(["docker", "rm", "-f", BOT_CONTAINER], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if image:
        subprocess.run(["docker", "image", "rm", image], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for name in (
        "mm-ibkr-source",
        "mmibkr-proof-data",
        "mm-ibkr-source.tar.gz",
        "ibkr-submit-request.json",
        "ibkr-runtime.json",
        "ibkr-proof-return-recipient.json",
        "ibkr-command-private.b64",
        "ibkr-command-envelope.json",
        "ibkr-command-ciphertext.bin",
        "ibkr-paper-proof-receipt.json",
        "ibkr-paper-execute-receipt.json",
        "ibkr-paper-proof-return",
    ):
        path = runner_temp / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--public-head", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--exchange-ref", default=EXCHANGE_REF)
    parser.add_argument("--runner-temp", default=os.environ.get("RUNNER_TEMP", ""))
    parser.add_argument("--gateway-host", default="127.0.0.1")
    parser.add_argument("--gateway-port", type=int, default=4002)
    parser.add_argument("--wait-seconds", type=int, default=900)
    parser.add_argument(
        "--mode",
        choices=(capsule_v2.PROOF_MODE, capsule_v2.EXECUTE_MODE),
        default=capsule_v2.PROOF_MODE,
    )
    args = parser.parse_args()

    run_id = _required_text(args.run_id, "run_id")
    public_head = _required_text(args.public_head, "public_head")
    repository = _required_text(args.repository, "repository")
    token = _required_text(os.environ.get("GH_TOKEN"), "GH_TOKEN")
    runner_temp = Path(_required_text(args.runner_temp, "runner_temp"))
    runner_temp.mkdir(parents=True, exist_ok=True)

    private_key_path = runner_temp / "ibkr-command-private.b64"
    image: str | None = None
    receipt: dict[str, Any] | None = None
    try:
        recipient = generate_command_recipient(run_id=run_id, private_key_path=private_key_path)
        recipient_path = publish_command_recipient(
            token=token,
            repository=repository,
            branch=args.exchange_ref,
            run_id=run_id,
            recipient=recipient,
        )
        print("IBKR_REMOTE_COMMAND_RECIPIENT_PUBLISHED=1")
        print("IBKR_REMOTE_COMMAND_RECIPIENT_PATH=" + recipient_path)

        envelope = wait_for_command_envelope(
            token=token,
            repository=repository,
            branch=args.exchange_ref,
            run_id=run_id,
            timeout_sec=args.wait_seconds,
            expected_public_head=public_head,
        )
        if envelope.get("_boundary_closed") is True:
            marker = (
                envelope.get("close_marker")
                if isinstance(envelope.get("close_marker"), Mapping)
                else {}
            )
            close_path = runner_temp / "ibkr-no-command-close.json"
            close_path.write_text(
                json.dumps(dict(marker), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print("IBKR_REMOTE_NO_COMMAND_CLOSE_ACCEPTED=1")
            print("IBKR_REMOTE_SELECTED_RUNTIME_COMMAND_EXECUTED=0")
            print("IBKR_REMOTE_LIVE_EXECUTION_ALLOWED=0")
            return

        envelope_path = runner_temp / "ibkr-command-envelope.json"
        envelope_path.write_text(json.dumps(envelope, sort_keys=True) + "\n", encoding="utf-8")
        ciphertext = assemble_command_ciphertext(
            envelope=envelope,
            token=token,
            repository=repository,
            branch=args.exchange_ref,
            run_id=run_id,
        )
        ciphertext_path = runner_temp / "ibkr-command-ciphertext.bin"
        ciphertext_path.write_bytes(ciphertext)
        os.chmod(ciphertext_path, stat.S_IRUSR | stat.S_IWUSR)

        runtime = materialize_command(
            envelope=envelope,
            ciphertext=ciphertext,
            private_key_path=private_key_path,
            run_id=run_id,
            runner_temp=runner_temp,
        )
        if str(runtime.get("mode") or "") != str(args.mode):
            raise ActivationError("workflow mode does not match encrypted command mode")
        print("IBKR_REMOTE_COMMAND_MATERIALIZED=1")
        print("IBKR_REMOTE_COMMAND_ID=" + str(runtime.get("command_id")))
        print("IBKR_REMOTE_COMMAND_MODE=" + str(runtime.get("mode")))

        image, _ = start_canonical_runtime(
            runtime=runtime,
            run_id=run_id,
            runner_temp=runner_temp,
            gateway_host=args.gateway_host,
            gateway_port=args.gateway_port,
        )
        print("IBKR_REMOTE_CANONICAL_RUNTIME_READY=1")

        receipt_path = runner_temp / (
            "ibkr-paper-proof-receipt.json"
            if runtime.get("mode") == capsule_v2.PROOF_MODE
            else "ibkr-paper-execute-receipt.json"
        )
        receipt = execute_command(
            runtime=runtime,
            run_id=run_id,
            public_head=public_head,
            receipt_path=receipt_path,
        )
        print("IBKR_REMOTE_SELECTED_RUNTIME_COMMAND_EXECUTED=1")
        print("IBKR_REMOTE_SELECTED_RUNTIME_COMMAND_STATUS=" + str(receipt.get("status") or ""))

        recipient_return_path = Path(_required_text(runtime.get("return_recipient_path"), "runtime.return_recipient_path"))
        return_recipient = json.loads(recipient_return_path.read_text(encoding="utf-8"))
        return_dir = runner_temp / "ibkr-paper-proof-return"
        return_envelope = proof_return.encrypt_receipt(
            receipt=receipt,
            runtime=runtime,
            recipient=return_recipient,
            run_id=run_id,
            output_dir=return_dir,
        )
        publish_encrypted_return(
            token=token,
            repository=repository,
            branch=args.exchange_ref,
            run_id=run_id,
            output_dir=return_dir,
            envelope=return_envelope,
        )
        print("IBKR_REMOTE_ENCRYPTED_RETURN_PUBLISHED=1")
        print("IBKR_REMOTE_RETURN_PLAINTEXT_PUBLISHED=0")
        print("IBKR_REMOTE_GLOBAL_CANCEL_CALLED=0")
        print("IBKR_REMOTE_LIVE_EXECUTION_ALLOWED=0")
        print("IBKR_REMOTE_SELECTED_RUNTIME_COMMAND_OK=" + ("1" if receipt.get("ok") else "0"))
    finally:
        cleanup_private_material(image=image, runner_temp=runner_temp)

    raise SystemExit(0 if receipt and receipt.get("ok") else 2)


if __name__ == "__main__":
    main()
