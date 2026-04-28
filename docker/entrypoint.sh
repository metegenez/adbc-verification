#!/bin/bash
set -e

# Clean stale PID/lock files from previous runs
rm -f /usr/lib/starrocks/fe/bin/fe.pid
rm -f /var/lib/starrocks/fe/meta/lock
rm -f /usr/lib/starrocks/be/bin/be.pid
mkdir -p /run/starrocks-fe /run/starrocks-be

# Patch priority_networks with container's actual IP at runtime
CONTAINER_IP=$(hostname -i | awk '{print $1}')
CONTAINER_SUBNET=$(echo "$CONTAINER_IP" | sed 's/\.[0-9]*$/.0\/24/')
echo "Container IP: $CONTAINER_IP (network: $CONTAINER_SUBNET)"
echo "priority_networks = $CONTAINER_SUBNET" >> /etc/starrocks/fe/fe.conf
echo "priority_networks = $CONTAINER_SUBNET" >> /etc/starrocks/be/be.conf

# Set JAVA_HOME for BE (start_be.sh --daemon drops Dockerfile ENV; JDBC connector needs it)
echo "JAVA_HOME = /usr/lib/jvm/java-17-openjdk-amd64" >> /etc/starrocks/be/be.conf
echo "/usr/lib/jvm/java-17-openjdk-amd64/lib/server" > /etc/ld.so.conf.d/java.conf
ldconfig

echo "=== Starting StarRocks FE ==="
/usr/lib/starrocks/fe/bin/start_fe.sh --daemon

echo "Waiting for FE to be ready (port 9030)..."
for i in $(seq 1 120); do
    if nc -z 127.0.0.1 9030 2>/dev/null; then
        echo "FE ready after ${i}s"
        break
    fi
    sleep 1
done

if ! nc -z 127.0.0.1 9030 2>/dev/null; then
    echo "ERROR: FE did not start within 120s"
    cat /var/log/starrocks/fe/fe.log 2>/dev/null | tail -30
    exit 1
fi

echo "=== Starting StarRocks BE ==="
/usr/lib/starrocks/be/bin/start_be.sh --daemon

echo "Waiting for BE to be ready (port 9060)..."
for i in $(seq 1 60); do
    if nc -z 127.0.0.1 9060 2>/dev/null; then
        echo "BE ready after ${i}s"
        break
    fi
    sleep 1
done

if ! nc -z 127.0.0.1 9060 2>/dev/null; then
    echo "ERROR: BE did not start within 60s"
    cat /var/log/starrocks/be/be.INFO 2>/dev/null | tail -30
    exit 1
fi

echo "=== Registering BE with FE ==="
echo "Registering BE at ${CONTAINER_IP}:9050"
mysql -uroot -h127.0.0.1 -P9030 -e "ALTER SYSTEM ADD BACKEND '${CONTAINER_IP}:9050';" 2>/dev/null || true

echo "Waiting for BE to register..."
for i in $(seq 1 60); do
    ALIVE=$(mysql -uroot -h127.0.0.1 -P9030 -N -e "SHOW PROC '/backends'" 2>/dev/null | grep -c "true" || echo "0")
    if [ "$ALIVE" -gt 0 ]; then
        echo "BE registered and alive after ${i}s"
        break
    fi
    sleep 1
done

echo "=== StarRocks is ready ==="
echo "  MySQL:        port 9030"
echo "  FE HTTP:      port 8030"
echo "  FE Flight:    port 9408"
echo "  BE Flight:    port 9419"
echo ""

# Run init SQL scripts if mounted at /docker-entrypoint-initdb.d/
if [ -d /docker-entrypoint-initdb.d ]; then
    for f in /docker-entrypoint-initdb.d/*.sql; do
        if [ -f "$f" ]; then
            echo "=== Running init script: $f ==="
            sleep 5
            mysql -uroot -h127.0.0.1 -P9030 < "$f" 2>&1 && echo "  OK: $f" || echo "  WARN: $f had errors (non-fatal)"
        fi
    done
fi

echo "=== Init complete, container running ==="

exec tail -f /var/log/starrocks/fe/fe.log
