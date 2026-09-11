"""AF04 independent PG window entry. Preparing this file is NOT execution authority."""

import argparse
import json
from pathlib import Path
import re

from runtime_phase1 import runtime03_pg_window as shared


SPEC = shared.WindowSpec(
    "a2flow-runtime04-pg", "a2flow-runtime04-pgdata",
    Path("/home/admin/OpenSource/.tmp/af-runtime-04-pg"),
    "oss-agent-workflow-runtime-af04", "A2FLOW_RUNTIME04", "test_postgres_lifecycle_integration.py",
)


def verify_source(expected):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise RuntimeError("EXPECTED_FIXED_SOURCE_SHA_REQUIRED")
    head = shared.command(["git", "-C", str(shared.REPO), "rev-parse", "HEAD"]).stdout.strip()
    dirty = shared.command(["git", "-C", str(shared.REPO), "status", "--porcelain"]).stdout
    if head != expected or dirty:
        raise RuntimeError("FIXED_SOURCE_OR_CLEAN_WORKTREE_MISMATCH")
    return head


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--authorized-window", action="store_true",
                       help="requires a separately reviewed main-brain release, not just this flag")
    group.add_argument("--cleanup", action="store_true")
    parser.add_argument("--expected-source-sha")
    args = parser.parse_args(argv)
    try:
        if args.cleanup:
            shared.cleanup(window=SPEC)
        else:
            source = verify_source(args.expected_source_sha)
            print(json.dumps({"sourceSha": source, "window": "AF-RUNTIME-04"}), flush=True)
            shared.run_window(window=SPEC)
            # Detect accidental source changes during the bounded window, after
            # shared finally has already attempted cleanup.
            verify_source(source)
    except Exception as error:
        print(json.dumps({"window": "failed", "errorType": type(error).__name__,
                          "details": "redacted; inspect bounded safe evidence"}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
