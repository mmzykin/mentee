#!/usr/bin/env python3
"""
Test runner script for local development.
Run: python scripts/run_tests.py [options]

Options:
    --quick     Run only fast tests (skip slow ones)
    --db        Run only database tests
    --bot       Run only bot tests
    --cov       Generate coverage report
    --html      Generate HTML coverage report
    --watch     Watch mode - rerun tests on file changes
"""
import os
import sys
import subprocess
from pathlib import Path

# Navigate to project root
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)

# Set test environment
os.environ["BOT_TOKEN"] = "TEST_TOKEN_12345"


def run_tests(args: list[str]):
    """Run pytest with given arguments."""
    cmd = [sys.executable, "-m", "pytest"] + args
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd).returncode


def main():
    args = sys.argv[1:]
    pytest_args = ["-v", "--tb=short"]

    # Parse custom flags
    if "--quick" in args:
        args.remove("--quick")
        pytest_args.extend(["-m", "not slow"])

    if "--db" in args:
        args.remove("--db")
        pytest_args.append("tests/test_database.py")
    elif "--bot" in args:
        args.remove("--bot")
        pytest_args.append("tests/test_bot.py")
    else:
        pytest_args.append("tests/")

    if "--cov" in args:
        args.remove("--cov")
        pytest_args.extend(["--cov=.", "--cov-report=term-missing"])

    if "--html" in args:
        args.remove("--html")
        pytest_args.extend(["--cov=.", "--cov-report=html:coverage_html"])

    if "--watch" in args:
        args.remove("--watch")
        try:
            import pytest_watch
        except ImportError:
            print("Installing pytest-watch...")
            subprocess.run([sys.executable, "-m", "pip", "install", "pytest-watch", "--quiet"])

        cmd = [sys.executable, "-m", "pytest_watch", "--"] + pytest_args + args
        return subprocess.run(cmd).returncode

    # Add any remaining args
    pytest_args.extend(args)

    return run_tests(pytest_args)


if __name__ == "__main__":
    sys.exit(main())
