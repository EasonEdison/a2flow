"""Attended schema bootstrap: apply b-side and scheduler schemas (idempotent).

Asset-store tables and the reviewed asset seed come from deploy.mvp.seed, run
separately in the same init step. Import performs no DDL.
"""

from __future__ import annotations

import os
from importlib.resources import files

import psycopg


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_ATTENDED_CONFIGURATION:" + name)
    return value


def main() -> None:
    dsn = required("A2FLOW_ATTENDED_DATABASE_URL")
    with psycopg.connect(dsn, autocommit=True) as connection:
        for package, resource in (
            ("a2flow_bside", "schema.sql"),
            ("a2flow_scheduler", "schema.sql"),
        ):
            script = files(package).joinpath(resource).read_text(encoding="utf-8")
            connection.execute(script)
    print("attended schemas applied")
    from agent_workflow_runtime.chat.persistence import ConversationStore
    ConversationStore(dsn).setup()
    from agent_workflow_runtime.personal_memory import PersonalMemory
    PersonalMemory(dsn).setup()
    print("conversation checkpoint schema applied")


if __name__ == "__main__":
    main()
