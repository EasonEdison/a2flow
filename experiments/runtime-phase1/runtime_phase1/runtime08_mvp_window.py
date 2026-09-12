"""MVP08 one-shot live-chain window. This source is not execution authority."""

import argparse
import json
import os
from pathlib import Path
import re
import stat

from runtime_phase1 import runtime03_pg_window as shared


EVIDENCE_DIRECTORY = Path(
    "/home/admin/OpenSource/.evidence/oss-agent-workflow-runtime",
)
WINDOW_NAME = "AF-MVP-08-LIVE-W3"
EVIDENCE_FILE = EVIDENCE_DIRECTORY / "af-mvp-08-live-w3.jsonl"
SPEC = shared.WindowSpec(
    container="a2flow-mvp08-pg",
    volume="a2flow-mvp08-pgdata",
    private=Path("/home/admin/OpenSource/.tmp/a2flow-mvp08-live"),
    owner="oss-agent-workflow-runtime-mvp08",
    env_prefix="A2FLOW_MVP08",
    test_pattern="test_mvp08_live_acceptance.py",
    test_directory="experiments/runtime-phase1/tests",
    max_seconds=300,
    max_data_kib=256 * 1024,
    pythonpath=(
        "packages/contracts/src:packages/asset-store/src:services/skill-registry/src:"
        "services/capability-registry/src:services/agent-workflow-runtime/src:"
        "services/agent-workflow-runtime/tests:examples/activity-planning:"
        "experiments/runtime-phase1:experiments/runtime-phase1/tests"
    ),
    evidence_file=EVIDENCE_FILE,
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


def prepare_evidence(source, *, window=SPEC):
    """Create one durable 0600 JSONL target; never overwrite prior evidence."""
    path = window.evidence_file
    if path is None or not path.is_absolute() or path.parent != EVIDENCE_DIRECTORY:
        raise RuntimeError("EVIDENCE_PATH_MISMATCH")
    for directory in (EVIDENCE_DIRECTORY.parent, EVIDENCE_DIRECTORY):
        directory.mkdir(mode=0o700, exist_ok=True)
        metadata = directory.stat()
        if (directory.is_symlink() or directory.resolve() != directory
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700):
            raise RuntimeError("EVIDENCE_DIRECTORY_UNSAFE")
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    os.close(fd)
    shared.append_evidence(
        "ENTRY", window=window, windowName=WINDOW_NAME,
        sourceSha=source, outcome="STARTED",
    )
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
    stage = "ARGUMENTS"
    evidence = None
    try:
        if args.cleanup:
            shared.cleanup(window=SPEC)
        else:
            stage = "SOURCE"
            source = verify_source(args.expected_source_sha)
            stage = "KEY_METADATA"
            key_file = verified_model_key_file()
            stage = "EVIDENCE"
            evidence = prepare_evidence(source)
            print(json.dumps({
                "sourceSha": source,
                "window": WINDOW_NAME,
                "modelKeyFile": "verified-not-read",
                "evidenceFile": str(evidence),
            }), flush=True)
            os.environ[MODEL_KEY_FILE_ENV] = str(key_file)
            stage = "WINDOW"
            shared.run_window(window=SPEC)
            stage = "SOURCE_AFTER_CLEANUP"
            verify_source(source)
            shared.append_evidence(
                "WINDOW_RESULT", window=SPEC, outcome="PASS",
            )
    except Exception as error:
        if evidence is not None:
            try:
                shared.append_evidence(
                    "WINDOW_RESULT", window=SPEC, outcome="FAILED",
                    errorStage=stage, errorType=type(error).__name__,
                )
            except Exception:
                pass
        print(json.dumps({
            "window": "failed",
            "errorType": type(error).__name__,
            "details": "redacted; inspect bounded safe evidence",
        }), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
