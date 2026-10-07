"""Explicit initialization and loopback-only service entry points.

Use a new Compose project/volume, never an older identity database. Initialization
only installs reviewed demo prerequisites; acceptance edits are made in M UI.
"""

import os
import sys

from psycopg.conninfo import make_conninfo


def configure():
    from deploy.common.config import _secret, _required
    dsn = make_conninfo(
        host="/run/postgresql", dbname=_required("A2FLOW_DATABASE_NAME"),
        user=_required("A2FLOW_DATABASE_USER"),
        password=_secret("A2FLOW_POSTGRES_PASSWORD_FILE"),
    )
    if _required("A2FLOW_ENVIRONMENT") != "PRT":
        raise RuntimeError("REALCHAT_COMPOSE_PRT_ONLY")
    for name in ("A2FLOW_DATABASE_URL", "A2FLOW_ATTENDED_DATABASE_URL",
                 "A2FLOW_BSIDE_DATABASE_URL"):
        os.environ[name] = dsn
    os.environ["DEEPSEEK_API_KEY"] = _secret("A2FLOW_DEEPSEEK_KEY_FILE")
    os.environ["A2FLOW_BSIDE_PEPPER"] = _secret("A2FLOW_PEPPER_FILE")
    os.environ["A2FLOW_BSIDE_INTERNAL_TOKEN"] = _secret("A2FLOW_INTERNAL_TOKEN_FILE")
    return dsn


def initialize(dsn):
    from deploy.attended.seed import main as schemas
    from deploy.assets import bundle_validator
    from activity_planning_demo.package_bundle import make_package_bundle
    from a2flow_asset_store import PostgresAssetRepository
    schemas()
    database = os.environ["A2FLOW_DATABASE_NAME"]
    namespace = os.environ["A2FLOW_ASSET_NAMESPACE"]
    repository = PostgresAssetRepository(
        dsn, environment="PRT", database=database, validator=bundle_validator())
    repository.setup()
    repository.import_bundle(make_package_bundle("PRT"),
                             expected_namespace=namespace, dry_run=False)
    print("PRT schemas and reviewed prerequisite assets initialized")


def bside():
    from deploy.attended.bside_app import create_app_from_environment
    from fastapi.staticfiles import StaticFiles
    app = create_app_from_environment()
    app.mount("/employee", StaticFiles(
        directory=os.environ["A2FLOW_EMPLOYEE_STATIC_DIRECTORY"], html=True),
        name="employee")
    return app


def runtime():
    from deploy.assets import (
        bundle_validator, application_validator, application_data_validator,
    )
    from deploy.mvp.operations import operations
    from agent_workflow_runtime.workflow_rpc_host import RpcWorkflowHost
    from agent_workflow_runtime.rpc_client import RpcClient
    from deploy.attended.runtime_app import completed_card, SchedulerEventSink
    from agent_workflow_runtime.internal_identity import private_identity
    from agent_workflow_runtime.model_factory import DeepSeekModelFactory
    from agent_workflow_runtime.personal_memory import PersonalMemory
    from pydantic import SecretStr

    def configuration(reference, owner):
        if reference != "deepseek-v4-flash" or owner.environment != "PRT":
            raise RuntimeError("MODEL_CONFIGURATION_NOT_FOUND")
        return {"model_id": reference, "credential_ref": "env:DEEPSEEK_API_KEY",
                "timeout_seconds": 30.0,
                "options": {"thinking": "disabled", "max_tokens": 4096}}

    def secret(reference, owner):
        if reference != "env:DEEPSEEK_API_KEY" or owner.environment != "PRT":
            raise RuntimeError("MODEL_CREDENTIAL_UNAVAILABLE")
        return SecretStr(os.environ["DEEPSEEK_API_KEY"])

    dsn = os.environ["A2FLOW_DATABASE_URL"]
    return RpcWorkflowHost(
        rpc=RpcClient.from_environment(os.environ),
        completion_observer=completed_card, event_sink=SchedulerEventSink(dsn),
        conninfo=dsn, database=os.environ["A2FLOW_DATABASE_NAME"],
        environment="PRT", namespace=os.environ["A2FLOW_ASSET_NAMESPACE"],
        bundle_validator=bundle_validator(),
        application_validator=application_validator,
        application_data_validator=application_data_validator,
        operation_specs=operations(),
        model_factory=DeepSeekModelFactory(configuration, secret),
        identity_resolver=private_identity("PRT"),
        personal_memory=PersonalMemory(dsn),
    ).create_app()


def main():
    commands = {
        "bside": "deploy.realchat.launcher:bside",
        "runtime": "deploy.realchat.launcher:runtime",
    }
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command not in {*commands, "initialize"}:
        raise RuntimeError("INVALID_REALCHAT_COMMAND")
    dsn = configure()
    if command == "initialize":
        initialize(dsn)
        return
    raw_port = os.environ["A2FLOW_LISTEN_PORT"]
    port = int(raw_port)
    if not 1024 <= port <= 65535 or str(port) != raw_port:
        raise RuntimeError("INVALID_LISTEN_PORT")
    import uvicorn
    uvicorn.run(commands[command], factory=True, host="127.0.0.1", port=port,
                proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
