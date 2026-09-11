"""Offline Runtime adapter checks against the fixed seeded demo bundle."""

from dataclasses import replace
import json
import unittest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langsmith import tracing_context

from agent_workflow_runtime import ActionService, LangGraphContinuation

from a2flow_asset_store import AssetReader
from activity_planning_demo import (
    APPLICATION_KEY, BUDGET_KEY, CONFIRM_KEY, CONFIRM_OPERATION,
    OPERATION_MAP, application_validator, bundle_validator,
)
from activity_planning_demo.bundle import NAMESPACE, make_bundle

from agent_workflow_runtime.lifecycle import RunLifecycle
from agent_workflow_runtime.assembly import build_engine
from agent_workflow_runtime.asset_adapters import OperationSpec, RuntimeAssets
from agent_workflow_runtime.models import ActionRejected, Interaction
from agent_workflow_runtime.mvp_tools import build_tools, validators
from agent_workflow_runtime.native_control import ControlledRunRunner
from lifecycle_support import RunRepository, fixture
from agent_workflow_runtime.workflow_loader import compose_workflow
from runtime_phase1.scripted_model import ScriptedToolModel
from support import Repository, context


class BundleRepository:
    environment = "PRT"

    def __init__(self):
        self.validator = bundle_validator()
        self.bundle = self.validator.validate(
            make_bundle("PRT"), expected_namespace=NAMESPACE,
            expected_environment="PRT",
        )

    def read(self, namespace):
        if namespace != NAMESPACE:
            raise AssertionError("unexpected namespace")
        return self.bundle


def budget_input(value):
    return (type(value) is dict and set(value) == {"participants", "budgetMinor"}
            and type(value["participants"]) is int and value["participants"] >= 1
            and type(value["budgetMinor"]) is int and value["budgetMinor"] >= 0)


def budget_result(value):
    return (type(value) is dict and set(value) == {
        "participants", "budgetMinor", "perPersonMinor", "remainderMinor"}
        and all(type(item) is int for item in value.values()))


def confirm_input(value):
    return (type(value) is dict and set(value) == {"optionId", "confirmed"}
            and type(value["optionId"]) is str and value["confirmed"] is True)


def confirm_result(value):
    return (type(value) is dict and set(value) == {"selectedOptionId", "confirmed"}
            and type(value["selectedOptionId"]) is str and value["confirmed"] is True)


def operation_specs():
    return {
        BUDGET_KEY: OperationSpec(
            OPERATION_MAP[BUDGET_KEY], budget_input, budget_result,
            model_allowed=True,
        ),
        CONFIRM_OPERATION: OperationSpec(
            OPERATION_MAP[CONFIRM_OPERATION], confirm_input, confirm_result,
            action_allowed=True,
        ),
    }


class SeededRuntimeAssetsTest(unittest.TestCase):
    def setUp(self):
        self.reader = AssetReader(BundleRepository(), NAMESPACE)
        _, _, sample = fixture()
        resolved = self.reader.resolve_workflow("activity-planning", sample.owner)
        self.run = replace(
            sample, definition_key="activity-planning", entry_node_id="plan",
            versions=resolved.effective_versions,
        )
        self.definition = resolved.definition
        operations = operation_specs()
        self.assets = RuntimeAssets(
            self.reader, self.run, operations, self.definition,
            bound_node_id="plan",
        )

    def test_seeded_skill_ability_and_application_resolve_as_one_closure(self):
        material = self.reader.load_skill(
            "activity-planning/plan", self.run.context("plan"),
        )
        self.assertEqual(
            ("execute_ability", "render_application"),
            material.required_tool_names,
        )
        budget = self.assets.execute_ability(
            BUDGET_KEY, {"participants": 3, "budgetMinor": 1000},
            self.run.context(),
        )
        self.assertEqual(333, budget["output"]["perPersonMinor"])
        application = self.assets.application(APPLICATION_KEY, self.run.context())
        self.assertTrue(application_validator(application["application"]))
        self.assertEqual(dict(self.run.versions), dict(application["recordedVersions"]))

    def test_seeded_confirmation_is_action_only_and_option_bound(self):
        with self.assertRaisesRegex(ActionRejected, "ABILITY_NOT_MODEL_CALLABLE"):
            self.assets.execute_ability(
                CONFIRM_KEY, {"optionId": "a", "confirmed": True},
                self.run.context(),
            )
        application = self.assets.application(APPLICATION_KEY, self.run.context())
        card = {"cardId": "card", "nodeId": "plan", "interactionId": "interaction",
                "data": {"options": [{"label": "A", "value": "a"},
                                     {"label": "B", "value": "b"}]}}
        interaction = Interaction(
            self.run.context("plan"), "interaction", APPLICATION_KEY,
            application["resolvedVersion"]["versionId"], self.run.thread_id,
            tuple(application["recordedVersions"]),
            display_json=json.dumps(card),
        )
        config = self.assets.action(interaction, "confirm_activity")
        self.assertTrue(config.validate_input({"optionId": "a", "confirmed": True}))
        self.assertFalse(config.validate_input({"optionId": "foreign", "confirmed": True}))


class SeededRuntimeGraphTest(unittest.TestCase):

    def test_actual_seeded_tools_wait_and_resume_through_saved_action(self):
        reader = AssetReader(BundleRepository(), NAMESPACE)
        repository = RunRepository()
        lifecycle = RunLifecycle(repository)
        owner = context().trusted_context
        definition = reader.resolve_workflow("activity-planning", owner)
        run, _ = lifecycle.allocate(
            owner, "mvp-start", "activity-planning",
            {"requirement": "Plan an activity"}, "plan",
            lambda *_: definition.effective_versions,
        )
        configuration = RuntimeAssets(
            reader, run, operation_specs(), definition.definition,
        )
        interactions = Repository()
        service = ActionService(
            interactions, configuration, configuration.executor, None,
            lifecycle=lifecycle,
        )
        assets = RuntimeAssets(
            reader, run, operation_specs(), definition.definition,
            bound_node_id="plan",
        )
        tools = build_tools(assets, service, application_validator)
        model = ScriptedToolModel(responses=[
            AIMessage(content="", tool_calls=[{
                "name": "use_skill",
                "args": {"skillKey": "activity-planning/plan"},
                "id": "skill", "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "execute_ability",
                "args": {"abilityKey": BUDGET_KEY,
                         "arguments": {"participants": 4, "budgetMinor": 10000}},
                "id": "budget", "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "render_application",
                "args": {"applicationKey": APPLICATION_KEY, "data": {
                    "prompt": "请选择活动方案",
                    "options": [{"label": "团建晚餐", "value": "dinner"},
                                {"label": "户外徒步", "value": "hiking"}]}},
                "id": "render", "type": "tool_call",
            }]),
            AIMessage(content="方案已确认。"),
        ])
        plan_graph = build_engine(
            model, tools, validators(),
            ("use_skill", "execute_ability", "render_application"),
            harness_profile_key="scriptedtoolmodel",
            terminal_guard=service.assert_finalizable,
            run_lifecycle=lifecycle, node_context=run.context("plan"),
        )
        copy_assets = RuntimeAssets(
            reader, run, operation_specs(), definition.definition,
            bound_node_id="copy",
        )
        copy_tools = {
            item.name: item
            for item in build_tools(copy_assets, service, application_validator)
        }
        copy_model = ScriptedToolModel(responses=[
            AIMessage(content="", tool_calls=[{
                "name": "use_skill",
                "args": {"skillKey": "activity-planning/copy"},
                "id": "copy-skill", "type": "tool_call",
            }]),
            AIMessage(content="一起出发，把好心情写进这次活动。"),
        ])
        copy_graph = build_engine(
            copy_model, [copy_tools["use_skill"]],
            {"use_skill": validators()["use_skill"]}, ("use_skill",),
            harness_profile_key="scriptedtoolmodel",
            terminal_guard=service.assert_finalizable,
            run_lifecycle=lifecycle, node_context=run.context("copy"),
        )

        class Views:
            def __init__(self):
                self.outputs = {}

            def ensure(self, current_run, current_definition, versions):
                self.definition = current_definition

            def node(self, current_owner, run_id, node_id, status):
                pass

            def complete(self, current_owner, run_id, node_id, content):
                self.outputs[node_id] = content
        views = Views()
        graph = compose_workflow(
            run, lifecycle, definition.definition,
            {"plan": plan_graph, "copy": copy_graph}, views, MemorySaver(),
        )
        service.continuation = LangGraphContinuation(graph, lifecycle=lifecycle)
        runner = ControlledRunRunner(lifecycle, None, None)
        with tracing_context(enabled=False):
            waiting = runner.invoke(
                run, graph, {"messages": [{"role": "user", "content": "Plan"}]},
            )
        self.assertIn("__interrupt__", waiting)
        item = next(iter(interactions.items.values()))
        card = json.loads(item.display_json)
        self.assertEqual("selection", card["components"][2]["id"])
        payload = {
            "runId": run.run_id, "nodeId": "plan",
            "interactionId": item.interaction_id,
            "actionName": "confirm_activity", "controlRequestId": "confirm-one",
            "inputs": {"optionId": "dinner", "confirmed": True},
        }
        with tracing_context(enabled=False):
            result = runner.action(run, service, payload)
        self.assertTrue(result.interaction_completed)
        self.assertEqual("RETURNED", result.resume_status)
        self.assertEqual("SUCCEEDED", lifecycle.read(owner, run.run_id).status)
        self.assertEqual(
            {"plan": "方案已确认。", "copy": "一起出发，把好心情写进这次活动。"},
            views.outputs,
        )
