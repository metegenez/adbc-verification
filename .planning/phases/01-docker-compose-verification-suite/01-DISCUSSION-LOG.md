# Phase 1: Docker Compose Verification Suite - Discussion Log

**Generated:** 2026-04-27
**Areas discussed:** 4 (all selected)
**Questions asked:** 10

---

## Area 1: Compatibility Mode

| # | Question | Options Presented | Selected | Notes |
|---|---|---|---|---|
| 1 | Should the codebase support both the old bare-metal mode and the new Docker Compose mode, or hard-replace the old code? | Hard replace (recommended) / Dual-mode / Incremental | **Hard replace** | Retire lib/docker_backends.py, simplify lib/starrocks.py, no dual-mode |

**Resolution:** Hard replace. The entire `lib/docker_backends.py` is retired. `lib/starrocks.py` becomes a pure pymysql connect function. `STARROCKS_HOME` env var replaced. No fallback to bare-metal mode.

---

## Area 2: Container Topology & Assets

| # | Question | Options Presented | Selected | Notes |
|---|---|---|---|---|
| 2 | Should StarRocks FE and BE run in a single container or as separate Compose services? | Single container (recommended) / Separate services | **Single container** | FE+BE co-located, one Dockerfile, sequential entrypoint |
| 3 | How should ADBC driver .so files get into the StarRocks container? | Baked into image (recommended) / Volume mounted | **Baked into image** | COPY docker/drivers/ at build time |
| 4 | How should SQLite and DuckDB .db test files get into the StarRocks container? | Baked into image (recommended) / Volume mounted / Generated at startup | **Baked into image** | COPY docker/data/ at build time |

**Resolution:** Single `sr-main` container with FE+BE. Drivers at `/opt/starrocks/drivers/`, data at `/opt/starrocks/data/`. All baked into image — no runtime volume mounts for StarRocks assets.

---

## Area 3: Data Loading Strategy

| # | Question | Options Presented | Selected | Notes |
|---|---|---|---|---|
| 5 | How should TPC-H schema + data be loaded into PostgreSQL, MySQL, and FlightSQL backend containers? | Init scripts at startup (recommended) / Baked into images / Test-time fixtures | **Init scripts at startup** | Volume-mounted SQL into docker-entrypoint-initdb.d/ |
| 6 | What TPC-H scale factor / data volume should be loaded? | SF1 (recommended) / Minimal seed / Both tiers | **TPC-H SF1** | ~1GB total, full 22 TPC-H queries supported |

**Resolution:** Backend data loaded via init scripts at container startup (not baked, not test-time). TPC-H SF1 scale for meaningful queries.

---

## Area 4: CLI Runner & Dev Loop

| # | Question | Options Presented | Selected | Notes |
|---|---|---|---|---|
| 7 | What should the CLI runner be? | Bash script (recommended) / Python CLI | **Python CLI** | argparse-based, richer error handling |
| 8 | After tests complete, should run-verify.py auto-cleanup? | Configurable (recommended) / Always cleanup / Leave running | **Leave running** | No auto-cleanup. User manages down manually. |
| 9 | On test failure, what log capture strategy? | All services / Smart capture / SR only + docker compose logs (recommended) | **SR only + docker compose logs** | Capture sr-main logs, print all service tails |
| 10 | How should SQL query files in queries/ be organized? | Per-driver directories (recommended) / Flat + config / Flat + naming convention | **Per-driver directories** | queries/sqlite/, queries/postgres/, etc. |
| 11 | Fast iteration path: how should subset mode work? | pytest -k with reuse (recommended) / CLI flag / Both | **pytest -k with reuse** | No special CLI flag. Documented docker compose up -d + pytest -k |

**Resolution:** Python CLI (`run-verify.py`), no auto-cleanup, StarRocks-tail + all-service-tail log capture, per-driver query directories, fast path via documented `pytest -k`.

---

## Summary

- 4 areas discussed, 11 questions asked, all resolved
- No scope creep detected — all decisions are about HOW to implement phase scope
- No deferred ideas from discussion (all existing deferred items from PROJECT.md carried forward)
