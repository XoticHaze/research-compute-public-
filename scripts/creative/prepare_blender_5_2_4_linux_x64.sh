#!/usr/bin/env bash
# Fixed public Blender binary preparation; executor owners call only after placement admission.
# No request-owned version, URL, destination or shell. Does not launch any job.
set -euo pipefail

version="5.2.4"
base="https://download.blender.org/release/Blender5.2"
filename="blender-${version}-linux-x64.tar.xz"
expected_bytes=385047680
expected_sha256="2fd14c50987426897ba60237ee996edf2b4151f4b1a72a460ca20be58c1d2d86"
root="${RUNNER_TEMP:?trusted executor must set RUNNER_TEMP}/cc-blender-runtime"
mkdir -p "$root"
[[ ! -e "$root/$filename" ]] || { echo "runtime_archive_already_exists"; exit 2; }
curl --fail --location --silent --show-error --retry 3 --max-time 360 "$base/$filename" -o "$root/$filename"
curl --fail --location --silent --show-error --retry 3 --max-time 30 "$base/blender-${version}.sha256" -o "$root/SHA256SUMS"
actual_bytes="$(wc -c < "$root/$filename" | tr -d '[:space:]')"
[[ "$actual_bytes" == "$expected_bytes" ]] || { echo "runtime_download_length_mismatch" >&2; exit 2; }
# Blender's official release manifest is fetched from the same HTTPS origin; pin
# and its hash must also match the independently pinned release archive SHA-256.
digest="$(awk -v name="$filename" '$2 == name || $2 == "*"name {print $1}' "$root/SHA256SUMS")"
[[ "$digest" =~ ^[a-fA-F0-9]{64}$ ]] || { echo "official_manifest_digest_missing" >&2; exit 2; }
[[ "${digest,,}" == "$expected_sha256" ]] || { echo "unapproved_blender_release_digest" >&2; exit 2; }
(cd "$root" && printf '%s  %s\n' "$digest" "$filename" | sha256sum --check --status)
# Reject absolute and parent-traversal names before extraction.
archive_root="blender-${version}-linux-x64"
if ! tar -tJf "$root/$filename" | python3 -c '
import sys
from pathlib import PurePosixPath
root = sys.argv[1]
names = [line.rstrip("\\n") for line in sys.stdin]
if not names: sys.exit(2)
for name in names:
    bits = PurePosixPath(name).parts
    if name.startswith("/") or not bits or bits[0] != root or ".." in bits: sys.exit(3)
' "$archive_root"; then
    echo "runtime_archive_path_rejected" >&2; exit 2
fi
tar -xJf "$root/$filename" -C "$root"
binary="$root/blender-${version}-linux-x64/blender"
[[ -x "$binary" ]] || { echo "blender_binary_missing" >&2; exit 2; }
version_out="$("$binary" --version)"
grep -m 1 -F "Blender $version" <<< "$version_out" >/dev/null
printf 'CC_BLENDER_RUNTIME_PREPARED_VERSION=%s\n' "$version"
printf 'CC_BLENDER_RUNTIME_SHA256=%s\n' "$digest"
printf 'CC_BLENDER_RUNTIME_PATH=%s\n' "$binary"
