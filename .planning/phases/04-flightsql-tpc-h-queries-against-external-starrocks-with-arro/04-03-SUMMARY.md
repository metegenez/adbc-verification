---
phase: 04
plan: 04-03
title: Phase 4 Integration — run-verify wiring + REQUIREMENTS + ROADMAP + CLAUDE.md
status: complete
started: 2026-04-29T18:25:00Z
completed: 2026-04-29T18:28:00Z
---

## One-Liner
Registered 9 FS-SR-* requirements in .planning/REQUIREMENTS.md, filled Phase 4 ROADMAP entry, wired sr-external into run-verify.py healthcheck, and updated CLAUDE.md with Phase 4 layout + pitfalls + Phase 2 SF1 rewrite.

## Tasks

### T01: Add FS-SR-01..FS-SR-09 to REQUIREMENTS.md
- Inserted `### FlightSQL → External StarRocks (Phase 4)` section after VAL-07
- Added 9 requirement rows (FS-SR-01..09) with descriptions and checkbox status
- Extended traceability table with 9 rows mapping FS-SR-* to 04-01/02/04/05
- Updated coverage tally: 17 → 26 total

### T02: Fill ROADMAP.md Phase 4
- Replaced `[To be planned]` / `TBD` with full Goal, Requirements, Depends on, 9 Success Criteria
- Added 5 concrete plans with FS-SR-* ownership
- Added Progress table row for Phase 4
- Updated execution order note with correct wave topology

### T03: Add sr-external to run-verify.py services dict
- One-line insertion: `"sr-external": False` between sr-flightsql-tls and sr-main

### T04: Update CLAUDE.md
- Updated queries/ listing to show `queries/tpch/` canonical home
- Added `test_flightsql_starrocks.py` to tests/ listing
- Dropped `driver_registry.py` from lib/ listing
- Rewrote Phase 2 SF1 section for DuckDB tpch generator + canonical query consolidation
- Added `## Phase 4: External StarRocks Arrow Flight` subsection
- Added 2 new pitfalls (DUPLICATE KEY ordering + run-verify.py service dict)
- Deleted `## Retired` table (files now actually deleted by 04-04)
