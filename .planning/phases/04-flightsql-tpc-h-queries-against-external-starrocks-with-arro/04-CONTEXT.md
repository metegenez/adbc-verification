# Phase 4: FlightSQL TPC-H Queries Against External StarRocks with Arrow Flight Ports — Context

**Gathered:** 2026-04-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a second StarRocks instance ("sr-external") to the Docker Compose verification stack, exposing its Arrow Flight ports (FE 9408 / BE 9419 — already configured in `docker/Dockerfile` but currently unexercised). Load TPC-H SF1 data into sr-external's native StarRocks tables. From `sr-main`, create an ADBC FlightSQL catalog (`sr_flightsql_starrocks`) pointing at sr-external's FE Arrow Flight port and execute TPC-H queries through that path.

The verification path under test:
`sr-main` → ADBC FlightSQL catalog → `grpc://sr-external:9408` (StarRocks Arrow Flight server) → sr-external native StarRocks tables.

**In scope:**
- New `sr-external` Compose service reusing the sr-main image
- TPC-H schema + SF1 data loaded into sr-external as native StarRocks tables
- New `queries/tpch/` canonical TPC-H query home with 22 queries using `{catalog}.{db}` template substitution (single source of truth, eliminating per-backend duplicates)
- New `tests/test_flightsql_starrocks.py` (lifecycle + data + wrong-password + passthrough)
- Plaintext (`grpc://`) connection only

**Out of scope:**
- StarRocks-native Arrow Flight TLS (existing TLS sqlflite test still exercises the FlightSQL ADBC TLS pass-through code path)
- Cross-driver JOINs that include `sr_flightsql_starrocks` (could be added later)
- Benchmarking Arrow Flight vs MySQL-protocol fetch timing (Phase 3 territory; deliberately separate)
- Cross-version Arrow Flight (different `.deb` on sr-external vs sr-main)
- Retiring sqlflite — existing `sr-flightsql` / `sr-flightsql-tls` services and `tests/test_flightsql.py` stay untouched

</domain>

<decisions>
## Implementation Decisions

### External StarRocks Setup
- **D-01:** Reuse the existing sr-main image (same `docker/Dockerfile`, same `.deb`) for sr-external. Same ADBC drivers and the Arrow Flight ports are already baked into `fe.conf` / `be.conf` (`docker/Dockerfile:15-16`, `EXPOSE` line 23). Cheapest path; also validates the as-shipped container in the verifier role.
- **D-02:** Compose service name: `sr-external`. Compose-internal only — no host ports published. Reachable from sr-main via Docker DNS at `sr-external:9408` (FE Arrow Flight). MySQL port (9030) and BE Flight port (9419) also Docker-internal.
- **D-03:** FE+BE co-located in a single container, mirroring Phase 1 D-02. Same `docker/entrypoint.sh` runs FE then BE then registers BE.
- **D-04:** `sr-main depends_on sr-external: { condition: service_healthy }`. sr-external healthcheck reuses sr-main's pattern (`mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"`). `start_period` must accommodate SF1 data load — analogous to sr-mysql's 300s; tune empirically once FILES() load times are measured.

### Data Source for sr-external
- **D-05:** sr-external owns native StarRocks tables under a `tpch` database/schema, populated from Phase 2's SF1 CSVs. Real test of Arrow Flight as a result-fetch path on realistic data volume — not a federated hop back to another backend.
- **D-06:** `docker/data/sf1/` bind-mounted **read-only** into sr-external (path inside container chosen by the planner; needs to be reachable by the StarRocks BE for `FILES()`). Parity with the sr-postgres / sr-mysql mounts already in `docker/docker-compose.yml`. Read-only avoids the MySQL-style chown trap noted in CLAUDE.md.
- **D-07:** Loader: `INSERT INTO tpch.<table> SELECT * FROM FILES('path/to/<table>.csv', format='csv', ...)`. Native StarRocks `FILES()` table function. Single statement per table; runs from the FE; no extra services (no Stream Load HTTP, no broker).
- **D-08:** TPC-H DDL + per-table `INSERT … FROM FILES()` statements live as multiple SQL files under `docker/init/sr-external/`, Compose-mounted into `/docker-entrypoint-initdb.d/`. The existing `docker/entrypoint.sh` (lines 74–83) already runs any `*.sql` in that directory after StarRocks is up — sr-external uses the same image and inherits that loop unchanged.

### Query Corpus & Coexistence
- **D-09:** Full 22 TPC-H queries on SF1, adapted as needed for the StarRocks SQL dialect on the read side. Picked up automatically by `tests/test_queries.py` via its `queries/**/*.sql` discovery glob. Each query file includes the standard `-- Expected: N rows` annotation.
- **D-10 (OVERRIDDEN by 04-CANONICAL-SPEC.md):** ~~New top-level directory `queries/flightsql-starrocks/`.~~ Replaced by `queries/tpch/` as the single canonical TPC-H query home using `{catalog}.{db}` template substitution and per-backend `CANONICAL_BACKENDS` mapping. This eliminates 44 duplicate per-backend query files and supports multi-backend substitution from one source of truth.
- **D-11:** Catalog name `sr_flightsql_starrocks`. Tables addressed as `sr_flightsql_starrocks.tpch.<table>`. The existing `sr_flightsql` namespace continues to map to the sqlflite SQLite seed-data backend.
- **D-12:** **Both FlightSQL paths coexist.** Existing `sr-flightsql` / `sr-flightsql-tls` services, `tests/test_flightsql.py` (5 tests), and `queries/flightsql/` (2 query files) all stay untouched. New `tests/test_flightsql_starrocks.py` covers the StarRocks Arrow Flight path independently.

### Auth / TLS Coverage
- **D-13:** sr-external uses StarRocks `root` with empty password — matches the existing `sr_conn` fixture convention in `conftest.py`. ADBC FlightSQL driver passes `username=root` / `password=""` through to StarRocks Arrow Flight.
- **D-14:** Plaintext only (`grpc://`) for v1. The existing `test_flightsql_tls_lifecycle` against `sr-flightsql-tls` continues to exercise the FlightSQL ADBC TLS pass-through code path on the catalog side, so TLS coverage is not lost.
- **D-15:** `tests/test_flightsql_starrocks.py` scenarios mirror `tests/test_flightsql.py` structure — four tests:
  1. `test_flightsql_sr_catalog_lifecycle` — CREATE / SHOW / SHOW DATABASES / DROP
  2. `test_flightsql_sr_data_query` — SHOW TABLES + small SELECT against `sr_flightsql_starrocks.tpch.region`
  3. `test_flightsql_sr_wrong_password` — error at create or first query
  4. `test_flightsql_sr_adbc_passthrough` — arbitrary `adbc.flight.sql.*` property forwarded without error
  TPC-H query coverage (22 queries) is delivered separately via `test_queries.py` auto-discovery.
- **D-16:** Catalog URI: `grpc://sr-external:9408` — FE Arrow Flight port. Already declared in `docker/Dockerfile:15` and exposed via `EXPOSE` line 23.

### Agent's Discretion
- Exact `FILES()` invocation: format options, NULL marker, header handling. CSVs are LF-terminated (CLAUDE.md MySQL gotcha — same generator output, same lineterminator).
- Schema/database name in sr-external (`tpch` is the natural choice; could be `default` if it simplifies init).
- Healthcheck `start_period` value for sr-external SF1 load — measure empirically. FILES() into native StarRocks tables should be faster than MySQL `LOAD DATA INFILE` of 6M lineitem rows, but still measurable.
- In-container mount path for `docker/data/sf1/` on sr-external (must be readable by BE for `FILES()`).
- Whether sr-external needs any `conf.d` overrides beyond what's already in the image.
- Expected-row-count derivation for the 22 SF1 queries on sr-external — likely identical to the postgres/mysql versions because SF1 data is identical; reuse the same numbers, adjust where StarRocks-side semantics diverge from the postgres/mysql versions.
- Catalog cleanup pattern in `test_flightsql_starrocks.py` (try/finally with `drop_catalog`, matches existing `test_flightsql.py`).
- Whether `run-verify.py` needs any change (the healthcheck loop already accepts services with healthchecks; a new service should "just work").

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — Key Decisions table (Docker Compose, `.deb`-based StarRocks, fixed driver paths, host pytest)
- `.planning/REQUIREMENTS.md` — v1/v2 tables; VAL-05 (FlightSQL test coverage), out-of-scope items
- `.planning/ROADMAP.md` — Phase 4 entry; depends on Phase 3 transitively, on Phase 2 for SF1 data
- `CLAUDE.md` — Pitfalls section: CSV LF line endings, MySQL `:ro` mount trap (read-only mount on this phase intentionally avoids the chown trap), healthcheck timing, `start_period` sizing for SF1 loads, FE SIGSEGV recovery

### Prior Phase Context (this phase builds on these)
- `.planning/phases/01-docker-compose-verification-suite/01-CONTEXT.md` — sr-main image / Dockerfile / entrypoint conventions, FE+BE co-location, driver baking
- `.planning/phases/02-postgresql-and-mysql-tpc-h-sf1-data-loading-and-queries/02-CONTEXT.md` — SF1 CSV generator, bind-mount pattern, idempotent init
- `.planning/phases/03-compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints/03-CONTEXT.md` — Catalog naming precedent (`bench_jdbc` / `bench_adbc`), driver/JAR baking precedent

### Existing Code (read before adding sr-external)
- `docker/Dockerfile` — Arrow Flight ports already configured (lines 15–16); `EXPOSE 9030 8030 9408 9050 9419` (line 23). Reused as-is for sr-external.
- `docker/entrypoint.sh` — `/docker-entrypoint-initdb.d/` runner (lines 74–83). sr-external inherits; new SQL files plug in.
- `docker/docker-compose.yml` — Service patterns: `sr-postgres`, `sr-mysql` (init script + bind-mount pattern), `sr-flightsql`, `sr-flightsql-tls` (kept), healthcheck shapes
- `docker/init/postgres/`, `docker/init/mysql/` — Pattern for Compose-mounted init SQL
- `docker/data/sf1/` — Phase 2 SF1 CSVs (region.csv … lineitem.csv); regenerated by `docker/generate-sf1-data.py`
- `conftest.py` — `STARROCKS_HOST/PORT`, `FLIGHTSQL_DRIVER` constant (`/opt/starrocks/drivers/libadbc_driver_flightsql.so`), `sr_conn` fixture (root / empty password), `flightsql_driver_path` fixture, `capture_on_failure` autouse fixture
- `lib/catalog_helpers.py` — `create_adbc_catalog()`, `drop_catalog()`, `execute_sql()`, `show_catalogs()` — reused unchanged for `sr_flightsql_starrocks`
- `tests/test_flightsql.py` — Template for `tests/test_flightsql_starrocks.py` (4 of 5 scenarios mirror cleanly; TLS scenario intentionally omitted)
- `tests/test_queries.py` — Query-file discovery (`QUERIES_DIR.rglob("*.sql")`), driver-param mapping, `-- Expected: N rows` parser, `-- Skip:` directive
- `queries/postgres/03-q01…q22.sql`, `queries/mysql/03-q01…q22.sql` — 22 TPC-H queries that adapt cleanly for StarRocks dialect

### StarRocks Reference (planner / researcher must verify)
- StarRocks `FILES()` table function — CSV format, NULL handling, schema inference vs explicit casting
- StarRocks Arrow Flight server — FE port 9408 vs BE port 9419, auth model, query routing
- StarRocks ADBC FlightSQL catalog — property names for `username` / `password` over Arrow Flight to StarRocks (compare with sqlflite usage in `tests/test_flightsql.py`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docker/Dockerfile`: Already has `arrow_flight_port = 9408` (FE) and `9419` (BE) baked into `fe.conf` / `be.conf`. sr-external reuses this image — no Dockerfile change needed for the Arrow Flight side.
- `docker/entrypoint.sh`: Runs `*.sql` in `/docker-entrypoint-initdb.d/` after StarRocks is up. sr-external inherits this; only the mount target changes.
- `docker/data/sf1/`: Phase 2 CSVs reused as-is. No new generator step.
- `conftest.py`: `FLIGHTSQL_DRIVER` constant + `flightsql_driver_path` fixture both reused unchanged for the new catalog.
- `lib/catalog_helpers.py`: Pure SQL catalog helpers — work for any FlightSQL endpoint, including StarRocks.
- `tests/test_queries.py`: Canonical loader (per 04-CANONICAL-SPEC.md) reads `queries/tpch/q*.sql` and substitutes `{catalog}.{db}` per backend.
- `tests/test_flightsql.py`: Direct template for `tests/test_flightsql_starrocks.py` (4 scenarios reuse cleanly; TLS one is intentionally not carried over).

### Established Patterns
- Service naming: `sr-<role>` (sr-main, sr-mysql, sr-postgres, sr-flightsql, sr-flightsql-tls). `sr-external` follows it.
- Fixed container-internal driver paths under `/opt/starrocks/drivers/`.
- Docker DNS service names for cross-container traffic; no host loopback inside Compose.
- Bind-mount `./init/<role>/` into `/docker-entrypoint-initdb.d/`; bind-mount `./data/sf1/` read-only.
- `start_period` sized to data load (300s for SF1 in postgres/mysql).
- Catalog tests follow `try: … finally: drop_catalog(...)` pattern.

### Integration Points
- sr-main (FE) creates `sr_flightsql_starrocks` catalog → `grpc://sr-external:9408` (Docker DNS) → sr-external StarRocks Arrow Flight server → sr-external `tpch.*` tables
- sr-external bind-mounts `./data/sf1/` (read-only) and `./init/sr-external/` (read-only) from `docker/`
- sr-external healthcheck blocks sr-main startup until ready (`depends_on: condition: service_healthy`)
- `tests/test_queries.py` canonical loader reads `queries/tpch/q*.sql` and substitutes `{catalog}.{db}` per backend (per 04-CANONICAL-SPEC.md)
- `tests/test_flightsql_starrocks.py` uses `flightsql_driver_path` and `sr_conn` fixtures from `conftest.py` (no new fixtures required)
- `run-verify.py` healthcheck loop already accepts services with healthchecks — no CLI change anticipated

### What Changes
| Asset | Change | Reason |
|---|---|---|
| `docker/docker-compose.yml` | Add `sr-external` service (same `build: .`, no host ports, mounts SF1 + init/sr-external, healthcheck, start_period); add `sr-external` to sr-main's `depends_on` | New service |
| `docker/init/sr-external/` (new) | TPC-H DDL + per-table `INSERT … FROM FILES()` SQL files | sr-external init |
| `queries/tpch/` (new) | 22 canonical TPC-H query files with `{catalog}.{db}` substitution, addressing `sr_flightsql_starrocks.tpch.*` (among others) | Canonical query home |
| `tests/test_flightsql_starrocks.py` (new) | 4 lifecycle/data/negative/passthrough tests | New catalog coverage |
| `.planning/REQUIREMENTS.md` | Add new requirements for FlightSQL→StarRocks (FS-SR-01…) | Traceability |

### What Stays the Same
- `docker/Dockerfile` and `docker/entrypoint.sh` — sr-external reuses as-is
- `conftest.py` — no new fixtures needed
- `lib/catalog_helpers.py` — unchanged
- `tests/test_flightsql.py`, `tests/test_queries.py` — unchanged
- `queries/flightsql/`, `docker/init/sqlflite/` — unchanged (sqlflite path coexists)
- `run-verify.py` — no anticipated changes

</code_context>

<specifics>
## Specific Ideas

- The phase title explicitly emphasizes "external StarRocks with **Arrow Flight ports**" — the verification target is StarRocks's Arrow Flight server side, not just adding another generic Arrow Flight backend. The Arrow Flight ports are already configured in `docker/Dockerfile` but currently unexercised; this phase makes them load-bearing.
- User connected the host-port question directly to data loading: *"if we copy the csv inside starrocks and directly create a table from tpch csvs, i dont think it is necessary"*. That choice (in-container CSV access via bind-mount + `FILES()`) eliminates any need to publish sr-external ports to the host.
- Reuse principle: the same StarRocks image is used on both sides of the connection, so the as-shipped artifact is being exercised in both the verifier and verified roles.
- New services follow the existing `sr-<role>` naming convention. Catalog naming (`sr_flightsql_starrocks`) preserves the existing `sr_flightsql` namespace for the sqlflite path.
- Both FlightSQL paths verified independently: sqlflite (generic Arrow Flight + TLS pass-through) and StarRocks (TPC-H depth + native Arrow Flight server).

</specifics>

<deferred>
## Deferred Ideas

- **TLS-enabled sr-external Arrow Flight** — would require StarRocks-side Arrow Flight TLS configuration research; existing TLS sqlflite test still covers the FlightSQL ADBC TLS pass-through code path on the catalog side.
- **Cross-version Arrow Flight** (different `.deb` on sr-external vs sr-main) — adds CLI surface (two `.deb` args); out of v1 scope.
- **Benchmarking Arrow Flight vs MySQL-protocol fetch** — Phase 3-style work; deliberately separate from this phase.
- **Cross-driver JOINs that include `sr_flightsql_starrocks`** (e.g., `sr_flightsql_starrocks.tpch.orders` JOIN `sr_postgres.public.lineitem`) — could be added in a future federation phase.
- **Retiring sqlflite** once external StarRocks proves stable — left for a future cleanup phase; v1 keeps both.
- **Refactoring `tests/test_flightsql.py` into a parametric module** covering both sqlflite and sr-external — refactor for later.
- **Stream Load / Broker Load** as alternative loaders — `FILES()` is sufficient for v1.
- **Generate-inside-container** SF1 path — reuses Phase 2's host-side generator instead.

</deferred>

---

*Phase: 04-flightsql-tpc-h-queries-against-external-starrocks-with-arro*
*Context gathered: 2026-04-28*
