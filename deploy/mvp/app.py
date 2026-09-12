"""Environment-bound private MVP app. Import performs no DDL or listener start."""

import os

from a2flow_asset_store.records import canonical
from pydantic import SecretStr
from skillweave_contracts import TrustedContext

from activity_planning_demo import (
    BUDGET_KEY, CONFIRM_KEY, CONFIRM_OPERATION, OPERATION_MAP,
    PACKAGE_SCHEDULE_ABILITY_KEY, PACKAGE_SCHEDULE_OPERATION,
    PACKAGE_SELECT_ABILITY_KEY, PACKAGE_SELECT_OPERATION,
    ability_definition, application_data_validator, application_validator,
    bundle_validator,
)
from agent_workflow_runtime.asset_adapters import OperationSpec
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.mvp_assembly import MvpRuntimeHost


def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_HOST_CONFIGURATION:" + name)
    return value


def budget_input(value):
    return (type(value) is dict and set(value) == {"participants", "budgetMinor"}
            and type(value["participants"]) is int and 1 <= value["participants"] <= 100000
            and type(value["budgetMinor"]) is int and 0 <= value["budgetMinor"] <= 10**12)


def budget_result(value):
    if (type(value) is not dict or set(value) != {
            "participants", "budgetMinor", "perPersonMinor", "remainderMinor"}):
        return False
    if any(type(value[key]) is not int for key in value):
        return False
    people, budget = value["participants"], value["budgetMinor"]
    return (1 <= people <= 100000 and 0 <= budget <= 10**12
            and (value["perPersonMinor"], value["remainderMinor"]) == divmod(budget, people))


def confirmation_input(value):
    return (type(value) is dict and set(value) == {"optionId", "confirmed"}
            and type(value["optionId"]) is str and 1 <= len(value["optionId"]) <= 128
            and value["confirmed"] is True)


def confirmation_result(value):
    return (type(value) is dict and set(value) == {"selectedOptionId", "confirmed"}
            and type(value["selectedOptionId"]) is str
            and 1 <= len(value["selectedOptionId"]) <= 128
            and value["confirmed"] is True)


def selection_input(value):
    return (type(value) is dict and set(value) == {"optionId"}
            and type(value["optionId"]) is str and 1 <= len(value["optionId"]) <= 128)


def selection_result(value):
    return (type(value) is dict and set(value) == {"selectedOptionId"}
            and type(value["selectedOptionId"]) is str
            and 1 <= len(value["selectedOptionId"]) <= 128)


def ability_profile(key):
    expected = canonical(ability_definition(key))
    return lambda definition: canonical(definition) == expected


def operations():
    return {
        BUDGET_KEY: OperationSpec(
            OPERATION_MAP[BUDGET_KEY], budget_input, budget_result,
            ability_profile(BUDGET_KEY),
            model_allowed=True,
        ),
        CONFIRM_OPERATION: OperationSpec(
            OPERATION_MAP[CONFIRM_OPERATION], confirmation_input,
            confirmation_result, ability_profile(CONFIRM_KEY),
            action_allowed=True,
        ),
        PACKAGE_SELECT_OPERATION: OperationSpec(
            OPERATION_MAP[PACKAGE_SELECT_OPERATION], selection_input,
            selection_result, ability_profile(PACKAGE_SELECT_ABILITY_KEY),
            action_allowed=True,
        ),
        PACKAGE_SCHEDULE_OPERATION: OperationSpec(
            OPERATION_MAP[PACKAGE_SCHEDULE_OPERATION], confirmation_input,
            confirmation_result, ability_profile(PACKAGE_SCHEDULE_ABILITY_KEY),
            action_allowed=True,
        ),
    }


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


host = MvpRuntimeHost(
    conninfo=required("A2FLOW_DATABASE_URL"),
    database=required("A2FLOW_DATABASE_NAME"),
    environment=environment,
    namespace="a2flow-mvp-activity-planning",
    bundle_validator=bundle_validator(),
    application_validator=application_validator,
    operation_specs=operations(),
    model_factory=DeepSeekModelFactory(model_configuration, model_secret),
    identity_resolver=lambda scope: owner,
    application_data_validator=application_data_validator,
    static_directory=os.environ.get("A2FLOW_STATIC_DIRECTORY"),
)
app = host.create_app()
