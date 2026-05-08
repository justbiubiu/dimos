#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "================================================================"
echo " verify.sh @ $REPO_ROOT"
echo " host: $(uname -srm)"
echo "================================================================"

echo ">>> [1/4] Validate basic project files"
test -f pyproject.toml
test -d dimos
echo "<<< OK"

echo ">>> [2/4] Sync dependencies (uv)"
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
uv sync --all-extras --no-extra dds --frozen
echo "<<< OK"

echo ">>> [3/4] Ruff check"
uv run ruff check .
echo "<<< OK"

echo ">>> [4/4] Pytest fast suite"
uv run pytest
echo "<<< OK"

echo "================================================================"
echo " verify.sh finished successfully"
echo "================================================================"
