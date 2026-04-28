# Phase 4: FlightSQL TPC-H Queries Against External StarRocks — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `04-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-28
**Phase:** 04-flightsql-tpc-h-queries-against-external-starrocks-with-arro
**Areas discussed:** External StarRocks setup, Data source for sr-external, Query corpus & coexistence, Auth/TLS coverage

---

## Area Selection

| Option | Description | Selected |
|---|---|---|
| External StarRocks setup | How sr-external is constructed, service name, port exposure, FE/BE topology | ✓ |
| Data source for sr-external | Native tables vs federation; CSV delivery; loader; DDL location | ✓ |
| Query corpus & coexistence | Number of queries, directory, catalog name, sqlflite coexistence | ✓ |
| Auth/TLS coverage | Auth mode, TLS, test scenarios, URI/port | ✓ |

**User's choice:** All four areas selected (multi-select).

---

## External StarRocks Setup

### Q1 — How is the external StarRocks container constructed?

| Option | Description | Selected |
|---|---|---|
| Reuse sr-main image (Recommended) | Same Dockerfile/.deb, second container | ✓ |
| Slim image (no ADBC drivers) | Custom Dockerfile, smaller image | |
| Different StarRocks .deb version | Cross-version Arrow Flight compatibility | |

**User's choice:** Reuse sr-main image.

### Q2 — Compose service name and host port exposure for sr-external?

| Option | Description | Selected |
|---|---|---|
| sr-external, no host ports (Recommended) | Service name 'sr-external'. Docker DNS only. | (effectively chosen, conditional) |
| sr-external, FE Flight published to host | Publish 9408 for host-side debug | |
| sr-flightsql-starrocks, no host ports | More descriptive name | |

**User's choice (free text):** *"it will be inside the docker compose, but issue is we need to load to into it, so, publishing some sort of port is depending on how we push data inside. if we copy the csv inside starrocks and directly create a table from tpch csvs, i dont think it is necessary"*

**Notes:** User tied the port-exposure decision directly to the data-loading approach. After resolving the data-source question (in-container CSV bind-mount + `FILES()`), no host port is needed. Service name `sr-external` adopted.

### Q3 — FE/BE topology for sr-external?

| Option | Description | Selected |
|---|---|---|
| FE+BE co-located, single container (Recommended) | Mirror sr-main pattern (Phase 1 D-02) | ✓ |
| Separate FE and BE containers | Closer to real deployment | |

**User's choice:** FE+BE co-located.

### Q4 — Init/boot timing — how does sr-external get ready before sr-main needs it?

| Option | Description | Selected |
|---|---|---|
| sr-main depends_on sr-external, healthcheck (Recommended) | depends_on with condition: service_healthy | ✓ |
| sr-main depends_on sr-external, service_started only | No healthcheck — flaky | |
| No dependency, fixture polls Arrow Flight port | Fixture-side polling | |

**User's choice:** depends_on with healthcheck.

---

## Data Source for sr-external

### Q1 — Where do TPC-H tables in sr-external get their data from?

| Option | Description | Selected |
|---|---|---|
| Native StarRocks tables, SF1 CSVs (Recommended) | Real Arrow Flight workload | ✓ |
| Native StarRocks tables, seed data only (5 rows) | Smoke level | |
| sr-external federates to sr-postgres/sr-mysql | Another catalog hop | |

**User's choice:** Native StarRocks tables, SF1 CSVs.

### Q2 — How are SF1 CSVs delivered into sr-external?

| Option | Description | Selected |
|---|---|---|
| Bind-mount docker/data/sf1/ read-only (Recommended) | Same dir Phase 2 mounts; avoids chown trap | ✓ |
| COPY CSVs into the image at build time | Hermetic but ~900MB image | |
| Generate inside the container at startup | Couples boot to data gen | |

**User's choice:** Bind-mount read-only.

### Q3 — Which StarRocks loader populates the tables from CSVs?

| Option | Description | Selected |
|---|---|---|
| INSERT INTO ... SELECT FROM FILES() (Recommended) | Native StarRocks FILES() table function | ✓ |
| Stream Load (HTTP PUT to FE/BE) | Needs host or sidecar driver | |
| Broker Load | Requires broker config | |

**User's choice:** INSERT INTO … SELECT FROM FILES().

### Q4 — Where does the TPC-H DDL for sr-external live, and how is it run?

| Option | Description | Selected |
|---|---|---|
| docker/init/sr-external/*.sql, run by entrypoint (Recommended) | Mirrors Phase 1 init pattern | ✓ |
| Single docker/init/sr-external/init.sql with DDL + LOAD | Simpler, harder to iterate | |
| External Python loader script | Decouples but adds CLI step | |

**User's choice:** docker/init/sr-external/*.sql, run by sr-external's entrypoint (same script as sr-main, inherited via the reused image).

---

## Query Corpus & Coexistence

### Q1 — How many TPC-H queries run through the FlightSQL→sr-external path?

| Option | Description | Selected |
|---|---|---|
| Full 22 TPC-H queries on SF1 (Recommended) | Matches queries/postgres/, queries/mysql/ | ✓ |
| Reduced corpus (e.g., Q1, Q3, Q5, Q10) | Faster suite, less coverage | |
| Two queries (parity with today's queries/flightsql/) | Smoke only | |

**User's choice:** Full 22 TPC-H queries on SF1.

### Q2 — Where do the new query files live?

| Option | Description | Selected |
|---|---|---|
| queries/flightsql-starrocks/ (Recommended) | New top-level directory | ✓ |
| queries/flightsql/ (replace existing) | Couples this phase to retiring sqlflite | |
| queries/flightsql/sr-external/ (subdirectory) | Subdir as new driver param | |

**User's choice:** queries/flightsql-starrocks/.

### Q3 — How do the new TPC-H query files address the FlightSQL→sr-external catalog?

| Option | Description | Selected |
|---|---|---|
| Catalog name sr_flightsql_starrocks (Recommended) | Verbose but explicit; preserves sr_flightsql namespace | ✓ |
| Catalog name sr_flightsql (rename current) | Forward-looking but churn-y | |
| Catalog name sr_arrow | Doesn't follow sr_<driver> pattern | |

**User's choice:** sr_flightsql_starrocks.

### Q4 — What happens to the existing sqlflite-based FlightSQL tests and queries?

| Option | Description | Selected |
|---|---|---|
| Keep alongside; new tests in test_flightsql_starrocks.py (Recommended) | Two FlightSQL paths verified independently | ✓ |
| Replace sqlflite with sr-external entirely | Loses generic Arrow Flight verification | |
| Keep services, fold new tests into test_flightsql.py | Mixes concerns | |

**User's choice:** Keep alongside; new test_flightsql_starrocks.py.

---

## Auth/TLS Coverage

### Q1 — What authentication mode does sr-external's Arrow Flight server use?

| Option | Description | Selected |
|---|---|---|
| StarRocks root, empty password (Recommended) | Matches sr_conn fixture convention | ✓ |
| Dedicated user with non-empty password | More realistic; one extra DDL | |
| Anonymous / no auth | Probably not supported by StarRocks Arrow Flight | |

**User's choice:** StarRocks root, empty password.

### Q2 — TLS coverage for the sr-external Arrow Flight connection?

| Option | Description | Selected |
|---|---|---|
| Plaintext only (grpc://) for v1 (Recommended) | TLS pass-through still covered by existing sqlflite TLS test | ✓ |
| Both plaintext and TLS | Cert generation + StarRocks-side Arrow Flight TLS config | |
| TLS only | No fallback if TLS config fails | |

**User's choice:** Plaintext only for v1.

### Q3 — Which catalog scenarios does test_flightsql_starrocks.py cover?

| Option | Description | Selected |
|---|---|---|
| Lifecycle + data + wrong-password + passthrough (Recommended) | Mirrors test_flightsql.py minus TLS scenario | ✓ |
| Lifecycle + data only (two tests) | Skips negative + passthrough | |
| Lifecycle + data + wrong-password + passthrough + TLS | Only meaningful if TLS picked above | |

**User's choice:** Lifecycle + data + wrong-password + passthrough (4 scenarios).

### Q4 — How does sr-main reach sr-external's FE Arrow Flight port?

| Option | Description | Selected |
|---|---|---|
| grpc://sr-external:9408 (FE Arrow Flight) (Recommended) | FE port — already in Dockerfile | ✓ |
| grpc://sr-external:9419 (BE Arrow Flight) | Bypasses FE planning | |
| TBD — documented in research/planning | Defer to researcher | |

**User's choice:** grpc://sr-external:9408 (FE Arrow Flight).

---

## Claude's Discretion

User explicitly deferred (or accepted as researcher/planner discretion):

- Exact `FILES()` invocation: format options, NULL marker, header handling
- Schema/database name in sr-external (`tpch` vs `default`)
- Healthcheck `start_period` value for sr-external SF1 load (measure empirically)
- In-container mount path for `docker/data/sf1/` on sr-external
- Whether sr-external needs any `conf.d` overrides beyond the image defaults
- Expected-row-count derivation strategy for the 22 SF1 queries on sr-external
- Catalog cleanup pattern in `test_flightsql_starrocks.py` (try/finally)
- Whether `run-verify.py` needs any change

## Deferred Ideas

- TLS-enabled sr-external Arrow Flight
- Cross-version Arrow Flight (different `.deb` per side)
- Benchmarking Arrow Flight vs MySQL-protocol fetch
- Cross-driver JOINs that include `sr_flightsql_starrocks`
- Retiring sqlflite once external StarRocks proves stable
- Refactoring `test_flightsql.py` into a parametric module
- Stream Load / Broker Load as alternative loaders
- Generate-inside-container SF1 path
