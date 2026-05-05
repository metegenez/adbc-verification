#!/usr/bin/env bash
# Runs the repro from the host, matching FE's environment as closely as possible.
#
# Usage: ./run.sh [iterations] [threads] [persistent]
#   iterations: number of open/connect/query/close cycles (default 500)
#   threads:    parallel workers (default 1)
#   persistent: 'true' to reuse Database+Connection across iterations (default false)

set -euo pipefail
cd "$(dirname "$0")"

ITERS="${1:-500}"
THREADS="${2:-1}"
PERSISTENT="${3:-false}"

DRIVER_SO="${DRIVER_SO:-/home/mete/coding/opensource/adbc_verification/docker/drivers/libadbc_driver_flightsql.so}"
URI="${URI:-grpc://127.0.0.1:9408}"

JDK_HOME="${JDK_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
LIBJSIG="${JDK_HOME}/lib/libjsig.so"

if [[ ! -f "$LIBJSIG" ]]; then
  echo "libjsig.so not found at $LIBJSIG — install openjdk-17-jdk or set JDK_HOME" >&2
  exit 1
fi
if [[ ! -f "$DRIVER_SO" ]]; then
  echo "Driver .so not found at $DRIVER_SO" >&2
  exit 1
fi
if [[ ! -d target/lib ]] || [[ ! -f target/jvm-jni-repro-1.0-SNAPSHOT.jar ]]; then
  echo "Building (mvn package -DskipTests -Denforcer.skip=true)..."
  mvn -q package -DskipTests -Denforcer.skip=true
fi

export LD_PRELOAD="${LIBJSIG}${LD_PRELOAD:+:$LD_PRELOAD}"
export GODEBUG="${GODEBUG:-asyncpreemptoff=1}"

echo "LD_PRELOAD=$LD_PRELOAD"
echo "GODEBUG=$GODEBUG"
echo

XMX="${XMX:-2048m}"

exec java \
  -XX:+UseG1GC -Xmx${XMX} -Xms${XMX} \
  -XX:ErrorFile=hs_err_pid%p.log \
  --add-opens=java.base/java.nio=ALL-UNNAMED \
  --add-opens=java.base/sun.nio.ch=ALL-UNNAMED \
  -Drepro.driver="$DRIVER_SO" \
  -Drepro.uri="$URI" \
  -Drepro.iterations="$ITERS" \
  -Drepro.threads="$THREADS" \
  -Drepro.persistent="$PERSISTENT" \
  ${QUERY:+-Drepro.query="$QUERY"} \
  ${HEAP_PRESSURE:+-Drepro.heappressure="$HEAP_PRESSURE"} \
  ${FORCE_GC:+-Drepro.forcegc="$FORCE_GC"} \
  ${POOL:+-Drepro.pool="$POOL"} \
  ${MODE:+-Drepro.mode="$MODE"} \
  ${IDLE_THREADS:+-Drepro.idleThreads="$IDLE_THREADS"} \
  ${BUGGY_CLOSE:+-Drepro.buggyClose="$BUGGY_CLOSE"} \
  -jar target/jvm-jni-repro-1.0-SNAPSHOT.jar
