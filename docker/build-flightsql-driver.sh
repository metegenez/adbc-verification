#!/usr/bin/env bash
# Rebuilds libadbc_driver_flightsql.so with all session patches.
#
# Patches stacked into the build:
#   1. Attempt 1 (committed on fix branch): runtime.GC() removed from 4 FlightSQL Release functions
#   2. Attempt 4 (committed on fix branch): record_reader.go done-channel + waiter sync
#   3. arrow-go PR #793 (deterministic-cdata branch): cdata nativeCRecordBatchReader
#      uses atomic Retain/Release instead of finalizer. Wired via Go module
#      `replace` directive (NOT git subtree) — keeps the upstream repo tidy.
#
# Output: docker/drivers/libadbc_driver_flightsql.so (overwrites)
#
# Required local checkouts:
#   $ARROW_ADBC_DIR (default ~/coding/opensource/arrow-adbc) — must have branch
#                   fix/flightsql-remove-explicit-gc available
#   $ARROW_GO_PR793_DIR (default ~/coding/opensource/arrow-go-pr793) — checked
#                   out at branch deterministic-cdata
#
# What this script does:
#   1. Saves arrow-adbc's current branch + go.mod
#   2. Switches arrow-adbc/go/adbc to fix/flightsql-remove-explicit-gc
#   3. Adds the arrow-go replace directive to go.mod (uncommitted, working tree only)
#   4. Builds with `go build -tags driverlib -buildmode=c-shared`
#   5. Restores arrow-adbc go.mod (removes replace directive)
#   6. Optionally restores the original branch (set RESTORE_BRANCH=1)
#
# To revert to the stock upstream driver: copy docker/drivers/libadbc_driver_flightsql.so.original
# back over the patched .so.

set -euo pipefail

# Ensure go binary is on PATH (user's Go install lives at ~/go/bin/go).
if ! command -v go >/dev/null 2>&1; then
    if [[ -x "$HOME/go/bin/go" ]]; then
        export PATH="$HOME/go/bin:$PATH"
    elif [[ -x /usr/local/go/bin/go ]]; then
        export PATH="/usr/local/go/bin:$PATH"
    fi
fi

ARROW_ADBC_DIR="${ARROW_ADBC_DIR:-$HOME/coding/opensource/arrow-adbc}"
ARROW_GO_PR793_DIR="${ARROW_GO_PR793_DIR:-$HOME/coding/opensource/arrow-go-pr793}"
FIX_BRANCH="${FIX_BRANCH:-fix/flightsql-remove-explicit-gc}"
PR793_BRANCH="${PR793_BRANCH:-deterministic-cdata}"
RESTORE_BRANCH="${RESTORE_BRANCH:-0}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_SO="${OUTPUT_SO:-$REPO_ROOT/docker/drivers/libadbc_driver_flightsql.so}"

GO_ADBC="$ARROW_ADBC_DIR/go/adbc"

[[ -d "$GO_ADBC" ]] || { echo "ERROR: $GO_ADBC not found" >&2; exit 1; }
[[ -d "$ARROW_GO_PR793_DIR/.git" ]] || { echo "ERROR: $ARROW_GO_PR793_DIR is not a git repo" >&2; exit 1; }

pr793_branch_now="$(git -C "$ARROW_GO_PR793_DIR" branch --show-current 2>/dev/null || echo '')"
if [[ "$pr793_branch_now" != "$PR793_BRANCH" ]]; then
    echo "WARNING: arrow-go-pr793 is on '$pr793_branch_now' (expected '$PR793_BRANCH')" >&2
    echo "         continuing anyway, but build provenance may differ from Cycle 11" >&2
fi

orig_branch="$(git -C "$GO_ADBC" branch --show-current 2>/dev/null || echo 'DETACHED')"
echo "[1/6] arrow-adbc original branch: $orig_branch"

if [[ "$orig_branch" != "$FIX_BRANCH" ]]; then
    echo "[2/6] Checking out $FIX_BRANCH in $GO_ADBC..."
    git -C "$GO_ADBC" checkout "$FIX_BRANCH"
else
    echo "[2/6] Already on $FIX_BRANCH"
fi

GO_MOD="$GO_ADBC/go.mod"
GO_SUM="$GO_ADBC/go.sum"
GO_MOD_BACKUP="$GO_MOD.prebuild.bak"
GO_SUM_BACKUP="$GO_SUM.prebuild.bak"
cp "$GO_MOD" "$GO_MOD_BACKUP"
cp "$GO_SUM" "$GO_SUM_BACKUP"
restore_modfiles() {
    [[ -f "$GO_MOD_BACKUP" ]] && mv "$GO_MOD_BACKUP" "$GO_MOD" && echo "[trap] restored $GO_MOD" >&2
    [[ -f "$GO_SUM_BACKUP" ]] && mv "$GO_SUM_BACKUP" "$GO_SUM" && echo "[trap] restored $GO_SUM" >&2
}
trap restore_modfiles EXIT

echo "[3/6] Adding replace directive: arrow-go/v18 => $ARROW_GO_PR793_DIR"
if ! grep -qE "^replace github\.com/apache/arrow-go/v18" "$GO_MOD"; then
    printf '\nreplace github.com/apache/arrow-go/v18 => %s\n' "$ARROW_GO_PR793_DIR" >> "$GO_MOD"
fi
echo "      Running go mod tidy to register local arrow-go..."
( cd "$GO_ADBC" && go mod tidy 2>&1 | tail -10 )

echo "[4/6] Building libadbc_driver_flightsql.so..."
( cd "$GO_ADBC" && go build -tags driverlib -buildmode=c-shared -o "$OUTPUT_SO" ./pkg/flightsql )

# Verify markers. Use grep -c to avoid SIGPIPE-from-grep-q under pipefail.
echo "[5/6] Verifying patched markers in $OUTPUT_SO..."
n_pr793=$(strings "$OUTPUT_SO" | grep -c 'nativeCRecordBatchReader).Retain' || true)
if [[ "$n_pr793" -gt 0 ]]; then
    echo "      OK: PR793 nativeCRecordBatchReader.Retain symbol present ($n_pr793 ref)"
else
    echo "      MISSING: PR793 markers — replace directive may not have wired through" >&2
    exit 1
fi

# Informational: count direct runtime.GC call sites. Original driver had 4
# (one per Release function); patched driver should have 0.
n_gc=$(go tool nm "$OUTPUT_SO" 2>/dev/null | grep -c 'runtime\.GC$' || true)
echo "      runtime.GC symbol references in .so: $n_gc (informational)"

echo "[6/6] Build complete: $OUTPUT_SO"
ls -la "$OUTPUT_SO"

restore_modfiles
trap - EXIT

if [[ "$RESTORE_BRANCH" == "1" && "$orig_branch" != "DETACHED" && "$orig_branch" != "$FIX_BRANCH" ]]; then
    echo "[+] Restoring arrow-adbc to branch '$orig_branch'..."
    git -C "$GO_ADBC" checkout "$orig_branch"
fi

echo "DONE."
