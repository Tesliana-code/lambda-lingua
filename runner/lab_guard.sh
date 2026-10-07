#!/usr/bin/env bash
set -euo pipefail

EXPECTED_ROOT="/home/superadmin/lambda-lingua-experiment-zero-20261007"
EXPECTED_BRANCH="experiment/zero-20261007"

ACTUAL_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
ACTUAL_BRANCH="$(git branch --show-current 2>/dev/null || true)"

if [ "$ACTUAL_ROOT" != "$EXPECTED_ROOT" ]; then
    echo "ABORT: wrong worktree"
    echo "expected: $EXPECTED_ROOT"
    echo "actual:   ${ACTUAL_ROOT:-NONE}"
    exit 1
fi

if [ "$ACTUAL_BRANCH" != "$EXPECTED_BRANCH" ]; then
    echo "ABORT: wrong branch"
    echo "expected: $EXPECTED_BRANCH"
    echo "actual:   ${ACTUAL_BRANCH:-NONE}"
    exit 1
fi

echo "ΛLAB GUARD: PASS"
