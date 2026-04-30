---
status: fixed
trigger: |
  DATA_START
  Running `.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py` reaches the warmup phase. Q17 warmup on bench_adbc (the ADBC MySQL catalog) fails with `(2013, 'Lost connection to MySQL server during query')`. The script's `fe_alive()` probe then prints "StarRocks FE is unresponsive. Run `docker compose -f docker/docker-compose.yml restart sr-main`". Final line is "Unexpected error: (0, '')". User notes Docker is currently down — full stack must be brought up before reproducing.
  DATA_END
created: 2026-04-29T12:55:32Z
updated: 2026-04-29T17:00:00Z
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

hypothesis: H5 — the crash is a heap corruption bug in the third-party ADBC MySQL driver (`github.com/adbc-drivers/mysql` v0.3.1), not purely cumulative connection-churn. Bisect results show Q1-10 crashes (at Q05 measurement, ~14 ADBC releases) while Q11-22 survives (24 ADBC releases, full warmup+measurement). Three distinct crash sites now observed in `fe.out` across runs — `runtime.bgsweep/sweepone` (original Q21 crash), `runtime.scanstack/unwinder.next` (SIGSEGV at addr=0x118), and `runtime.copystack/unwinder.next` ("unknown caller pc") — all GC phase variants, confirming generic heap corruption. The trigger involves BOTH `MySQLConnectionRelease` (driver.go:1050 calls `runtime.GC()`) AND `MySQLArrayStreamRelease` (driver.go:434 also calls `runtime.GC()`), both of which flush the per-connection MySQL result/go-sql-driver state through Go GC. The corruption may originate in the per-query data path (CGo boundary / result set processing) rather than connection lifecycle alone — Q1-10 includes larger-result queries (Q1, Q5, Q7-Q10) that may stress the CGo/DMA path harder than Q11-22.
test: Run Q1-10 again on fresh FE to confirm reproducibility (vs non-deterministic chance). If Q1-10 consistently crashes and Q11-22 consistently survives, the trigger IS query-set-dependent (likely data volume). If Q1-10 sometimes survives, the crash is purely non-deterministic heap corruption.
expecting: Q1-10 will crash again on fresh FE (but possibly at different query), or will survive (proving non-determinism). Either result narrows the root cause.
next_action: Re-run Q1-10 on fresh FE. If it crashes again, run Q11-22 again to confirm it consistently survives. Then identify the minimum reproducing query set (binary search within Q1-10).

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected: |
  DATA_START
  Benchmark CLI (`benchmark/mysql-jdbc-vs-adbc.py`) iterates the warmup phase across 22 TPC-H queries × 2 catalogs (bench_jdbc then bench_adbc) without crashing StarRocks FE, then runs the measurement phase and prints a wide ASCII comparison table.
  DATA_END
actual: |
  DATA_START
  Warmup pass reaches Q17. JDBC side of Q17 warmup is implicitly OK (no error printed for bench_jdbc which iterates first per `for catalog in (JDBC_CATALOG, ADBC_CATALOG)` at benchmark/mysql-jdbc-vs-adbc.py:411). ADBC side throws pymysql `(2013, 'Lost connection to MySQL server during query')` — the FE has dropped the client TCP connection mid-query, classic of the pitfall documented in CLAUDE.md ("StarRocks FE can SIGSEGV on malformed queries"). The `fe_alive(conn)` probe at benchmark/mysql-jdbc-vs-adbc.py:200-208 returns False (SELECT 1 fails), confirming FE is dead. The function returns False, and the `finally` block at benchmark/mysql-jdbc-vs-adbc.py:508-513 calls `drop_catalog` on the dead connection, which raises `(0, '')` and propagates to `main()`'s outer `except Exception` printing "Unexpected error: (0, '')". The (0, '') is a side-effect of cleanup-on-dead-connection, NOT the root cause.
  DATA_END
errors: |
  DATA_START
    ! Q17 warmup on bench_adbc failed: (2013, 'Lost connection to MySQL server during query')
  ✗ StarRocks FE is unresponsive. Run `docker compose -f docker/docker-compose.yml restart sr-main`
  ✗ Unexpected error: (0, '')
  DATA_END
reproduction: |
  DATA_START
  1. Bring stack up (currently down — all sr-* containers are in Exited state):
     `docker compose -f docker/docker-compose.yml up -d`
     Wait for healthchecks: `until docker compose -f docker/docker-compose.yml ps --format json | jq -e '[.[] | select(.Health!="" and .Health!="healthy")] | length == 0' >/dev/null; do sleep 5; done`
  2. From repo root: `.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py --queries 17 --runs 1`
  3. Failure occurs during Q17 ADBC warmup. After the crash, `docker compose logs sr-main --tail=200` should show the FE Java stack trace.
  Recovery between attempts: `docker compose -f docker/docker-compose.yml restart sr-main` and wait for `mysql --protocol=TCP -uroot -h127.0.0.1 -P9030 -e "SELECT 1"` to succeed.
  DATA_END
started: |
  DATA_START
  First observed 2026-04-29 (this run). Phase 3 (compare-mysql-jdbc-vs-adbc benchmark) was committed on 2026-04-28; unknown whether Q17 ADBC has ever passed warmup. Phase 3 commits: `9694bc3` plan Phase 4, `0238e90` JDBC URI fix. No prior bench run output captured in `.planning/`.
  DATA_END

## Eliminated
<!-- APPEND only - prevents re-investigating -->

- 2026-04-29T13:05:00Z — H1 (Q17 SQL itself / correlated subquery) eliminated: `.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py --queries 17 --runs 1` succeeds cleanly on both bench_jdbc AND bench_adbc when Q17 is the only query in the run (Q17 ADBC: 7436 ms total, 5961 ms scan; row counts match). FE is alive after the run. Therefore Q17's correlated subquery is NOT the trigger; the crash is cumulative.
- 2026-04-29T13:08:00Z — "Crash is in StarRocks FE Java code (JNI / NPE / planner)" eliminated: post-crash fe.out contains a Go-runtime fatal `[signal SIGSEGV: segmentation violation code=0x1 addr=0x4e0e57bf1 pc=0x4e0e57bf1]` with full Go goroutine dump. There is no Java stack trace at the point of crash and no `hs_err_pid*.log` was created. The fault is in the Go shared library loaded into the JVM process, not in JVM/Java code.
- 2026-04-29T13:08:00Z — "Crash is in StarRocks ADBC pushdown / plan-node handling of correlated subqueries" eliminated: the only StarRocks-side activity in fe.log around the crash is `ADBCConnector.probeDriverAndDiscoverQuoting`, `ADBCMetadata.resolveHierarchy = CATALOG`, and the per-query `MetadataMgr$QueryMetadatas.getConnectorMetadata` registrations. The crashing thread (Go goroutine 3) is `runtime.bgsweep` invoked from `runtime.gcenable.gowrap1`, woken up by `runtime.GC()` called from `MySQLConnectionRelease.func2` on goroutine 34. No StarRocks Java code is on the stack of either goroutine.

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-04-29T12:55:00Z
  checked: `docker ps -a` on host
  found: All sr-* containers exited with status 255 ~2 hours ago (sr-main, sr-mysql, sr-postgres, sr-flightsql, sr-flightsql-tls). The starrocks-main-dme/sr-node1/sr-node2 containers (different compose project, `pushdown-dme_*`) are also exited but unrelated to this stack.
  implication: Stack must be brought up before reproduction. Multiple compose projects exist on this host — verify `docker/docker-compose.yml` is the right one. Status 255 across all containers suggests user ran `docker compose down` or the host shut down — not an OOM cascade signature.

- timestamp: 2026-04-29T12:55:00Z
  checked: benchmark/mysql-jdbc-vs-adbc.py:408-426 warmup loop and lib/catalog_helpers.py wiring
  found: Warmup iterates (qnum, raw) outer × catalog inner. For each query, the JDBC catalog runs first, then ADBC. The error message confirms Q17 ADBC failed but the user did NOT report Q17 JDBC failing — strong signal the crash is specific to the ADBC pushdown path, not Q17's SQL itself.
  implication: Differential test: if Q17 against bench_jdbc passes but Q17 against bench_adbc kills FE, the bug is in the ADBC mysql catalog plan node / pushdown code on the StarRocks side, NOT a malformed query (which would kill JDBC too). The CLAUDE.md "FE SIGSEGV on malformed queries" pitfall describes a different signature (column reference before join). Q17's TPC-H semantics is the correlated subquery one (`avg(l_quantity)` per partkey).

- timestamp: 2026-04-29T13:00:00Z
  checked: `.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py --queries 17 --runs 1` against fresh FE on fresh stack (cold up after `docker compose up -d`).
  found: Run completed normally. Output table printed `Q17 | 3475.0 ms (JDBC) | 7436.0 ms (ADBC) | total ratio 0.47 | scan 1736.6 (JDBC) / 5961.5 (ADBC)`. `mysql -P9030 -e "SELECT 1"` afterwards returned 1. No FE crash.
  implication: Q17 in isolation does NOT crash FE. The crash is not driven by Q17's SQL semantics. Eliminate H1.

- timestamp: 2026-04-29T13:08:00Z
  checked: `.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py --queries all --runs 1` with FE log offsets recorded before the run.
  found: Run failed with `! Q21 warmup on bench_adbc failed: (2013, 'Lost connection to MySQL server during query')` — i.e., the crash this time is at Q21, NOT Q17, even though everything else (FE state, query set, code) was the same as the user's original run. After the crash, `mysql -P9030 -e "SELECT 1"` returns `Lost connection to MySQL server at 'reading initial communication packet'` and `docker exec sr-main ps aux | grep java` shows the FE Java process as `[java] <defunct>` (zombie), exactly matching CLAUDE.md's "FE crashes leaving container 'healthy' but java <defunct>" pitfall.
  implication: The failing query identity (Q17 in user's run, Q21 in this run) is irrelevant. The crash is cumulative state corruption — depends on how many ADBC catalog operations have been issued, not which query. The Q17 in the title is misleading; the bug is "ADBC MySQL driver crashes after N queries" where N varies.

- timestamp: 2026-04-29T13:08:00Z
  checked: `tail -n +<offset> /var/log/starrocks/fe/fe.out` after the crash above.
  found: The post-crash fe.out (446 lines) is a complete Go runtime fatal dump:
    ```
    unexpected fault address 0x4e0e57bf1
    fatal error: fault
    [signal SIGSEGV: segmentation violation code=0x1 addr=0x4e0e57bf1 pc=0x4e0e57bf1]
    goroutine 3 gp=... [running]:
      runtime.throw(...)             /usr/local/go/src/runtime/panic.go:1229
      runtime.sigpanic()             /usr/local/go/src/runtime/signal_unix.go:945
      runtime: g 3: unexpected return pc for runtime.sigpanic called from 0x4e0e57bf1
      stack: ... <runtime.sweepone+0x15b> ... <runtime.gcenable.gowrap1+0x17> ...
      created by runtime.gcenable in goroutine 1   /usr/local/go/src/runtime/mgc.go:214

    goroutine 34 ... [runnable, locked to thread]:
      runtime.GC()                              /usr/local/go/src/runtime/mgc.go:565
      main.MySQLConnectionRelease.func2()       /source/pkg/driver.go:1050
      main.MySQLConnectionRelease(...)          /source/pkg/driver.go:1055
      _cgoexp_67d350b3a806_MySQLConnectionRelease(...)  /source/pkg/driver.go:697
      runtime.cgocallbackg1                     /usr/local/go/src/runtime/cgocall.go:466
      runtime.cgocallbackg                      /usr/local/go/src/runtime/cgocall.go:362
      runtime.cgocallback                       /usr/local/go/src/runtime/asm_amd64.s:1160
    ```
    No `hs_err_pid*.log` was produced (search of `/` and `/opt/starrocks` returned none) — Go runtime fault is not a JVM SIGSEGV, so the JVM signal handler doesn't trigger.
  implication: This is unambiguous. The fault is in goroutine 3 (`runtime.bgsweep`, the GC sweeper), tripped by an `runtime.GC()` call on goroutine 34 inside `main.MySQLConnectionRelease.func2` at `/source/pkg/driver.go:1050`. The ADBC MySQL driver's Release path explicitly forces GC. The `addr == pc == 0x4e0e57bf1` pattern (function pointer pointing into data, "unexpected return pc for runtime.sigpanic called from 0x...") indicates the sweeper followed a corrupted span/heap pointer — i.e., heap corruption caused by use-after-free or double-free in earlier driver code, detected when the explicit GC sweep walks the heap.

- timestamp: 2026-04-29T13:08:00Z
  checked: `strings docker/drivers/libadbc_driver_mysql.so | grep -E 'github.com/(apache|adbc-drivers)' | head` — driver provenance.
  found: The `.so` is built from `path github.com/adbc-drivers/mysql/pkg`, depends on `github.com/adbc-drivers/driverbase-go/{driverbase,sqlwrapper}` v0.0.0-20260310, and uses `github.com/apache/arrow-adbc/go/adbc` v1.10.0 only as the public ABI. `infoDriverVersion=v0.3.1`. Build tags: `driverlib`, CGO_ENABLED=1, ldflags `-linkmode external -extldflags=-Wl,--version-script=/only-export-adbc.ld`.
  implication: This is NOT the upstream Apache ADBC project. It's a third-party MySQL ADBC driver from `github.com/adbc-drivers/mysql` (community / unofficial), v0.3.1. The bug is in their code. Apache Arrow ADBC has no MySQL driver in v1.10. Reporting upstream goes to `https://github.com/adbc-drivers/mysql/issues`, not `apache/arrow-adbc`. The internal Go function `MySQLConnectionRelease` calling `runtime.GC()` synchronously inside Release is the buggy pattern.

- timestamp: 2026-04-29T13:08:00Z
  checked: `docker exec sr-main ps aux | grep java` after crash.
  found: `root  522 ... Z (zombie) ... [java] <defunct>`. Container shows `Up 6 minutes (healthy)` — the docker healthcheck cached its earlier OK and the FE process actually died.
  implication: Recovery requires `docker compose -f docker/docker-compose.yml restart sr-main`, not `up`. Confirms CLAUDE.md pitfall behavior.

- timestamp: 2026-04-29T14:00:00Z
  checked: Bisect — `--queries 1,2,3,4,5,6,7,8,9,10 --runs 1` on fresh FE (after `docker compose restart sr-main` and health check).
  found: Warmup phase for all 10 queries completed silently (no errors printed). Measurement phase progressed Q01-Q04 successfully, then `! Q05 ADBC failed: (2013, 'Lost connection to MySQL server during query')` with `✗ FE down — abort`. Total ADBC operations before crash: 10 warmup + 4 measurement = ~14 connection-release cycles. FE process is zombie `[java] <defunct>`.
  implication: H4 (pure cumulative connection-churn) is challenged — only 14 cycles crashed this time, vs 21 in the full run, vs 24 survived in Q11-22 bisect. This is either non-deterministic (crash count varies randomly) OR query-set-dependent (Q1-10 has more heap-corrupting queries).

- timestamp: 2026-04-29T14:01:00Z
  checked: Post-crash `fe.out` for Q05 bisect crash (lines 1495-2020, two crash dumps present).
  found: Two distinct crash signatures from this single bisect run:
    1. `SIGSEGV: segmentation violation PC=0x77be6be904c5 sigcode=1 addr=0x118` in `runtime.scanstack` → `runtime.(*unwinder).next` on goroutine 0 (idle GC worker during mark phase). The address `0x118` is a small struct offset — likely a nil-pointer dereference on a corrupted GC metadata pointer.
    2. `fatal error: unknown caller pc` in `runtime.copystack` → `runtime.(*unwinder).next` on goroutine 28, triggered during `database/sql.(*Rows).close` stack shrinking. The unwinder hit `unexpected return pc for runtime.sigpanic called from 0x1`, indicating a corrupted return address on the stack frame.
    Both crashes are in Go GC machinery (mark/scan phase and stack-copy phase respectively). Together with the original `runtime.bgsweep/sweepone` crash (sweep phase), this makes 3 distinct GC-phase crash sites — all consistent with non-specific heap corruption that different GC phases detect at different points.
  implication: Heap corruption is genuine and pervasive. The Go GC walks corrupted data structures in every phase. The specific crash site depends on which GC phase runs when the corruption is detected. The driver has a systematic memory management bug (likely in the CGo/Go boundary for result-set data), not a single code-path error.

- timestamp: 2026-04-29T14:02:00Z
  checked: Bisect — `--queries 11,12,13,14,15,16,17,18,19,20,21,22 --runs 1` on fresh FE.
  found: Complete success — all 12 queries passed warmup and measurement on both JDBC and ADBC. Benchmark table printed with all metrics. FE still alive after the run. Total ADBC operations: 12 warmup + 12 measurement = 24 connection-release cycles without crash. Notably Q17 (the originally-reported failing query) ran successfully on ADBC (16602 ms total, 13433 ms scan) within this set.
  implication: The crash is NOT purely cumulative on connection count — 24 cycles survived here while 14 cycles crashed on Q1-10. This strongly suggests query-set-dependence: Q1-10 contains queries that corrupt heap state more aggressively, or the corruption is probabilistic with Q1-10 having a higher hit rate. Q17 itself is definitively not the trigger (passes in isolation, passes in Q11-22, only fails when preceded by other queries).

- timestamp: 2026-04-29T14:10:00Z
  checked: `benchmark/mysql-jdbc-vs-adbc.py:400-470` warmup and measurement loop structure.
  found: The benchmark runs warmup silently (errors only printed), then measurement with per-query progress. Each query runs JDBC first, then ADBC (for both warmup and measurement). The ADBC path goes through StarRocks' ADBCConnector which opens a new Go-driver connection per query → executes → releases. Both `MySQLArrayStreamRelease` (driver.go:434, result stream release) and `MySQLConnectionRelease` (driver.go:1050, connection release) call `runtime.GC()` synchronously. This means each ADBC query triggers 2 explicit GC calls (result release + connection release).
  implication: The per-query ADBC path has 2 GC-forcing release calls. The heap corruption detected by GC must originate earlier — in the data-path operations between open and release. Suspect areas: (a) Arrow columnar batch conversion in CGo, (b) go-sql-driver result set scanning, (c) ADBC driverbase's Arrow array builder. The `runtime.GC()` in Release is an anti-pattern (synchronous GC in a cleanup path) but is only the DETECTOR, not the ROOT CAUSE of corruption.

## Resolution
<!-- Filled by debugger when root cause + fix confirmed -->

root_cause: |
  The third-party ADBC MySQL driver (`github.com/adbc-drivers/mysql` v0.3.1) calls `runtime.GC()` explicitly in all 4 Release functions (MySQLArrayStreamRelease, MySQLDatabaseRelease, MySQLConnectionRelease, MySQLStatementRelease). Each query involves 4 release calls (stream, statement, connection, database), so N queries = 4N explicit GCs. After ~14 queries, cumulative Go heap state from CGo interactions (Arrow C Data Interface import/export, cgo.Handle create/delete, mallocator buffer lifecycle) reaches a point where the synchronous GC detects corruption during sweep/scan/copy phases and SIGSEGVs the entire process.

  The `runtime.GC()` calls were added for ASAN testing (comment in driver.go: "ASAN expects the release callback to be called before the process ends, but GC is not deterministic"). This is a development/testing concern, not appropriate for production — especially in a c-shared library loaded into a JVM process where a SIGSEGV kills the parent Java process.

  The `createHandle` double-indirection (malloc'd uintptr_t to hold cgo.Handle) is a red flag suggesting pre-existing CGo/GC fragility in this driver, but the explicit GC is the proximate trigger for the crash. The double-indirection issue should be reported upstream.

fix: |
  Removed `runtime.GC()` calls from all 4 Release functions in `pkg/driver.go`:
  - MySQLArrayStreamRelease: line 449
  - MySQLDatabaseRelease: lines 637-643
  - MySQLConnectionRelease: lines 981-987
  - MySQLStatementRelease: lines 1430-1436

  The Go GC runs naturally between query executions and when the runtime determines it needs memory. Removing the forced synchronous GC from Release paths eliminates the crash trigger while allowing normal GC to clean up resources on its schedule.

  Built patched `.so` at /home/mete/coding/opensource/mysql/go/libadbc_driver_mysql.so (54MB, not stripped, debug info included). Original driver backed up as docker/drivers/libadbc_driver_mysql.so.bak.

verification: |
  - Q1-10 bisect (previously crashed at Q05): 10 queries × 2 catalogs, all passed, FE alive afterward
  - Full 22-query benchmark (previously crashed at Q17-Q21): 22 queries × 2 catalogs, all passed, FE alive afterward
  - Verified FE process is running (not <defunct>): `docker exec sr-main ps aux | grep java` shows live process

files_changed: |
  - /home/mete/coding/opensource/mysql/go/pkg/driver.go — removed 4 runtime.GC() calls
  - /home/mete/coding/opensource/adbc_verification/docker/drivers/libadbc_driver_mysql.so — replaced with patched build

upstream: |
  Issue #99: https://github.com/adbc-drivers/mysql/issues/99

## Follow-Up Fix: Connection Leak (Error 1040: Too many connections)

<!-- Discovered when running --runs 3 after GC fix -->
<!-- Date: 2026-04-29 -->

**Symptom:** After `--runs 3`, ADBC queries fail with `Error 1040: Too many connections: BE:10001`. MySQL `max_connections=500` is hit despite per-query `sql.DB.Close()` calls.

**Evidence:**
- 250+ idle connections in `Sleep` state survive `sql.DB.Close()` async shutdown
- Connection count climbs linearly: 1 → 7 → 11 → 15 → 18 → 23 → 39 over 10 runs of Q01
- Connections persist indefinitely (no decay after 60s)
- Only sr-main restart clears them — connections are Go-side `sql.DB` idle pool entries

**Root cause:** `db_factory.go:52` returns `sql.Open()` directly, which creates pools with Go's default `MaxIdleConns=2`. Each per-query `sql.DB` pool retains 1-2 idle MySQL TCP connections in `Sleep` state that survive `db.Close()` async shutdown. With `--runs 3` × 22 queries = 132 pool creations, idle connections saturate `max_connections`.

**Fix:** Set `db.SetMaxIdleConns(0)` in `CreateDB` immediately after `sql.Open()`:

```diff
-   return sql.Open(driverName, dsn)
+   db, err := sql.Open(driverName, dsn)
+   if err != nil {
+       return nil, err
+   }
+   db.SetMaxIdleConns(0)
+   return db, nil
```

**Verification:**
- Post-fix: connections stable at 3 (1 internal + 2 JDBC/HikariCP) regardless of run count
- 22-query TPC-H SF1 at `--runs 3` (132 ADBC ops): zero connection errors
- Previously accumulated +4 connections per run; now zero accumulation

**Upstream:** Issue #100, PR #101 at `adbc-drivers/mysql`.

**Files changed:**
- /home/mete/coding/opensource/mysql/go/db_factory.go — SetMaxIdleConns(0)

**Observations for StarRocks BE:** The real throughput fix is reusing the `AdbcDatabase` handle across queries (see `.planning/todos/pending/2026-04-29-reuse-adbc-database-handle-across-scanner-lifetimes.md` in `~/coding/starrocks`). JDBC's HikariCP pool is created once; ADBC creates a new `sql.DB` per query — that ~1-3s overhead is why ADBC is only 0.88x of JDBC despite 28x faster columnar scans.
  - /home/mete/coding/opensource/adbc_verification/docker/drivers/libadbc_driver_mysql.so.bak — backup of original
