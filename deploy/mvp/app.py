"""Environment-bound private MVP app. Import performs no DDL or listener start."""

import os

from pydantic import SecretStr
from skillweave_contracts import TrustedContext

from activity_planning_demo import (
    application_data_validator, application_validator,
    bundle_validator,
)
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.mvp_assembly import MvpRuntimeHost

from .runtime_support import (
    BoundedDeepSeekFactory, SafeErrorObserver, database_conninfo, required,
)
from .operations import business_registry, operations


environment = required("A2FLOW_ENVIRONMENT")
if environment not in {"PRT", "ONLINE"}:
    raise RuntimeError("INVALID_HOST_ENVIRONMENT")
user_id = required("A2FLOW_USER_ID")
owner = TrustedContext.from_mapping({"userId": user_id, "environment": environment})


def model_configuration(reference, current_owner):
    if reference != "deepseek-v4-flash" or current_owner != owner:
        raise RuntimeError("MODEL_CONFIGURATION_NOT_FOUND")
    return {
        "model_id": "deepseek-v4-flash",
        "credential_ref": "env:DEEPSEEK_API_KEY",
        "timeout_seconds": 30.0,
        "options": {"thinking": "enabled", "reasoning_effort": "low", "max_tokens": 4096},
    }


def model_secret(reference, current_owner):
    if reference != "env:DEEPSEEK_API_KEY" or current_owner != owner:
        raise RuntimeError("MODEL_CREDENTIAL_UNAVAILABLE")
    return SecretStr(required("DEEPSEEK_API_KEY"))


compose_mode = bool(os.environ.get("A2FLOW_MODEL_BUDGET_FILE"))
conninfo = database_conninfo() if compose_mode else required("A2FLOW_DATABASE_URL")
model_factory = (BoundedDeepSeekFactory(owner) if compose_mode else
                 DeepSeekModelFactory(model_configuration, model_secret))
error_observer = SafeErrorObserver() if os.environ.get("A2FLOW_SAFE_ERROR_FILE") else None


host = MvpRuntimeHost(
    conninfo=conninfo,
    database=required("A2FLOW_DATABASE_NAME"),
    environment=environment,
    namespace=os.environ.get("A2FLOW_ASSET_NAMESPACE", "a2flow-mvp-activity-planning"),
    bundle_validator=bundle_validator(),
    application_validator=application_validator,
    operation_specs=operations(),
    model_factory=model_factory,
    identity_resolver=lambda scope: owner,
    application_data_validator=application_data_validator,
    static_directory=os.environ.get("A2FLOW_STATIC_DIRECTORY"),
    unexpected_error_observer=error_observer,
)
app = host.create_app()
