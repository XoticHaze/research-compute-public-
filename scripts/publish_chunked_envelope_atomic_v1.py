from __future__ import annotations

"""Atomically publish encrypted capsule chunks and completion envelope.

The Git ref is advanced only after every blob, the combined tree, and commit exist.
Consumers therefore observe either the old exchange state or the complete new
capsule publication, never chunks without their envelope.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DEFAULT_CHUNK_CHARS = 8000


def build_publication(
    payload_b64: str,
    envelope: dict,
    *,
    response_root: str,
    stem: str,
    envelope_path: str,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
) -> list[tuple[str, bytes]]:
    if not payload_b64 or int(chunk_chars) <= 0:
        raise ValueError("invalid payload/chunk size")
    try:
        ciphertext = base64.b64decode(payload_b64.encode("ascii"), validate=True)
    except Exception as exc:
        raise ValueError("payload must be valid base64") from exc
    if hashlib.sha256(ciphertext).hexdigest() != envelope.get("ciphertext_sha256"):
        raise ValueError("ciphertext digest does not match envelope")
    root = response_root.rstrip("/")
    if not root or "/../" in f"/{root}/" or not stem or "/" in stem:
        raise ValueError("invalid publication path")
    if not envelope_path.startswith(root + "/") or "/../" in f"/{envelope_path}/":
        raise ValueError("envelope path must be inside response root")

    files: list[tuple[str, bytes]] = []
    manifest: list[dict[str, object]] = []
    for index, start in enumerate(range(0, len(payload_b64), int(chunk_chars))):
        raw = payload_b64[start : start + int(chunk_chars)].encode("ascii")
        path = f"{root}/{stem}-{index:03d}.txt"
        files.append((path, raw))
        manifest.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "chars": len(raw)})

    complete = dict(envelope)
    complete["chunks"] = manifest
    files.append((envelope_path, (json.dumps(complete, sort_keys=True) + "\n").encode("utf-8")))
    return files


def _api(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API {method} {url} failed: {exc.code} {detail}") from exc


def publish_atomic(*, repo: str, branch: str, token: str, files: list[tuple[str, bytes]], message: str) -> str:
    base = f"https://api.github.com/repos/{repo}"
    ref = _api("GET", f"{base}/git/ref/heads/{branch}", token)
    parent = ref["object"]["sha"]
    commit = _api("GET", f"{base}/git/commits/{parent}", token)
    entries = []
    for path, raw in files:
        blob = _api("POST", f"{base}/git/blobs", token, {"content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = _api("POST", f"{base}/git/trees", token, {"base_tree": commit["tree"]["sha"], "tree": entries})
    new_commit = _api("POST", f"{base}/git/commits", token, {"message": message, "tree": tree["sha"], "parents": [parent]})
    _api("PATCH", f"{base}/git/refs/heads/{branch}", token, {"sha": new_commit["sha"], "force": False})
    return new_commit["sha"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch", default="rendezvous-exchange")
    parser.add_argument("--token-env", default="GH_TOKEN")
    parser.add_argument("--payload-b64-file", type=Path, required=True)
    parser.add_argument("--envelope-file", type=Path, required=True)
    parser.add_argument("--response-root", required=True)
    parser.add_argument("--stem", required=True)
    parser.add_argument("--envelope-path", required=True)
    parser.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    parser.add_argument("--message", default="rendezvous: atomically publish encrypted capsule")
    args = parser.parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(f"missing token environment variable {args.token_env}")
    files = build_publication(
        args.payload_b64_file.read_text(encoding="ascii").strip(),
        json.loads(args.envelope_file.read_text(encoding="utf-8")),
        response_root=args.response_root,
        stem=args.stem,
        envelope_path=args.envelope_path,
        chunk_chars=args.chunk_chars,
    )
    sha = publish_atomic(repo=args.repo, branch=args.branch, token=token, files=files, message=args.message)
    print(json.dumps({"published_commit": sha, "file_count": len(files)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
