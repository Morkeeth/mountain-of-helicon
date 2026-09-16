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
    "$python_bin" -m twine check "$build_dir"/*
done

for artifact in helicon-0.2.0.tar.gz helicon-0.2.0-py3-none-any.whl; do
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
sha256sum "$output/helicon-0.2.0.tar.gz" \
    "$output/helicon-0.2.0-py3-none-any.whl"
