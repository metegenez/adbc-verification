# Quick Task 260501-krv: Ship StarRocks 0.2.0-dev

**Date:** 2026-05-01
**Status:** executing

## Task 1: Package and copy .debs

Package StarRocks FE+BE from ~/coding/starrocks as version 0.2.0-dev, copy to docker/ in this project.

**Action:** Run packaging script, then copy .debs.
**Verify:** starrocks-fe_0.2.0-dev_amd64.deb and starrocks-be_0.2.0-dev_amd64.deb exist in docker/.

## Task 2: Run verification suite

Use run-verify.py to build Docker image, start containers, run test suite.

**Action:** `.venv/bin/python ./run-verify.py docker/starrocks-fe_0.2.0-dev_amd64.deb docker/starrocks-be_0.2.0-dev_amd64.deb`
**Verify:** Tests pass or failures reported.
