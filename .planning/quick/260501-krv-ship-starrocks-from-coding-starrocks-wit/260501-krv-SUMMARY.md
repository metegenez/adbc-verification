---
status: complete
---

# Quick Task 260501-krv: Ship StarRocks 0.2.0-dev

**Completed:** 2026-05-01

## Summary

Packaged StarRocks FE+BE from `~/coding/starrocks` as version 0.2.0-dev, copied to `docker/`, and rebuilt Docker images for `sr-main` and `sr-external`.

## Actions

1. **Packaging:** Ran `./packaging/debian/build.sh 0.2.0-dev ../../output/fe ../../output/be` — produced `starrocks-fe_0.2.0-dev_amd64.deb` (608MB) and `starrocks-be_0.2.0-dev_amd64.deb` (3.4GB). First attempt timed out mid-BE build (truncated .deb at 2.6GB); repackaged successfully with 900s timeout.

2. **Copy:** Debs copied to `docker/` in adbc_verification project. Old `starrocks-*_latest_amd64.deb` files removed to avoid Dockerfile glob conflicts.

3. **Rebuild:** `docker compose build sr-main sr-external` — both images built successfully (11.3GB each, tag `docker-sr-main:latest` / `docker-sr-external:latest`).

## Notes

- FE was already built; only packaging was needed
- BE .deb grew from 2.6GB (0.1.0-dev) to 3.4GB (0.2.0-dev, includes connection pooling changes)
- Verification tests were NOT run — images rebuilt only per user request
