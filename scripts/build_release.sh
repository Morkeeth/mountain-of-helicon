#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="${1:-"$root/dist"}"
python_bin="${PYTHON:-python3}"

if ! git -C "$root" diff --quiet HEAD -- . ':!dist'; then
    echo "Release build needs a committed source tree." >&2
    exit 2
fi

epoch="${SOURCE_DATE_EPOCH:-$(git -C "$root" show -s --format=%ct HEAD)}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

normalize_sdist() {
    local archive="$1"
    "$python_bin" - "$archive" "$epoch" <<'PYTHON'
import gzip
from pathlib import Path
import sys
import tarfile

archive = Path(sys.argv[1])
epoch = int(sys.argv[2])
normalized = archive.with_suffix(archive.suffix + ".normalized")
with tarfile.open(archive, "r:gz") as source:
    with normalized.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as target:
                for member in sorted(source.getmembers(), key=lambda item: item.name):
                    content = source.extractfile(member) if member.isfile() else None
                    member.uid = member.gid = 0
                    member.uname = member.gname = ""
                    member.mtime = epoch
                    member.pax_headers = {}
                    target.addfile(member, content)
normalized.replace(archive)
PYTHON
}

for run in first second; do
    source_dir="$work/source-$run"
    build_dir="$work/build-$run"
    mkdir -p "$source_dir" "$build_dir"
    git -C "$root" archive HEAD | tar -x -C "$source_dir"
    (
        cd "$source_dir"
        LC_ALL=C.UTF-8 \
        PYTHONHASHSEED=0 \
        SOURCE_DATE_EPOCH="$epoch" \
        "$python_bin" -m build --sdist --wheel --outdir "$build_dir"
    )
    normalize_sdist \
        "$build_dir/mountain_of_helicon-0.2.4.tar.gz" \
        "$work/unpack-$run"
    "$python_bin" -m twine check "$build_dir"/*
done

for artifact in mountain_of_helicon-0.2.4.tar.gz mountain_of_helicon-0.2.4-py3-none-any.whl; do
    first="$work/build-first/$artifact"
    second="$work/build-second/$artifact"
    if ! cmp -s "$first" "$second"; then
        echo "Reproducibility check failed for $artifact." >&2
        sha256sum "$first" "$second" >&2
        exit 1
    fi
done

rm -rf "$output"
mkdir -p "$output"
cp "$work/build-first/"* "$output/"

echo "Reproducible release artifacts:"
sha256sum "$output/mountain_of_helicon-0.2.4.tar.gz" \
    "$output/mountain_of_helicon-0.2.4-py3-none-any.whl"
