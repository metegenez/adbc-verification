#!/usr/bin/env bash
# Fetch MySQL Connector/J 9.3.0 into docker/drivers/ for the StarRocks JDBC catalog.
#
# This JAR is required by the Phase 3 benchmark CLI (benchmark/mysql-jdbc-vs-adbc.py).
# It is NOT committed to git (docker/drivers/ is gitignored, mirroring the .so flow);
# each contributor runs this script once after cloning.
#
# After fetching, rebuild the StarRocks image:
#   docker compose -f docker/docker-compose.yml up --build -d
#
# Idempotent: re-running is safe; downloads only if the file is missing or
# size-mismatched.

set -euo pipefail

JAR_VERSION="9.3.0"
JAR_FILENAME="mysql-connector-j-${JAR_VERSION}.jar"
JAR_URL="https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/${JAR_VERSION}/${JAR_FILENAME}"

# Resolve docker/drivers/ relative to this script (works from any cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVERS_DIR="${SCRIPT_DIR}/drivers"
JAR_PATH="${DRIVERS_DIR}/${JAR_FILENAME}"

mkdir -p "${DRIVERS_DIR}"

if [[ -f "${JAR_PATH}" ]]; then
    SIZE=$(stat -c%s "${JAR_PATH}" 2>/dev/null || stat -f%z "${JAR_PATH}")
    if [[ "${SIZE}" -gt 1000000 ]]; then
        echo "✓ ${JAR_FILENAME} already present (${SIZE} bytes); skipping download"
        exit 0
    fi
    echo "! ${JAR_FILENAME} present but truncated (${SIZE} bytes); re-downloading"
fi

echo "◆ Downloading ${JAR_FILENAME} from Maven Central..."
curl -fsSL -o "${JAR_PATH}" "${JAR_URL}"

SIZE=$(stat -c%s "${JAR_PATH}" 2>/dev/null || stat -f%z "${JAR_PATH}")
if [[ "${SIZE}" -lt 1000000 ]]; then
    echo "✗ Downloaded file is suspiciously small (${SIZE} bytes); aborting" >&2
    rm -f "${JAR_PATH}"
    exit 1
fi

echo "✓ ${JAR_FILENAME} fetched (${SIZE} bytes) -> ${JAR_PATH}"
echo ""
echo "Next: rebuild the StarRocks image to bake the JAR in:"
echo "  docker compose -f docker/docker-compose.yml up --build -d"
