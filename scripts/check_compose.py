#!/usr/bin/env python3
"""Validate current deployment syntax with synthetic configuration; never start it."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("Docker with Compose v2 is required for syntax validation.")
    with tempfile.TemporaryDirectory(prefix="a2flow-compose-check-") as directory:
        temp = Path(directory)
        for name in ("java.env", "accounts.env", "bside.env", "execution.env", "content.env", "empty.env"):
            (temp / name).touch(mode=0o600)
        environment = dict(os.environ)
        environment.update({
            "A2FLOW_JAVA_IMAGE": "a2flow-syntax-only:java",
            "A2FLOW_PYTHON_IMAGE": "a2flow-syntax-only:python",
            "A2FLOW_EXECUTION_IMAGE": "a2flow-syntax-only:execution",
            "A2FLOW_DEPLOY_PRIVATE": str(temp),
            "A2FLOW_EXECUTION_PRIVATE": str(temp),
            "A2FLOW_RELEASE_DIRECTORY": str(temp / "release"),
            "A2FLOW_EXISTING_SECRETS": str(temp / "secrets"),
            "A2FLOW_EXISTING_POSTGRES_SOCKET": "a2flow-syntax-only-socket",
            "A2FLOW_PRIVATE": str(temp / "selfhost"),
            "A2FLOW_APP_UID": "1000",
            "A2FLOW_APP_GID": "1000",
            "A2FLOW_DB_PREFIX": "a2flow_syntax_only",
        })
        groups = (
            ("deploy/selfhost/compose.yaml",),
            ("deploy/java-management/compose.yaml",),
            ("deploy/python-execution/compose.yaml",),
            ("deploy/java-management/compose.yaml", "deploy/python-execution/management.override.yaml"),
        )
        for group in groups:
            command = ["docker", "compose", "--env-file", str(temp / "empty.env"), "--project-name", "a2flow-syntax-check"]
            for name in group:
                command.extend(["-f", str(ROOT / name)])
            subprocess.run([*command, "config", "--quiet"], cwd=ROOT, env=environment, check=True)
            print("PASS: " + " + ".join(group))
    print("Syntax only: no containers, credentials, images, accounts or databases provisioned.")


if __name__ == "__main__":
    main()
