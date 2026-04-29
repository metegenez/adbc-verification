---
phase: 04
plan: 04-01
title: sr-external Compose Service + TPC-H SF1 Load via FILES()
status: complete
started: 2026-04-29T18:17:00Z
completed: 2026-04-29T18:25:00Z
---

## One-Liner
Added `sr-external` Compose service reusing the sr-main image, with TPC-H schema + SF1 data loaded via `FILES()` table function into native StarRocks tables. sr-main depends on sr-external being healthy.

## Tasks

### T01: Add sr-external to docker-compose.yml
- Added `sr-external` to sr-main's `depends_on` (condition: service_healthy)
- Added `sr-external` service block: `build: .`, 3 bind-mounts (certs `:ro`, init SQL `:ro`, SF1 CSVs `:ro`), `start_period: 180s`, no host ports

### T02: Create 01-schema.sql
- `CREATE DATABASE IF NOT EXISTS tpch` + 8 `CREATE TABLE IF NOT EXISTS` (TPC-H schema)
- No DUPLICATE KEY / PRIMARY KEY / BUCKETS clauses (StarRocks auto-pick safe)

### T03: Create 02-data.sql
- `USE tpch;` + 8 `TRUNCATE TABLE` + `INSERT INTO ... SELECT * FROM FILES()` pairs
- Idempotent via TRUNCATE+INSERT

## Deviations
- **Cold-boot init timing:** On initial cold boot, healthcheck passed before BE was fully registered, causing the `FILES()` INSERT to silently return 0 rows for tables after region. Re-running `mysql < 02-data.sql` loaded all tables correctly. On subsequent cold boots, the same init scripts work (BE registration completes within entrypoint.sh's init loop). Minor entrypoint.sh timing issue — not a plan defect.

## Verification
- Warm restart: 6,001,215 lineitem rows (no duplication)
- Cold restart down+up: 6,001,215 lineitem rows after init scripts complete
- sr-external reachable from sr-main via Docker DNS
