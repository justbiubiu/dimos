#!/usr/bin/env bash
# Daily quality sweep for GitHub Actions: optional ruff auto-fix, then ruff/mypy/pytest.
# Writes report/daily-quality.md and sets GitHub Actions step outputs when GITHUB_OUTPUT is set.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

REPORT_DIR="${REPORT_DIR:-report}"
mkdir -p "$REPORT_DIR"
REPORT_FILE="${REPORT_DIR}/daily-quality.md"

log() {
  echo "$*" | tee -a "$REPORT_FILE"
}

: >"$REPORT_FILE"
log "# Daily quality report"
log ""
log "- **UTC time:** $(date -u '+%Y-%m-%d %H:%M:%S')"
log "- **Host:** $(uname -srm)"
log "- **Commit:** $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
log ""

FAILED=0
RUFF_CHECK_OK=1
MYPY_OK=1
PYTEST_OK=1

run_ruff_autofix() {
  log "## Ruff auto-fix (format + check --fix)"
  uv run ruff format .
  uv run ruff check . --fix
  log "<<< ruff auto-fix finished"
  log ""
}

run_ruff_check() {
  log "## Ruff check"
  if uv run ruff check .; then
    log "**Result:** PASS"
  else
    log "**Result:** FAIL"
    RUFF_CHECK_OK=0
    FAILED=1
  fi
  log ""
}

run_mypy() {
  log "## Mypy (dimos/)"
  if uv run mypy dimos; then
    log "**Result:** PASS"
  else
    log "**Result:** FAIL"
    MYPY_OK=0
    FAILED=1
  fi
  log ""
}

run_pytest() {
  log "## Pytest (fast suite)"
  if uv run pytest; then
    log "**Result:** PASS"
  else
    log "**Result:** FAIL"
    PYTEST_OK=0
    FAILED=1
  fi
  log ""
}

# Optional: static scan for TODO/FIXME density (informational)
scan_todos() {
  log "## TODO / FIXME scan (informational)"
  local count
  count="$(git grep -n -E 'TODO|FIXME' -- dimos examples scripts 2>/dev/null | wc -l || true)"
  log "Rough line hit count: ${count}"
  log ""
}

run_ruff_autofix

run_ruff_check
run_mypy
run_pytest

scan_todos || true

HAS_CHANGES=0
if ! git diff --quiet || ! git diff --cached --quiet; then
  HAS_CHANGES=1
fi

log "## Summary"
log "| Check | Status |"
log "|-------|--------|"
log "| ruff check | $([[ "$RUFF_CHECK_OK" -eq 1 ]] && echo OK || echo FAIL) |"
log "| mypy | $([[ "$MYPY_OK" -eq 1 ]] && echo OK || echo FAIL) |"
log "| pytest | $([[ "$PYTEST_OK" -eq 1 ]] && echo OK || echo FAIL) |"
log "| uncommitted after ruff | $([[ "$HAS_CHANGES" -eq 1 ]] && echo yes || echo no) |"
log ""

# Roll back auto-fixes if anything failed (no PR for broken tree).
if [[ "$FAILED" -ne 0 ]]; then
  log "**Action:** checks failed — discarding ruff changes to tracked files (report kept)."
  git reset --hard HEAD
  HAS_CHANGES=0
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "checks_passed=$([[ "$FAILED" -eq 0 ]] && echo true || echo false)"
    echo "has_uncommitted_changes=$([[ "$HAS_CHANGES" -eq 1 ]] && echo true || echo false)"
    echo "report_path=$REPORT_FILE"
  } >>"$GITHUB_OUTPUT"
fi

exit "$FAILED"
