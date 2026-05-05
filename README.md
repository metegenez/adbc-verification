# StarRocks ADBC Verification Suite

End-to-end verification and benchmarking for StarRocks' ADBC catalog stack. Spins up StarRocks (FE + BE) alongside backend data sources (PostgreSQL, MySQL, FlightSQL/SQLite, DuckDB, plus a second StarRocks instance for Arrow Flight) in Docker Compose, then runs:

- **39 pytest cases** across 8 modules — catalog lifecycle, data correctness, error paths, TLS, federation
- **Auto-discovered query suite** — every `.sql` file under `queries/` runs against its target catalog
- **TPC-H SF1 benchmarks** — JDBC vs ADBC head-to-head for both MySQL and StarRocks-to-StarRocks (Arrow Flight)

One command does the full ship → verify → retest loop: `./run-verify.py fe.deb be.deb`.

## Quick Start

### Prerequisites

- Docker and Docker Compose v2
- Python 3.11+ with venv
- StarRocks `.deb` packages (FE + BE) — build via `ship-starrocks` skill
- ADBC drivers installed via `dbc install`
- MySQL Connector/J JAR (for the JDBC catalog used in benchmarks)

### One-Time Setup

```bash
# 1. Create Python venv and install deps
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Install ADBC drivers (5 drivers)
~/.local/bin/dbc install sqlite flightsql postgresql duckdb mysql

# 3. Copy driver .so files to docker/drivers/ (read by sr-main image at build time)
mkdir -p docker/drivers
cp ~/.config/adbc/drivers/libadbc_driver_*.so docker/drivers/

# 4. Fetch MySQL Connector/J JAR for the JDBC benchmark catalog (one-time)
bash docker/fetch-jdbc-jar.sh

# 5. Generate pre-baked test data (SF1 CSVs + .db files)
python docker/generate-data.py
```

### Full Verification Cycle

```bash
./run-verify.py /path/to/starrocks-fe.deb /path/to/starrocks-be.deb
```

Copies `.deb` packages into `docker/`, builds the Docker image, waits for healthchecks, runs the full pytest suite, and reports results.

### Fast Iteration

Containers stay running by default (`--keep`). Re-run tests without rebuilding:

```bash
# Drop in new .debs and rebuild only sr-main
cp /path/to/new-fe.deb docker/starrocks-fe_latest_amd64.deb
cp /path/to/new-be.deb docker/starrocks-be_latest_amd64.deb
docker compose -f docker/docker-compose.yml up -d --build sr-main

# Re-run a subset
.venv/bin/pytest tests/ -k flightsql -v
.venv/bin/pytest tests/ -k "sqlite or duckdb" -v
.venv/bin/pytest tests/ -k "not tls" -v
```

### Running Tests Directly

```bash
source .venv/bin/activate
export STARROCKS_HOST=127.0.0.1 STARROCKS_PORT=9030

pytest tests/ -v                                      # all
pytest tests/test_postgres.py -v                       # one module
pytest tests/test_flightsql.py -k "test_name" -v -s    # one test
pytest tests/test_queries.py -v                        # auto-discovered .sql files
```

## Benchmarks

Two TPC-H SF1 benchmarks live under `benchmark/`. Both run identical queries through two catalogs side-by-side (one JDBC, one ADBC) and print a per-query timing comparison plus arithmetic + geometric averages.

```bash
# StarRocks-to-StarRocks: JDBC (MySQL protocol) vs ADBC (Arrow Flight)
.venv/bin/python -u benchmark/starrocks-jdbc-vs-adbc.py --queries all --runs 10 --timeout 120

# Backend MySQL: JDBC (MySQL Connector/J) vs ADBC (Go-based mysql driver)
.venv/bin/python -u benchmark/mysql-jdbc-vs-adbc.py --queries all --runs 10 --timeout 60
```

Common flags: `--queries 1,3,5` to run a subset, `--runs N` measurement runs (a warmup is always added), `--timeout N` per-query cap.

### Initial Performance Indicators for ADBC MySQL

We need to improve connection handling for ADBC and increase the scale factor for putting more workload on data read, since most of the queries require much less data.

```
═══════════════════════════════════════════════════════════════════════════════════════════
 MySQL JDBC vs ADBC Benchmark
 Scale: sf1 | Queries: 22 | Runs: 10 (+1 warmup) | Timeout: 60s
═══════════════════════════════════════════════════════════════════════════════════════════
+-------+-----------------+-----------------+-------------+-----------------+-----------------+-------------+
| Query | JDBC total (ms) | ADBC total (ms) | Total ratio | JDBC scan (ms)  | ADBC scan (ms)  | Scan ratio  |
+-------+-----------------+-----------------+-------------+-----------------+-----------------+-------------+
| Q01   |         11445.0 |         14509.0 |        0.79 |         11458.2 |         14522.3 |        0.79 |
| Q02   |           473.2 |           796.1 |        0.59 |            89.9 |           159.2 |        0.58 |
| Q03   |          4576.9 |          4577.8 |        1.00 |          1857.2 |          1675.0 |        1.47 |
| Q04   |          7998.1 |          2770.9 |        2.89 |          3992.0 |          1377.8 |        2.13 |
| Q05   |          4010.3 |          7571.8 |        0.53 |           722.0 |          1314.0 |        0.76 |
| Q06   |          1151.9 |          1141.3 |        1.01 |          1139.8 |          1126.7 |        1.01 |
| Q07   |          2867.8 |          2776.1 |        1.03 |           568.5 |           544.4 |        0.86 |
| Q08   |          4543.1 |          7932.7 |        0.57 |           872.3 |          1410.9 |        0.75 |
| Q09   |          6200.2 |         11194.1 |        0.55 |          3854.1 |           461.3 |       23.81 |
| Q10   |          1448.4 |          2224.0 |        0.65 |           485.7 |           712.8 |        0.73 |
| Q11   |           539.0 |           867.1 |        0.62 |           154.1 |           268.1 |        0.56 |
| Q12   |          1530.3 |          1545.0 |        0.99 |          1051.1 |          1036.3 |        1.03 |
| Q13   |           848.4 |           789.9 |        1.07 |           423.6 |           392.6 |        1.08 |
| Q14   |          1120.5 |          1134.2 |        0.99 |           577.8 |           584.2 |        0.98 |
| Q15   |          1016.4 |          1116.3 |        0.91 |           663.3 |           728.8 |        0.89 |
| Q16   |           309.2 |           242.6 |        1.27 |           111.0 |            90.4 |        1.04 |
| Q17   |          3845.5 |          7834.3 |        0.49 |          1939.5 |          6397.4 |        0.25 |
| Q18   |          2744.4 |          5168.1 |        0.53 |          1964.1 |          3091.5 |        0.76 |
| Q19   |          1623.0 |          1677.1 |        0.97 |            63.1 |          1633.0 |        0.04 |
| Q20   |          1401.0 |          1366.4 |        1.03 |           356.9 |           344.4 |        0.85 |
| Q21   |          8226.9 |          2873.0 |        2.86 |          3152.3 |          1335.1 |        1.59 |
| Q22   |           391.2 |           379.3 |        1.03 |            80.8 |           165.7 |        0.48 |
+-------+-----------------+-----------------+-------------+-----------------+-----------------+-------------+
| AVG   |          3105.0 |          3658.5 |        1.02 |          1617.1 |          1789.6 |        1.93 |
| GEOM  |          1935.5 |          2160.0 |        0.90 |           698.4 |           838.3 |        0.86 |
+-------+-----------------+-----------------+-------------+-----------------+-----------------+-------------+
```

```
═══════════════════════════════════════════════════════════════════════════════════════════
 StarRocks to Starrocks JDBC(MySQL) vs ADBC(FlightSQL) Benchmark
 Scale: sf1 | Queries: 22 | Runs: 10 (+1 warmup) | Timeout: 120s
═══════════════════════════════════════════════════════════════════════════════════════════
+-------+-----------------+-----------------+-------------+-----------------+-----------------+-------------+
| Query | JDBC total (ms) | ADBC total (ms) | Total ratio | JDBC scan (ms)  | ADBC scan (ms)  | Scan ratio  |
+-------+-----------------+-----------------+-------------+-----------------+-----------------+-------------+
| Q01   |         11338.1 |           821.7 |       13.80 |         11305.0 |           810.6 |       13.95 |
| Q02   |           827.2 |           413.2 |        2.00 |           102.4 |           108.2 |        0.71 |
| Q03   |          4700.3 |           429.0 |       10.96 |          1849.1 |           189.1 |        7.01 |
| Q04   |          7311.6 |           354.7 |       20.61 |          3606.7 |           155.6 |       15.69 |
| Q05   |          4112.2 |           823.4 |        4.99 |           695.5 |           167.4 |        1.79 |
| Q06   |           261.5 |           127.6 |        2.05 |           197.4 |            85.5 |        2.31 |
| Q07   |          3045.2 |           482.5 |        6.31 |           568.3 |           122.8 |        2.71 |
| Q08   |          4728.1 |           772.3 |        6.12 |           851.5 |           163.9 |        2.47 |
| Q09   |          6121.0 |          1093.9 |        5.60 |          1224.6 |           132.6 |        9.23 |
| Q10   |          1255.9 |           367.4 |        3.42 |           340.5 |           146.6 |        1.75 |
| Q11   |           705.4 |           327.8 |        2.15 |           149.6 |            88.6 |        1.43 |
| Q12   |           650.2 |           196.9 |        3.30 |           319.3 |           102.2 |        2.83 |
| Q13   |           853.3 |           279.2 |        3.06 |           388.8 |           152.6 |        2.05 |
| Q14   |           245.4 |           155.1 |        1.58 |           100.0 |            79.2 |        1.32 |
| Q15   |           455.0 |           188.6 |        2.41 |           234.6 |           109.8 |        1.95 |
| Q16   |           418.5 |           221.3 |        1.89 |            98.1 |           103.9 |        0.83 |
| Q17   |          3884.5 |           649.4 |        5.98 |          1891.5 |           524.8 |        3.21 |
| Q18   |          2833.8 |           635.3 |        4.46 |          1942.6 |           348.2 |        5.04 |
| Q19   |           265.3 |           176.8 |        1.50 |            15.5 |            86.2 |        0.18 |
| Q20   |          1471.8 |           380.2 |        3.87 |           326.2 |           108.4 |        2.51 |
| Q21   |          8133.5 |           658.9 |       12.34 |          3015.9 |           283.3 |        7.12 |
| Q22   |           472.8 |           186.8 |        2.53 |            83.6 |            94.6 |        0.88 |
+-------+-----------------+-----------------+-------------+-----------------+-----------------+-------------+
| AVG   |          2913.2 |           442.8 |        5.50 |          1332.1 |           189.3 |        3.95 |
| GEOM  |          1530.2 |           370.4 |        4.13 |           462.5 |           150.7 |        2.46 |
+-------+-----------------+-----------------+-------------+-----------------+-----------------+-------------+
```

## FlightSQL ADBC Under Sustained Load

Loading the Go-based FlightSQL ADBC driver (`libadbc_driver_flightsql.so`) into a long-lived JVM via `JniDriverFactory` is fragile: under sustained workloads, the JVM crashes within tens of ADBC operations with one of three signatures (heap corruption in GC sweep, `addr=0x118` in the unwinder, or `memmove` inside gRPC's `loopyWriter`) — all consistent with the Go runtime catching freed-but-still-referenced state.

The image baked here ships the workaround that keeps it stable: `LD_PRELOAD=$JAVA_HOME/lib/libjsig.so` (JDK-shipped signal chaining) and `GODEBUG=asyncpreemptoff=1` (disable Go SIGURG-based preemption). Both are wired into `docker/entrypoint.sh`. With these, the StarRocks-to-StarRocks benchmark above runs 10×22×2 ≈ 440 ADBC operations on a single FE without restart.

The full investigation (14 cycles, ablation matrix, and the unverified Cycle 8 root-cause hypothesis around JNI shim parent-handle backrefs) lives at `.planning/debug/flightsql-adbc-fe-crash.md`. A draft for an upstream `apache/arrow-adbc` discussion lives at `.planning/debug/upstream-discussion-draft.md`. Local rebuilds of the patched `.so` go through `docker/build-flightsql-driver.sh`.

## Project Structure

```
benchmark/
  starrocks-jdbc-vs-adbc.py   # JDBC (MySQL protocol) vs ADBC (Arrow Flight) on sr-external
  mysql-jdbc-vs-adbc.py       # JDBC (Connector/J) vs ADBC (Go mysql) on sr-mysql
  explain_parser.py           # Extracts scan timings from StarRocks EXPLAIN output
docker/
  docker-compose.yml          # 6 services on sr-net bridge network
  Dockerfile                  # StarRocks container from ubuntu:24.04 with .deb install
  entrypoint.sh               # FE+BE startup, BE registration, libjsig + GODEBUG exports
  build-flightsql-driver.sh   # Reproducible patched .so build (Attempts 1+4 + arrow-go PR #793)
  fetch-jdbc-jar.sh           # Fetches mysql-connector-j JAR for benchmarks
  init/                       # Backend init SQL (auto-executed at container startup)
    postgres/                 # TPC-H schema + SF1 data
    mysql/                    # TPC-H schema + SF1 data
    sqlflite/                 # SQLite-compatible TPC-H schema (8 tables)
    sr-external/              # External StarRocks TPC-H schema + SF1 load
  data/                       # Pre-baked .db files + SF1 CSVs (gitignored, regenerated locally)
  certs/                      # Self-signed TLS certificates
  drivers/                    # ADBC driver .so files (gitignored, copied from host at build time)
queries/                      # Externalized SQL query files
  tpch/                       # 22 canonical TPC-H queries with {catalog}.{db} placeholders
  sqlite/                     # 2 TPC-H queries (select, join)
  postgres/                   # 2 TPC-H queries (select, join)
  mysql/                      # 2 TPC-H queries (select, join)
  flightsql/                  # 2 TPC-H queries (select, join)
  duckdb/                     # 2 TPC-H queries (select, join)
  cross-join/                 # Cross-driver federation queries
tests/                        # 39 pytest cases across 8 modules + auto-discovered query files
  test_queries.py             # Auto-discovers and runs every .sql under queries/
  test_flightsql_starrocks.py # 4 tests against sr-external (Arrow Flight, Phase 4)
lib/
  catalog_helpers.py          # CREATE/DROP CATALOG SQL helpers
conftest.py                   # pytest fixtures (Docker Compose-aware)
run-verify.py                 # CLI runner — ship→verify→retest loop
.planning/
  debug/                      # Active debug sessions (see flightsql-adbc-fe-crash.md)
  spikes/                     # Standalone reproducers (see jvm-jni-repro/)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STARROCKS_HOST` | `127.0.0.1` | StarRocks FE host (port 9030 published from container) |
| `STARROCKS_PORT` | `9030` | StarRocks FE MySQL port |

## Docker Compose Services

| Service | Port (internal) | Host Port | Description |
|---------|-----------------|-----------|-------------|
| `sr-main` | 9030, 9408 | 9030, 9408 | StarRocks FE+BE with 5 ADBC drivers + Arrow Flight |
| `sr-external` | 9030, 9408 | 9031, 9418 | Second StarRocks instance — Arrow Flight target for FlightSQL ADBC |
| `sr-postgres` | 5432 | — | PostgreSQL 16 with TPC-H SF1 data |
| `sr-mysql` | 3306 | — | MySQL 8.0 with TPC-H SF1 data |
| `sr-flightsql` | 31337 | — | FlightSQL (sqlflite) without TLS |
| `sr-flightsql-tls` | 31337 | 31338 | FlightSQL (sqlflite) with TLS |

All services communicate via Docker DNS on the `sr-net` bridge network.

## Test Coverage

- **39 tests** across 8 modules — catalog lifecycle, data correctness, error paths
- **5 ADBC drivers**: SQLite, DuckDB, MySQL, PostgreSQL, FlightSQL
- **2 FlightSQL targets**: sqlflite (Phase 1) + external StarRocks via Arrow Flight (Phase 4)
- **TPC-H queries**: 22 canonical queries × multiple backends, plus 2 select/join queries per legacy driver dir
- **Cross-driver federation**: SQLite ↔ PostgreSQL, SQLite ↔ SQLite JOINs
- **TLS**: FlightSQL and PostgreSQL with self-signed certificates
- **Error paths**: Bad URIs, wrong passwords, missing entrypoints, unknown keys

## pytest Markers

| Marker | Description |
|--------|-------------|
| `sqlite` / `flightsql` / `postgres` / `duckdb` / `mysql` | Per-driver tests |
| `cross_join` | Cross-driver federation tests |
| `negative` | Error path validation tests |
| `tls` | TLS-enabled tests |

## CLI Reference

```
usage: run-verify.py [-h] [--keep | --cleanup] [--subset FILTER]
                     [--report FILE] [--skip-rebuild]
                     fe_deb be_deb

StarRocks ADBC Verification Suite — ship→verify→retest loop

positional arguments:
  fe_deb           Path to starrocks-fe .deb package
  be_deb           Path to starrocks-be .deb package

options:
  -h, --help       show this help message and exit
  --keep           Leave containers running after tests (default)
  --cleanup        Run docker compose down after tests
  --subset FILTER  Pass filter to pytest -k (e.g., "flightsql")
  --report FILE    Write JSON report to FILE (default: reports/latest.json)
  --skip-rebuild   Skip docker compose build (reuse existing images)
```

### Examples

```bash
# Full cycle, leave containers running
./run-verify.py /tmp/starrocks-fe_3.4_amd64.deb /tmp/starrocks-be_3.4_amd64.deb

# Run only FlightSQL tests, clean up after
./run-verify.py --subset flightsql --cleanup fe.deb be.deb

# Skip rebuild (reuse cached image), save report
./run-verify.py --skip-rebuild --report report-v2.json fe.deb be.deb
```

## Troubleshooting

- **Tests fail but containers are healthy**: `docker compose -f docker/docker-compose.yml logs sr-main --tail=50`
- **Container won't start**: ensure `.deb` files exist in `docker/`, check `docker compose ps`
- **Driver not found**: verify `.so` files are in `docker/drivers/`
- **Port conflict**: ports 9030 (sr-main MySQL), 9408 (sr-main Arrow Flight), 9031/9418 (sr-external) must be free
- **MySQL `Too many connections`**: pinned to `--max-connections=500`; if you parallelize tests further, bump it
- **FE crash with Go runtime traceback**: see `.planning/debug/flightsql-adbc-fe-crash.md` — the libjsig + GODEBUG bake-in addresses the common cases; remaining variance points to the unverified Cycle 8 root cause
