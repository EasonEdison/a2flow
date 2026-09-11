"""MVP08 one-shot live-chain window. This source is not execution authority."""

import argparse
import json
import os
from pathlib import Path
import re
import stat

from runtime_phase1 import runtime03_pg_window as shared


SPEC = shared.WindowSpec(
    "a2flow-mvp08-pg",
    "a2flow-mvp08-pgdata",
    Path("/home/admin/OpenSource/.tmp/a2flow-mvp08-live"),
    "oss-agent-workflow-runtime-mvp08",
    "A2FLOW_MVP08",
    "test_mvp08_live_acceptance.py",
    "experiments/runtime-phase1/tests",
    300,
    256 * 1024,
    "packages/contracts/src:packages/asset-store/src:services/skill-registry/src:"
    "services/capability-registry/src:services/agent-workflow-runtime/src:"
    "services/agent-workflow-runtime/tests:examples/activity-planning:"
    "experiments/runtime-phase1:experiments/runtime-phase1/tests",
)
MODEL_KEY_FILE_ENV = "A2FLOW_MVP08_MODEL_KEY_FILE"


def verify_source(expected):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise RuntimeError("EXPECTED_FIXED_SOURCE_SHA_REQUIRED")
    head = shared.command(
        ["git", "-C", str(shared.REPO), "rev-parse", "HEAD"],
    ).stdout.strip()
    dirty = shared.command(
        ["git", "-C", str(shared.REPO), "status", "--porcelain"],
    ).stdout
    if head != expected or dirty:
        raise RuntimeError("FIXED_SOURCE_OR_CLEAN_WORKTREE_MISMATCH")
    return head


def verified_model_key_file():
    if os.environ.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("DIRECT_MODEL_SECRET_ENV_FORBIDDEN")
    raw = os.environ.get(MODEL_KEY_FILE_ENV)
    if not raw:
        raise RuntimeError("MODEL_KEY_FILE_REQUIRED")
    path = Path(raw)
    try:
        resolved = path.resolve(strict=True)
        metadata = path.stat()
    except OSError:
        raise RuntimeError("MODEL_KEY_FILE_UNAVAILABLE") from None
    if (not path.is_absolute() or path.is_symlink() or resolved != path
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= 512):
        raise RuntimeError("MODEL_KEY_FILE_UNSAFE")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--authorized-window",
        action="store_true",
        help="requires a separately reviewed main-brain release; this flag is not authorization",
    )
    group.add_argument("--cleanup", action="store_true")
    parser.add_argument("--expected-source-sha")
    args = parser.parse_args(argv)
    try:
        if args.cleanup:
            shared.cleanup(window=SPEC)
        else:
            source = verify_source(args.expected_source_sha)
            key_file = verified_model_key_file()
            print(json.dumps({
                "sourceSha": source,
                "window": "AF-MVP-08-LIVE-W1",
                "modelKeyFile": "verified-not-read",
            }), flush=True)
            os.environ[MODEL_KEY_FILE_ENV] = str(key_file)
            shared.run_window(window=SPEC)
            verify_source(source)
    except Exception as error:
        print(json.dumps({
            "window": "failed",
            "errorType": type(error).__name__,
            "details": "redacted; inspect bounded safe evidence",
        }), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
