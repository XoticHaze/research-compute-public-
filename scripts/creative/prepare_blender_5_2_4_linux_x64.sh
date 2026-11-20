#!/usr/bin/env bash
# Fixed public Blender binary preparation; executor owners call only after placement admission.
# No request-owned version, URL, destination or shell. Does not launch any job.
set -euo pipefail

version="5.2.4"
base="https://download.blender.org/release/Blender5.2"
filename="blender-${version}-linux-x64.tar.xz"
expected_bytes=385047680
root="${RUNNER_TEMP:?trusted executor must set RUNNER_TEMP}/cc-blender-runtime"
mkdir -p "$root"
[[ ! -e "$root/$filename" ]] || { echo "runtime_archive_already_exists"; exit 2; }
curl --fail --location --silent --show-error --retry 3 --max-time 360 "$base/$filename" -o "$root/$filename"
curl --fail --location --silent --show-error --retry 3 --max-time 30 "$base/blender-${version}.sha256" -o "$root/SHA256SUMS"
actual_bytes="$(wc -c < "$root/$filename" | tr -d '[:space:]')"
[[ "$actual_bytes" == "$expected_bytes" ]] || { echo "runtime_download_length_mismatch" >&2; exit 2; }
# Blender's official release manifest is fetched from the same HTTPS origin; pin
# its exact digest separately before production/secret-bearing execution.
digest="$(awk -v name="$filename" '$2 == name || $2 == "*"name {print $1}' "$root/SHA256SUMS")"
[[ "$digest" =~ ^[a-fA-F0-9]{64}$ ]] || { echo "official_manifest_digest_missing" >&2; exit 2; }
(cd "$root" && printf '%s  %s\n' "$digest" "$filename" | sha256sum --check --status)
# Prevent unexpected archive path layout from becoming arbitrary extraction paths.
if tar -tJf "$root/$filename" | grep -Ev "^blender-${version}-linux-x64/([A-Za-z0-9_.+@/ -]*)$" | grep -q .; then
    echo "runtime_archive_path_rejected" >&2; exit 2
fi
tar -xJf "$root/$filename" -C "$root"
binary="$root/blender-${version}-linux-x64/blender"
[[ -x "$binary" ]] || { echo "blender_binary_missing" >&2; exit 2; }
"$binary" --version | head -n 1 | grep -F "Blender $version" >/dev/null
printf 'CC_BLENDER_RUNTIME_PREPARED_VERSION=%s\n' "$version"
printf 'CC_BLENDER_RUNTIME_SHA256=%s\n' "$digest"
printf 'CC_BLENDER_RUNTIME_PATH=%s\n' "$binary"
