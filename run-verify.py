#!/usr/bin/env python3
"""StarRocks ADBC Verification Suite — ship→verify→retest loop.

Copies StarRocks .deb packages, builds Docker Compose containers, waits for
healthchecks, runs the pytest test suite, captures logs on failure, and
reports results.

Usage:
    ./run-verify.py /path/to/starrocks-fe.deb /path/to/starrocks-be.deb
    ./run-verify.py --subset flightsql fe.deb be.deb
    ./run-verify.py --cleanup --report results.json fe.deb be.deb
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

COMPOSE_DIR = pathlib.Path(__file__).resolve().parent / "docker"
REPORTS_DIR = pathlib.Path(__file__).resolve().parent / "reports"
DEFAULT_REPORT = "reports/latest.json"
HEALTHCHECK_TIMEOUT = 300
HEALTHCHECK_POLL_INTERVAL = 3


def main() -> None:
    args = parse_args()

    try:
        result = run_verification(args)
        sys.exit(0 if result else 1)
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Command failed: {e}", file=sys.stderr)
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        if args.cleanup:
            _run_docker_compose(["down"])
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="StarRocks ADBC Verification Suite — ship→verify→retest loop",
    )
    parser.add_argument("fe_deb", help="Path to starrocks-fe .deb package")
    parser.add_argument("be_deb", help="Path to starrocks-be .deb package")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--keep",
        action="store_true",
        default=True,
        help="Leave containers running after tests (default)",
    )
    mode.add_argument(
        "--cleanup",
        action="store_true",
        default=False,
        help="Run docker compose down after tests",
    )

    parser.add_argument(
        "--subset",
        metavar="FILTER",
        help="Pass filter to pytest -k (e.g. 'flightsql')",
    )
    parser.add_argument(
        "--report",
        metavar="FILE",
        default=DEFAULT_REPORT,
        help=f"Write JSON report to FILE (default: {DEFAULT_REPORT})",
    )
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="Skip docker compose build (reuse existing images)",
    )

    return parser.parse_args()


def run_verification(args: argparse.Namespace) -> bool:
    fe_path = pathlib.Path(args.fe_deb)
    be_path = pathlib.Path(args.be_deb)

    # Step 1: Validate inputs
    if not fe_path.is_file():
        print(f"✗ FE .deb not found: {fe_path}", file=sys.stderr)
        return False
    if not be_path.is_file():
        print(f"✗ BE .deb not found: {be_path}", file=sys.stderr)
        return False
    print(f"✓ DEB packages found: {fe_path}, {be_path}")

    # Step 2: Copy .debs to docker/ (skip if source already there)
    os.makedirs(COMPOSE_DIR, exist_ok=True)
    fe_dst = COMPOSE_DIR / "starrocks-fe_latest_amd64.deb"
    be_dst = COMPOSE_DIR / "starrocks-be_latest_amd64.deb"
    if fe_path.resolve() != fe_dst.resolve():
        shutil.copy2(fe_path, fe_dst)
    if be_path.resolve() != be_dst.resolve():
        shutil.copy2(be_path, be_dst)
    print("✓ DEBs in docker/")

    # Step 3: Build and start containers
    print("◆ Building and starting containers...")
    compose_args = ["up", "--detach"]
    if not args.skip_rebuild:
        compose_args.insert(1, "--build")
    _run_docker_compose(compose_args, check=True)

    # Step 4: Wait for healthchecks
    print("◆ Waiting for services to become healthy...")
    healthy = _wait_for_healthy()
    if not healthy:
        print("\n✗ Some services failed healthcheck or timed out", file=sys.stderr)
        _print_service_status()
        if args.cleanup:
            _run_docker_compose(["down"])
        return False

    # Step 5: Run tests
    print("◆ Running test suite...")
    test_passed = _run_tests(args)

    # Step 6: Capture logs on failure
    if not test_passed:
        print("\n── Container Logs (last 100 lines) ──")
        try:
            logs = _run_docker_compose(["logs", "--tail=100"], capture=True)
            if logs:
                print(logs)
        except Exception:
            pass

        print("\n── StarRocks Logs (last 200 lines) ──")
        try:
            sr_logs = _run_docker_compose(
                ["logs", "sr-main", "--tail=200"], capture=True
            )
            if sr_logs:
                print(sr_logs)
        except Exception:
            pass

    # Step 7: Report
    summary = _write_summary(args, test_passed)
    _print_report(args, test_passed, summary)

    # Step 8: Cleanup
    if args.cleanup:
        print("◆ Stopping containers...")
        _run_docker_compose(["down"])
        print("✓ Containers stopped and removed")

    return test_passed


def _run_docker_compose(
    args: list[str], check: bool = False, capture: bool = False
) -> str | None:
    cmd = ["docker", "compose"] + args
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=COMPOSE_DIR)
        return result.stdout
    subprocess.run(cmd, check=check, cwd=COMPOSE_DIR)
    return None


def _wait_for_healthy() -> bool:
    deadline = time.monotonic() + HEALTHCHECK_TIMEOUT
    services = {
        "sr-mysql": False,
        "sr-postgres": False,
        "sr-flightsql": False,
        "sr-flightsql-tls": False,
        "sr-main": False,
    }
    reported: set[str] = set()

    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                capture_output=True,
                text=True,
                cwd=COMPOSE_DIR,
                timeout=10,
            )
        except Exception:
            time.sleep(HEALTHCHECK_POLL_INTERVAL)
            continue

        all_healthy = True
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                svc = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = svc.get("Service", svc.get("Name", ""))
            health = svc.get("Health", "")
            state = svc.get("State", "")
            if name in services:
                ready = health == "healthy" or (health == "" and state == "running")
                if ready:
                    if not services[name]:
                        services[name] = True
                        elapsed = int(HEALTHCHECK_TIMEOUT - (deadline - time.monotonic()))
                        suffix = "healthy" if health == "healthy" else "running (no healthcheck)"
                        print(f"  ✓ {name} {suffix} ({elapsed}s)")
                else:
                    all_healthy = False
                    if name not in reported:
                        status = state or health or "unknown"
                        print(f"  ... {name}: {status}")

        if all_healthy and all(services.values()):
            print("✓ All services healthy")
            return True

        time.sleep(HEALTHCHECK_POLL_INTERVAL)

    return False


def _print_service_status() -> None:
    try:
        result = subprocess.run(
            ["docker", "compose", "ps"],
            capture_output=True,
            text=True,
            cwd=COMPOSE_DIR,
            timeout=10,
        )
        print(result.stdout)
    except Exception:
        pass


def _run_tests(args: argparse.Namespace) -> bool:
    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-v",
        "--json-report",
        f"--json-report-file={args.report}",
    ]
    if args.subset:
        pytest_cmd.extend(["-k", args.subset])

    result = subprocess.run(pytest_cmd)
    return result.returncode == 0


def _write_summary(args: argparse.Namespace, test_passed: bool) -> dict:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    summary_path = REPORTS_DIR / "summary.json"
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fe_deb": str(pathlib.Path(args.fe_deb).resolve()),
        "be_deb": str(pathlib.Path(args.be_deb).resolve()),
        "test_result": "passed" if test_passed else "failed",
        "subset": args.subset,
        "containers": "running" if args.keep else "stopped",
        "services_healthy": True,
        "report_file": args.report,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _print_report(args: argparse.Namespace, test_passed: bool, summary: dict) -> None:
    fe_name = pathlib.Path(args.fe_deb).name
    be_name = pathlib.Path(args.be_deb).name
    print()
    print("═══════════════════════════════════════════")
    print(" Verification Complete")
    print("═══════════════════════════════════════════")
    print(f" DEB: {fe_name}, {be_name}")
    print(f" Result: {'✓ PASSED' if test_passed else '✗ FAILED'}")
    print(f" Report: {summary['report_file']}")
    print(f" Containers: {summary['containers']}")


if __name__ == "__main__":
    main()
