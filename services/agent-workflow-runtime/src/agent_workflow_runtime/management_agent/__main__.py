"""Host entrypoint. Secrets resolve at deployment boundaries, never request arguments."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pydantic import SecretStr

from ..model_factory import DeepSeekModelFactory
from .bridge import ManagementToolBridge
from .host import serve
from .runner import ManagementRunner
from .store import ManagementStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-schema", action="store_true")
    args = parser.parse_args()
    dsn_file = os.environ.get("A2FLOW_MANAGEMENT_AGENT_POSTGRES_DSN_FILE")
    if not dsn_file:
        raise RuntimeError("MANAGEMENT_AGENT_DSN_FILE_REQUIRED")
    store = ManagementStore(
        Path(dsn_file).read_text().strip(),
        os.environ.get("A2FLOW_MANAGEMENT_AGENT_SCHEMA", "a2flow_management_agent"),
    )
    if args.init_schema:
        store.setup()
        print("Management Agent dedicated schema initialized; no existing B-side domain migration.")
        return
    reference = os.environ.get("A2FLOW_MANAGEMENT_AGENT_MODEL", "deepseek-v4-flash")

    def configuration(model_reference: str, owner: object) -> dict[str, object]:
        del owner
        if model_reference != reference:
            raise ValueError("MODEL_REFERENCE_INVALID")
        return dict(
            model_id=reference,
            credential_ref="env:DEEPSEEK_API_KEY",
            timeout_seconds=60.0,
            options=dict(thinking="disabled", max_tokens=8192),
        )

    def secret(credential_reference: str, owner: object) -> SecretStr:
        del owner
        if credential_reference != "env:DEEPSEEK_API_KEY":
            raise ValueError("MODEL_CREDENTIAL_REFERENCE_INVALID")
        return SecretStr(os.environ["DEEPSEEK_API_KEY"])

    bridge = ManagementToolBridge.from_environment(os.environ)
    runner = ManagementRunner(
        store,
        bridge,
        DeepSeekModelFactory(configuration, secret),
        reference,
        max_model_calls=int(os.environ.get("A2FLOW_MANAGEMENT_AGENT_MAX_MODEL_CALLS", "64")),
    )
    serve(os.environ.get("A2FLOW_MANAGEMENT_AGENT_BIND", "127.0.0.1:50055"), store, runner)


if __name__ == "__main__":
    main()
