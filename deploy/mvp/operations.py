"""Registered demo operations shared by Chat and Workflow composition roots."""

from a2flow_asset_store.records import canonical
from activity_planning_demo import ABILITY_DEFINITION_KEYS, MODEL_ABILITY_KEYS, ability_definition
from activity_planning_demo.service import (
    SERVICE_ACTIVITY_PACKAGE, SERVICE_ACTIVITY_PLANNING, ActivityPlanningService,
)
from agent_workflow_runtime.asset_adapters import OperationSpec
from agent_workflow_runtime.business import BusinessRegistry, parse_business_call_ref, schema_validator


def business_registry():
    service = ActivityPlanningService()
    return BusinessRegistry({SERVICE_ACTIVITY_PLANNING: service, SERVICE_ACTIVITY_PACKAGE: service})


def operations():
    registry = business_registry()
    specs = {}
    for key in ABILITY_DEFINITION_KEYS:
        definition = ability_definition(key)
        service, method = parse_business_call_ref(definition["adapterOperationRef"])
        expected = canonical(definition)
        specs[definition["adapterOperationRef"]] = OperationSpec(
            registry.dispatcher(service, method),
            schema_validator(definition["resolvedInputSchema"]),
            schema_validator(definition["outputSchema"]),
            lambda value, expected=expected: canonical(value) == expected,
            model_allowed=key in MODEL_ABILITY_KEYS,
            action_allowed=key not in MODEL_ABILITY_KEYS,
        )
    return specs
