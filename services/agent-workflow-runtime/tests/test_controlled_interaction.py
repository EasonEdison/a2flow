"""AF04 controlled Deep Agent wait/Action/Finalizer and fresh interaction probes."""

import json
import unittest

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agent_workflow_runtime import ActionRejected, ActionService, LangGraphContinuation
from agent_workflow_runtime.lifecycle import RunStoppedControl
from agent_workflow_runtime.native_control import ControlledRunRunner, RunGraphBinding
from lifecycle_support import fixture
from support import Configuration, Executor, Repository, Resolver, request
from test_langgraph_completion import render_call
from test_engine_spine_integration import IntegratedSkillMaterialPort
from runtime_phase1.a2ui_probe import build_render_application_tool, validate_render_application_model_args
from runtime_phase1.engine_spine_probe import build_engine_spine_probe
from runtime_phase1.scripted_model import ScriptedToolModel
from runtime_phase1.skill_registry_adapter import SkillRegistryResolver
from runtime_phase1.use_skill_probe import build_use_skill_tool, validate_use_skill_model_args


class ControlledInteractionTest(unittest.TestCase):
    def setUp(self):
        self.runs, self.life, self.run = fixture()
        self.repo, self.config, self.executor = Repository(), Configuration(), Executor()
        self.runner = ControlledRunRunner(self.life, None, None)
        self.built = {}

    def assemble(self, run):
        service = ActionService(self.repo, self.config, self.executor, None, lifecycle=self.life)
        materials = IntegratedSkillMaterialPort()
        tools = [
            build_use_skill_tool(SkillRegistryResolver(materials)),
            build_render_application_tool(Resolver(self.config), action_service=service),
        ]
        validators = {
            "use_skill": validate_use_skill_model_args,
            "render_application": validate_render_application_model_args,
        }
        model = ScriptedToolModel(responses=[
            AIMessage(content="", tool_calls=[{
                "name": "use_skill", "args": {"skillKey": "demo/evidence-first-brief"},
                "id": "skill-call", "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[render_call("render-call")]),
            AIMessage(content="Completed with current run evidence."),
        ])
        graph = build_engine_spine_probe(
            model, tools, validators, list(validators),
            harness_profile_key="scriptedtoolmodel", checkpointer=MemorySaver(),
            terminal_guard=service.assert_finalizable, run_lifecycle=self.life,
        )
        service.continuation = LangGraphContinuation(graph, lifecycle=self.life)
        self.built[run.run_id] = (graph, service, materials)
        return graph

    def start_waiting(self):
        graph = self.assemble(self.run)
        waiting = self.runner.invoke(self.run, graph, {
            "messages": [{"role": "user", "content": "Run current authorized interaction."}],
        })
        pending = waiting["__interrupt__"][0]
        item = self.repo.get((self.run.run_id, self.run.entry_node_id, pending.value["interactionId"]))
        return graph, self.built[self.run.run_id][1], item, pending

    def test_skill_wait_action_resume_finalizer_succeeds_through_controlled_entry(self):
        graph, service, item, _ = self.start_waiting()
        self.assertEqual("RUNNING", self.life.read(self.run.owner, self.run.run_id).status)
        result = self.runner.action(self.run, service, request(item))
        self.assertTrue(result.interaction_completed)
        self.assertEqual("RETURNED", result.resume_status)
        self.assertEqual(1, len(self.executor.calls))
        self.assertEqual(1, len(self.built[self.run.run_id][2].calls))
        self.assertEqual("SUCCEEDED", self.life.read(self.run.owner, self.run.run_id).status)
        self.assertFalse(graph.get_state({"configurable": {"thread_id": self.run.thread_id}}).next)
        facts = self.runs.operations(self.run.owner, self.run.run_id)
        self.assertTrue(any(f.kind == "FINALIZER" and f.status == "RETURNED" for f in facts))
        self.assertEqual(1, sum(f.kind == "ACTION" for f in facts))

    def test_stopped_wait_blocks_old_card_and_command_and_restart_has_new_interaction(self):
        graph, service, old_item, pending = self.start_waiting()
        self.life.stop(self.run.owner, self.run.run_id, "stop")
        old_history = self.repo.get(old_item.key)
        result = self.runner.action(self.run, service, request(old_item))
        self.assertEqual("STOPPED", result["status"])
        result = self.runner.invoke(self.run, graph, Command(resume={pending.id: {"controlRequestId": "old"}}))
        self.assertEqual("STOPPED", result["status"])
        self.assertEqual([], self.executor.calls)
        with self.assertRaises(RunStoppedControl):
            service.continuation(old_item, "old")
        self.runs.forbid_run_read.add(self.run.run_id)
        self.runs.forbid_fact_read.add(self.run.run_id)
        old_get = self.repo.get
        old_for_run, old_for_node = self.repo.for_run, self.repo.for_node
        def no_old_get(key, owner=None):
            if key[0] == self.run.run_id:
                raise AssertionError("old interaction read")
            return old_get(key, owner)
        def no_old_run(owner, run_id):
            if run_id == self.run.run_id:
                raise AssertionError("old business results read")
            return old_for_run(owner, run_id)
        def no_old_node(owner, run_id, node_id):
            if run_id == self.run.run_id:
                raise AssertionError("old node results read")
            return old_for_node(owner, run_id, node_id)
        self.repo.get, self.repo.for_run, self.repo.for_node = no_old_get, no_old_run, no_old_node
        def factory(run, _):
            return self.assemble(run), {"messages": [{
                "role": "user", "content": json.loads(run.initial_inputs_json)["instruction"],
            }]}
        fresh_runner = ControlledRunRunner(self.life, factory, lambda *_: self.config.current)
        fresh = fresh_runner.start(
            self.run.owner, "restart", self.run.definition_key, {"instruction": "Fresh request"},
            self.run.entry_node_id, stopped_run_id=self.run.run_id,
        )
        self.assertNotEqual(self.run.run_id, fresh["runId"])
        self.assertNotEqual(self.run.thread_id, fresh["threadId"])
        new_items = [i for i in self.repo.items.values() if i.key[0] == fresh["runId"]]
        self.assertEqual(1, len(new_items))
        self.assertNotEqual(old_item.interaction_id, new_items[0].interaction_id)
        new_run = self.life.read(self.run.owner, fresh["runId"])
        result = fresh_runner.action(new_run, self.built[fresh["runId"]][1], request(new_items[0]))
        self.assertTrue(result.interaction_completed)
        self.assertEqual(1, len(self.executor.calls))
        self.assertEqual(old_history, self.repo.items[old_item.key])

    def test_mismatched_continuation_binding_rejects_before_business_executor(self):
        graph, service, item, _ = self.start_waiting()
        _, other_life, _ = fixture()
        invalid = (
            LangGraphContinuation(graph),
            LangGraphContinuation(graph.graph, lifecycle=self.life),
            LangGraphContinuation(graph, lifecycle=other_life),
            LangGraphContinuation(RunGraphBinding(graph.graph, other_life), lifecycle=self.life),
        )
        for continuation in invalid:
            with self.subTest(continuation=continuation):
                service.continuation = continuation
                with self.assertRaisesRegex(ActionRejected, "CONTROLLED_CONTINUATION_BINDING_REQUIRED"):
                    self.runner.action(self.run, service, request(item))
                self.assertEqual([], self.executor.calls)
                self.assertEqual((), self.repo.get(item.key).attempts)
