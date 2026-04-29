---
phase: 04
plan: 04-04
title: Cleanup — Delete Retired lib/ Dead-Code Files
status: complete
files_created: []
files_deleted:
  - lib/docker_backends.py (164 lines — DEPRECATED, replaced by docker-compose.yml)
  - lib/starrocks.py (26 lines — Docker Compose mode helper, replaced by Docker Compose)
  - lib/tls.py (65 lines — DEPRECATED, pre-generated certs in docker/certs/)
  - lib/driver_registry.py (67 lines — build-time only, runtime uses fixed paths)
  - lib/__pycache__/ (stale .pyc files for deleted modules)
files_kept:
  - lib/__init__.py (package marker, unchanged)
  - lib/catalog_helpers.py (3,158 bytes, live module, unchanged)
started: 2026-04-29T17:42:00Z
completed: 2026-04-29T17:45:00Z
---

## One-Liner
Deleted four retired `lib/` dead-code modules (`docker_backends.py`, `starrocks.py`, `tls.py`, `driver_registry.py`) and cleared stale bytecode — 322 lines removed, zero external references, 93-test suite passes identically.

## Tasks

### T01: Pre-flight — verify zero external references and capture baseline
- All four files confirmed dead — deprecation markers present in headers
- Repo-wide grep: exactly ONE import reference — `lib/tls.py:14` → `lib/docker_backends._wait_for_port` (both in deletion set)
- Baseline recorded: 93 tests collected

### T02: Delete the four modules + clear bytecode
- `git rm` staged all four `.py` deletions
- `rm -rf lib/__pycache__` cleared stale `.pyc` files
- `lib/` retains exactly `__init__.py` and `catalog_helpers.py`

### T03: Post-flight regression
- Static collection: 93 tests (matches T01 baseline)
- Full integration run: 72 passed, 20 skipped, 1 xpassed — zero `ImportError` or `ModuleNotFoundError`

## Deviations
None.

## Forward Link
04-03 can now safely delete the CLAUDE.md "Retired" table — the four files it listed no longer exist on disk.
