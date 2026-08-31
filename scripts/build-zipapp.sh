#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
outdir="${1:-"$root/dist"}"
stage="$(mktemp -d "${TMPDIR:-/tmp}/research-cli-zipapp.XXXXXX")"
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT
mkdir -p "$outdir"
python3 -m pip install --disable-pip-version-check --upgrade -q pip
python3 -m pip install --disable-pip-version-check -q --target "$stage" "telethon==1.44.0"
cp -R "$root/src/research_cli" "$stage/research_cli"
find "$stage" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$stage" -name '*.dist-info' -type d -prune -exec rm -rf {} +
python3 -m zipapp "$stage" \
  --main "research_cli.cli:run" \
  --output "$outdir/research-cli.pyz" \
  --python "/usr/bin/env python3"
echo "wrote $outdir/research-cli.pyz"
