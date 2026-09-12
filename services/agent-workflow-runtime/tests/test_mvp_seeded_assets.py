"""Offline Runtime adapter checks against the fixed seeded demo bundle."""

from dataclasses import replace
import json
import unittest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langsmith import tracing_context

from agent_workflow_runtime import ActionService, LangGraphContinuation

from a2flow_asset_store import AssetReader
from a2flow_asset_store.records import canonical, digest
from activity_planning_demo import (
    APPLICATION_KEY, BUDGET_KEY, CONFIRM_KEY, CONFIRM_OPERATION,
    OPERATION_MAP, ability_definition, application_validator, bundle_validator,
)
from activity_planning_demo.bundle import NAMESPACE, make_bundle

from agent_workflow_runtime.lifecycle import RunLifecycle
from agent_workflow_runtime.assembly import build_engine
from agent_workflow_runtime.asset_adapters import OperationSpec, RuntimeAssets
from agent_workflow_runtime.models import ActionRejected, Interaction
from agent_workflow_runtime.mvp_assembly import MvpRuntimeHost, confirmed_context
from agent_workflow_runtime.mvp_tools import build_tools, validators
from agent_workflow_runtime.native_control import ControlledRunRunner
from lifecycle_support import RunRepository, fixture
from agent_workflow_runtime.workflow_loader import compose_workflow
from runtime_phase1.scripted_model import ScriptedToolModel
from support import Repository, context


class BundleRepository:
    environment = "PRT"

    def __init__(self, mutate=None):
        self.validator = bundle_validator()
        document = make_bundle("PRT")
        if mutate is not None:
            mutate(document)
            for asset in document["assets"]:
                source = {key: value for key, value in asset.items()
                          if key != "contentDigest"}
                asset["contentDigest"] = digest(canonical(source))
        self.bundle = self.validator.validate(
            document, expected_namespace=NAMESPACE,
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


def ability_profile(key):
    expected = canonical(ability_definition(key))
    return lambda definition: canonical(definition) == expected


def operation_specs():
    return {
        BUDGET_KEY: OperationSpec(
            OPERATION_MAP[BUDGET_KEY], budget_input, budget_result,
            ability_profile(BUDGET_KEY),
            model_allowed=True,
        ),
        CONFIRM_OPERATION: OperationSpec(
            OPERATION_MAP[CONFIRM_OPERATION], confirm_input, confirm_result,
            ability_profile(CONFIRM_KEY),
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

    def test_node_prompt_names_every_required_tool_before_terminal_text(self):
        host = object.__new__(MvpRuntimeHost)
        prompt = host._system_prompt(
            {"skillKey": "activity-planning/plan"},
            ("use_skill", "execute_ability", "render_application"),
        )
        self.assertIn("First call use_skill", prompt)
        self.assertIn(
            "Finalizer requires these Tools to have returned successfully: "
            "use_skill, execute_ability, render_application",
            prompt,
        )
        self.assertNotIn("call the same required Tool again", prompt)

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

    def test_missing_confirmed_context_fails_closed(self):
        with self.assertRaisesRegex(ActionRejected, "PREDECESSOR_CONTEXT_UNAVAILABLE"):
            confirmed_context(Repository(), self.run, ("plan",))

    def _mutated_assets(self, ability_key, change):
        def mutate(document):
            ability = next(asset for asset in document["assets"]
                           if asset["kind"] == "ABILITY" and asset["key"] == ability_key)
            change(ability["definition"])

        reader = AssetReader(BundleRepository(mutate), NAMESPACE)
        _, _, sample = fixture()
        resolved = reader.resolve_workflow("activity-planning", sample.owner)
        run = replace(
            sample, definition_key="activity-planning", entry_node_id="plan",
            versions=resolved.effective_versions,
        )
        calls = []

        def execute(value, owner):
            calls.append((value, owner))
            return {"confirmed": True}

        specs = operation_specs()
        operation_ref = BUDGET_KEY if ability_key == BUDGET_KEY else CONFIRM_OPERATION
        specs[operation_ref] = replace(specs[operation_ref], execute=execute)
        return (RuntimeAssets(
            reader, run, specs, resolved.definition, bound_node_id="plan",
        ), run, calls)

    def test_changed_model_argument_schema_rejects_before_operation(self):
        def narrow(definition):
            definition["modelArgumentSchema"]["properties"]["participants"]["maximum"] = 2

        assets, run, calls = self._mutated_assets(BUDGET_KEY, narrow)
        with self.assertRaisesRegex(ActionRejected, "UNSUPPORTED_ABILITY_PROFILE"):
            assets.execute_ability(
                BUDGET_KEY, {"participants": 3, "budgetMinor": 1000}, run.context(),
            )
        self.assertEqual([], calls)

    def test_changed_action_output_or_binding_profile_rejects_before_operation(self):
        def output_schema(definition):
            definition["outputSchema"]["properties"]["selectedOptionId"]["maxLength"] = 1

        def missing_binding(definition):
            definition["resolvedInputSchema"]["required"].remove("optionId")
            definition["inputBindings"] = [
                binding for binding in definition["inputBindings"]
                if binding["targetPath"] != "/optionId"
            ]

        for change in (output_schema, missing_binding):
            assets, run, calls = self._mutated_assets(CONFIRM_KEY, change)
            application = assets.application(APPLICATION_KEY, run.context())
            card = {"cardId": "card", "nodeId": "plan", "interactionId": "interaction",
                    "data": {"options": [{"label": "A", "value": "a"}]}}
            interaction = Interaction(
                run.context("plan"), "interaction", APPLICATION_KEY,
                application["resolvedVersion"]["versionId"], run.thread_id,
                tuple(application["recordedVersions"]), display_json=json.dumps(card),
            )
            with self.subTest(change=change.__name__), self.assertRaisesRegex(
                ActionRejected, "UNSUPPORTED_ABILITY_PROFILE",
            ):
                assets.action(interaction, "confirm_activity")
            self.assertEqual([], calls)


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
            {"plan": plan_graph, "copy": copy_graph}, views,
            lambda node_ids: confirmed_context(interactions, run, node_ids),
            MemorySaver(),
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
        first_copy_input = copy_model.observedMessages[0]
        self.assertTrue(all(
            message.type in {"system", "human"} for message in first_copy_input
        ))
        visible = "\n".join(str(message.content) for message in first_copy_input)
        self.assertIn("Plan", visible)
        self.assertIn("方案已确认。", visible)
        self.assertIn("团建晚餐", visible)
        self.assertIn('"selectedOptionId":"dinner"', visible)
        self.assertNotIn("perPersonMinor", visible)
        self.assertNotIn("activity-planning/plan", visible)
