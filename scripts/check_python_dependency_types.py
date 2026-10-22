"""Check the expanded Python HTTP/composition scope against real SDK types.

Run inside the core-probe image, which includes the pinned quality tools and
real dependencies. This gate does not import an application or contact a host.
Legacy imported function bodies remain outside this migration scope; dependency
argument/return compatibility is checked and missing imports are never ignored.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BSIDE = "services/b-side-api/src/a2flow_bside/"
RUNTIME = "services/agent-workflow-runtime/src/agent_workflow_runtime/"
HTTP = [
    BSIDE + name + ".py"
    for name in (
        "app",
        "account_routes",
        "activity_routes",
        "conversation_routes",
        "notification_routes",
        "run_routes",
        "schedule_routes",
        "chat_application",
        "workflow_application",
        "route_dependencies",
        "route_identity",
        "route_models",
        "route_support",
        "chat_history",
    )
]
PERSISTENCE = [
    BSIDE + name + ".py"
    for name in (
        "persistence_types",
        "chat_runner",
        "chat_wake",
        "chat_delivery",
        "processing_tasks",
        "repositories",
        "durable_chat",
        "turn_registry",
        "assembly",
    )
]
CONTRACTS = ["packages/contracts/src/skillweave_contracts/" + name + ".py"
             for name in ("chat_state", "chat_result")]
TRANSPORT = [RUNTIME + name + ".py" for name in ("http", "progress_http", "service")]
COMPOSITION = [
    "deploy/attended/bside_app.py",
    "deploy/attended/chat_runner.py",
    "deploy/realchat/launcher.py",
    RUNTIME + "model_factory.py",
]


def main() -> int:
    env = os.environ.copy()
    paths = [
        ROOT,
        ROOT / "examples/activity-planning",
        *sorted((ROOT / "packages").glob("*/src")),
        *sorted((ROOT / "services").glob("*/src")),
    ]
    env["MYPYPATH"] = os.pathsep.join(map(str, paths))
    with tempfile.TemporaryDirectory(prefix="a2flow-dependency-types-") as cache:
        for name, files, legacy_calls in (
            ("shared Chat contracts", CONTRACTS, False),
            ("HTTP routes", HTTP, False),
            ("persistence boundaries", PERSISTENCE, True),
            ("Runtime transport", TRANSPORT, False),
            ("production composition", COMPOSITION, True),
        ):
            command = [
                sys.executable,
                "-m",
                "mypy",
                "--follow-imports=silent",
                "--cache-dir",
                cache,
                *(["--allow-untyped-calls"] if legacy_calls else []),
                *files,
            ]
            print("Checking " + name, flush=True)
            subprocess.run(command, cwd=ROOT, env=env, check=True)
    files = HTTP + PERSISTENCE + TRANSPORT + COMPOSITION + CONTRACTS
    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", *HTTP],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--select",
            "ANN,F,I",
            *CONTRACTS,
            *PERSISTENCE,
            *TRANSPORT,
            *COMPOSITION,
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--no-cache", "--check", *files],
        cwd=ROOT,
        check=True,
    )
    print(f"PASS: {len(files)} Python dependency boundary files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
