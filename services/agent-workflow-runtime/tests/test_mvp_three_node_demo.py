"""Offline contract and execution checks for the additive three-node demo."""

from dataclasses import replace
import json
import unittest

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langsmith import tracing_context

from a2flow_asset_store import AssetReader
from a2flow_asset_store.records import canonical
from activity_planning_demo import (
    OPERATION_MAP,
    PACKAGE_CHOOSE_APPLICATION_KEY,
    PACKAGE_DISPLAY_APPLICATION_KEY,
    PACKAGE_SCHEDULE_ABILITY_KEY,
    PACKAGE_SCHEDULE_APPLICATION_KEY,
    PACKAGE_SCHEDULE_OPERATION,
    PACKAGE_SELECT_ABILITY_KEY,
    PACKAGE_SELECT_OPERATION,
    PACKAGE_WORKFLOW_KEY,
    ability_definition,
    application_data_validator,
    application_validator,
    bundle_validator,
)
from activity_planning_demo.bundle import NAMESPACE, make_bundle
from activity_planning_demo.package_bundle import make_package_bundle
from agent_workflow_runtime.actions import ActionService
from agent_workflow_runtime.assembly import build_engine
from agent_workflow_runtime.asset_adapters import OperationSpec, RuntimeAssets
from agent_workflow_runtime.langgraph_adapter import LangGraphContinuation
from agent_workflow_runtime.lifecycle import RunLifecycle
from agent_workflow_runtime.mvp_tools import build_tools, validators
from agent_workflow_runtime.native_control import ControlledRunRunner
from agent_workflow_runtime.serialization import decode, encode
from agent_workflow_runtime.ui_projection import (
    change_node, complete_node, initial_view, project_view,
)
from agent_workflow_runtime.workflow_loader import CONTEXT_PREFIX, compose_workflow
from lifecycle_support import RunRepository
from runtime_phase1.scripted_model import ScriptedToolModel
from support import Repository, context


class BundleRepository:
    environment = "PRT"

    def __init__(self):
        self.validator = bundle_validator()
        self.bundle = self.validator.validate(
            make_package_bundle("PRT"), expected_namespace=NAMESPACE,
            expected_environment="PRT",
        )

    def read(self, namespace):
        self.assert_namespace(namespace)
        return self.bundle

    @staticmethod
    def assert_namespace(namespace):
        if namespace != NAMESPACE:
            raise AssertionError("unexpected namespace")


def select_input(value):
    return (type(value) is dict and set(value) == {"optionId"}
            and type(value["optionId"]) is str)


def select_result(value):
    return (type(value) is dict and set(value) == {"selectedOptionId"}
            and type(value["selectedOptionId"]) is str)


def confirm_input(value):
    return (type(value) is dict and set(value) == {"optionId", "confirmed"}
            and type(value["optionId"]) is str and value["confirmed"] is True)


def confirm_result(value):
    return (type(value) is dict and set(value) == {"selectedOptionId", "confirmed"}
            and type(value["selectedOptionId"]) is str and value["confirmed"] is True)


def ability_profile(key):
    expected = canonical(ability_definition(key))
    return lambda value: canonical(value) == expected


def operation_specs():
    return {
        PACKAGE_SELECT_OPERATION: OperationSpec(
            OPERATION_MAP[PACKAGE_SELECT_OPERATION], select_input, select_result,
            ability_profile(PACKAGE_SELECT_ABILITY_KEY), action_allowed=True,
        ),
        PACKAGE_SCHEDULE_OPERATION: OperationSpec(
            OPERATION_MAP[PACKAGE_SCHEDULE_OPERATION], confirm_input, confirm_result,
            ability_profile(PACKAGE_SCHEDULE_ABILITY_KEY), action_allowed=True,
        ),
    }


class Views:
    def ensure(self, run, definition, versions):
        self.document = initial_view(run, definition, versions)

    def node(self, owner, run_id, node_id, status):
        change_node(self.document, node_id, status)

    def complete(self, owner, run_id, node_id, content):
        complete_node(self.document, node_id, content)


def scripted_node(run, node_id, assets, service, responses):
    tools = build_tools(
        assets, service, application_validator, application_data_validator,
    )
    model = ScriptedToolModel(responses=responses)
    graph = build_engine(
        model, tools, validators(), ("use_skill", "render_application"),
        harness_profile_key="scriptedtoolmodel",
        terminal_guard=service.assert_finalizable,
        run_lifecycle=service.lifecycle, node_context=run.context(node_id),
    )
    return model, graph


class ThreeNodeDemoTest(unittest.TestCase):
    def test_bundle_is_additive_closed_and_three_skills_are_independent(self):
        bundle = make_package_bundle("PRT")
        validated = bundle_validator().validate(
            bundle, expected_namespace=NAMESPACE, expected_environment="PRT",
        )
        self.assertEqual(10, len(validated.assets))
        old_identities = {(asset["kind"], asset["key"], asset["versionId"])
                          for asset in make_bundle("PRT")["assets"]}
        new_identities = {(asset["kind"], asset["key"], asset["versionId"])
                          for asset in bundle["assets"]}
        self.assertFalse(old_identities & new_identities)
        self.assertEqual({"v1"}, {identity[2] for identity in new_identities})
        workflow = next(asset for asset in validated.assets if asset.kind == "WORKFLOW")
        self.assertEqual(PACKAGE_WORKFLOW_KEY, workflow.key)
        self.assertEqual(
            ["choose_plan", "confirm_schedule", "show_activity_package"],
            [node["nodeId"] for node in workflow.definition["nodes"]],
        )
        skills = [asset for asset in validated.assets if asset.kind == "SKILL"]
        self.assertEqual(3, len(skills))
        for skill in skills:
            self.assertEqual(["render_application"], skill.definition["requiredToolNames"])
            text = skill.definition["entries"][0]["base64"]
            self.assertTrue(text)
        display = next(asset for asset in validated.assets
                       if asset.key == PACKAGE_DISPLAY_APPLICATION_KEY)
        self.assertEqual(
            {"tool": "render_application", "interactionMode": "DISPLAY_ONLY",
             "requiresPause": False},
            display.definition["renderPolicy"],
        )
        self.assertEqual([], display.definition["actionPolicies"])

    def test_two_saved_actions_flow_downstream_and_display_card_survives_terminal_view(self):
        reader = AssetReader(BundleRepository(), NAMESPACE)
        owner = context().trusted_context
        resolved = reader.resolve_workflow(PACKAGE_WORKFLOW_KEY, owner)
        lifecycle = RunLifecycle(RunRepository())
        run, _ = lifecycle.allocate(
            owner, "start-three", PACKAGE_WORKFLOW_KEY,
            {"requirement": "为 20 人策划周五团队活动"}, "choose_plan",
            lambda *_: resolved.effective_versions,
        )
        interactions = Repository()
        configuration = RuntimeAssets(reader, run, operation_specs(), resolved.definition)
        service = ActionService(
            interactions, configuration, configuration.executor, None,
            lifecycle=lifecycle,
        )

        definitions = (
            ("choose_plan", "activity-package/choose-plan", [
                AIMessage(content="", tool_calls=[{"name": "use_skill",
                    "args": {"skillKey": "activity-package/choose-plan"},
                    "id": "skill-one", "type": "tool_call"}]),
                AIMessage(content="", tool_calls=[{"name": "render_application",
                    "args": {"applicationKey": PACKAGE_CHOOSE_APPLICATION_KEY, "data": {
                        "prompt": "选择活动方案", "options": [
                            {"label": "城市定向", "value": "city"},
                            {"label": "创意工坊", "value": "studio"}]}},
                    "id": "render-one", "type": "tool_call"}]),
                AIMessage(content="已选择城市定向。"),
            ]),
            ("confirm_schedule", "activity-package/confirm-schedule", [
                AIMessage(content="", tool_calls=[{"name": "use_skill",
                    "args": {"skillKey": "activity-package/confirm-schedule"},
                    "id": "skill-two", "type": "tool_call"}]),
                AIMessage(content="", tool_calls=[{"name": "render_application",
                    "args": {"applicationKey": PACKAGE_SCHEDULE_APPLICATION_KEY, "data": {
                        "prompt": "确认执行安排", "options": [
                            {"label": "周五 18:30 集合", "value": "fri-evening"},
                            {"label": "周六 09:30 集合", "value": "sat-morning"}]}},
                    "id": "render-two", "type": "tool_call"}]),
                AIMessage(content="已确认周五晚间安排。"),
            ]),
            ("show_activity_package", "activity-package/show-package", [
                AIMessage(content="", tool_calls=[{"name": "use_skill",
                    "args": {"skillKey": "activity-package/show-package"},
                    "id": "skill-three", "type": "tool_call"}]),
                AIMessage(content="", tool_calls=[{"name": "render_application",
                    "args": {"applicationKey": PACKAGE_DISPLAY_APPLICATION_KEY, "data": {
                        "title": "团队城市定向活动包",
                        "selectedPlan": "城市定向",
                        "confirmedSchedule": "周五 18:30 集合",
                        "packageSummary": "20 人参与；地点与负责人待补充。"}},
                    "id": "render-three", "type": "tool_call"}]),
                AIMessage(content="最终活动包已保存。"),
            ]),
        )
        models, agents = {}, {}
        for node_id, skill_key, responses in definitions:
            assets = RuntimeAssets(
                reader, run, operation_specs(), resolved.definition,
                bound_node_id=node_id,
            )
            models[node_id], agents[node_id] = scripted_node(
                run, node_id, assets, service, responses,
            )
        views = Views()
        from agent_workflow_runtime.mvp_assembly import confirmed_context
        graph = compose_workflow(
            run, lifecycle, resolved.definition, agents, views,
            lambda nodes: confirmed_context(interactions, run, nodes), MemorySaver(),
        )
        service.continuation = LangGraphContinuation(graph, lifecycle=lifecycle)
        runner = ControlledRunRunner(lifecycle, None, None)
        with tracing_context(enabled=False):
            runner.invoke(run, graph, {"messages": [{"role": "user", "content": "策划活动"}]})
        first = next(item for item in interactions.items.values()
                     if item.context.invocation_scope.node_id == "choose_plan")
        first_card = json.loads(first.display_json)
        self.assertEqual(("WAITING", "REVALIDATION_REQUIRED"),
                         (first_card["state"], first_card["actionEligibility"]))
        self.assertEqual("select_activity_plan", first_card["actions"][0]["actionName"])
        self.assertEqual(["optionId"], first_card["actions"][0]["inputSchema"]["required"])
        self.assertEqual(
            ["prompt", "selection", "submit"], first_card["components"][0]["children"],
        )
        with tracing_context(enabled=False):
            runner.action(run, service, {"runId": run.run_id, "nodeId": "choose_plan",
                "interactionId": first.interaction_id, "actionName": "select_activity_plan",
                "controlRequestId": "select-one", "inputs": {"optionId": "city"}})
        second = next(item for item in interactions.items.values()
                      if item.context.invocation_scope.node_id == "confirm_schedule")
        second_card = json.loads(second.display_json)
        self.assertEqual("confirm_schedule", second_card["actions"][0]["actionName"])
        self.assertEqual(
            {"const": True},
            second_card["actions"][0]["inputSchema"]["properties"]["confirmed"],
        )
        self.assertEqual("确认执行安排", second_card["components"][3]["label"])
        with tracing_context(enabled=False):
            runner.action(run, service, {"runId": run.run_id, "nodeId": "confirm_schedule",
                "interactionId": second.interaction_id, "actionName": "confirm_schedule",
                "controlRequestId": "confirm-two",
                "inputs": {"optionId": "fri-evening", "confirmed": True}})

        self.assertEqual("SUCCEEDED", lifecycle.read(owner, run.run_id).status)
        final = next(item for item in interactions.items.values()
                     if item.context.invocation_scope.node_id == "show_activity_package")
        self.assertEqual(final, decode(encode(final)))
        self.assertEqual(("COMPLETED", False, True),
                         (final.phase, final.node_waiting, final.resume_consumed))
        card = json.loads(final.display_json)
        self.assertEqual(("READ_ONLY", "NOT_OPERABLE", []),
                         (card["state"], card["actionEligibility"], card["actions"]))
        by_id = {item.interaction_id: item for item in interactions.items.values()}
        self.assertEqual(
            ["title", "plan", "schedule", "package"],
            card["components"][0]["children"],
        )
        self.assertEqual(
            ["/title", "/selectedPlan", "/confirmedSchedule", "/packageSummary"],
            [component["text"]["path"] for component in card["components"][1:]],
        )
        self.assertEqual(
            {"title", "selectedPlan", "confirmedSchedule", "packageSummary"},
            set(card["inputSchema"]["required"]),
        )
        refreshed = project_view(
            views.document, 3, "SUCCEEDED", 3, by_id,
        )
        persisted = next(item for item in refreshed["cards"]
                         if item["nodeId"] == "show_activity_package")
        self.assertEqual("activity-package.display", persisted["applicationKey"])
        self.assertEqual("团队城市定向活动包", persisted["data"]["title"])
        self.assertEqual([3, 3, 3], [len(model.responses) for model in models.values()])
        visible = "\n".join(str(message.content)
                            for message in models["show_activity_package"].observedMessages[0])
        self.assertIn(CONTEXT_PREFIX.strip(), visible)
        self.assertIn("city", visible)
        self.assertIn("fri-evening", visible)


if __name__ == "__main__":
    unittest.main()
