"""Load installation-owned configuration, then reuse the actual product hosts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def main() -> None:
    role = sys.argv[1] if len(sys.argv) == 2 else ""
    allowed = {"bside", "runtime", "accounts", "execution", "content", "scheduler", "management-agent", "databases", "schemas"}
    if role not in allowed:
        raise SystemExit("Unknown selfhost role")
    config = json.loads(Path("/run/selfhost/config.json").read_text())
    os.environ.update(config["environment"])
    if role in {"databases", "schemas"}:
        from .bootstrap import run
        run(role, config)
        return
    if role in {"bside", "runtime"}:
        from deploy.realchat.launcher import main as start
        sys.argv = [sys.argv[0], role]
    elif role == "accounts":
        from deploy.accounts.launcher import main as start
    elif role == "content":
        from a2flow_content.host import main as start
        sys.argv = [sys.argv[0]]
    elif role == "execution":
        from a2flow_a2ui.host import main as start
    elif role == "scheduler":
        from a2flow_scheduler.main import main as start
    else:
        from agent_workflow_runtime.management_agent.__main__ import main as start
        os.environ["DEEPSEEK_API_KEY"] = Path("/run/selfhost/model_key").read_text().strip()
        sys.argv = [sys.argv[0]]
    result = start()
    if isinstance(result, int):
        raise SystemExit(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # DB/provider exceptions can include credentials; never render their messages.
        raise SystemExit("SELFHOST_STARTUP_FAILED:" + type(error).__name__) from None
