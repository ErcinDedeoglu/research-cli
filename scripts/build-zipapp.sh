#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
outdir="${1:-"$root/dist"}"
mkdir -p "$outdir"
python3 -m zipapp "$root/src" \
  --main "research_cli.cli:run" \
  --output "$outdir/research-cli.pyz" \
  --python "/usr/bin/env python3"
echo "wrote $outdir/research-cli.pyz"
