"""Trusted dependency assembly for the private MVP08 host."""

import asyncio
from contextlib import asynccontextmanager, contextmanager
import json

from a2flow_asset_store import AssetReader, PostgresAssetRepository
from langgraph.checkpoint.postgres import PostgresSaver

from .actions import ActionService
from .assembly import build_engine
from .asset_adapters import RuntimeAssets
from .langgraph_adapter import LangGraphContinuation
from .lifecycle import RunLifecycle
from .models import ActionRejected
from .mvp_host import create_mvp_app
from .mvp_tools import build_tools, validators
from .native_control import ControlledRunRunner
from .postgres import PostgresInteractionRepository
from .postgres_lifecycle import PostgresRunRepository
from .postgres_progress import PostgresProgress
from .postgres_projection import PostgresProjection
from .progress_writer import ProgressWriter
from .service import ExecutionSession, RuntimeService, require_owner
from .ui_projection import PostgresMvpView
from .workflow_loader import compose_workflow

WORKFLOW_CURSOR = "mvp08-workflow:"


def validate_workflow_inputs(value):
    if (type(value) is not dict or set(value) != {"requirement"}
            or type(value["requirement"]) is not str
            or not 1 <= len(value["requirement"]) <= 2000):
        raise ActionRejected("INVALID_SERVICE_INPUT")
    return value


def confirmed_context(repository, run, node_ids):
    """Read only saved, consumed Action results for completed predecessor nodes."""
    if (type(node_ids) not in (tuple, list)
            or any(type(node_id) is not str or not node_id for node_id in node_ids)):
        raise ActionRejected("PREDECESSOR_CONTEXT_UNAVAILABLE")
    results = []
    with repository.scope(run.owner, run.run_id):
        for node_id in node_ids:
            result_count = len(results)
            items = sorted(
                repository.for_node(run.owner, run.run_id, node_id),
                key=lambda item: item.interaction_id,
            )
            for item in items:
                if (item.phase != "COMPLETED" or not item.resume_consumed
                        or item.completion_request_id is None or item.display_json is None):
                    raise ActionRejected("PREDECESSOR_CONTEXT_UNAVAILABLE")
                attempts = [attempt for attempt in item.attempts
                            if attempt.request.control_request_id
                            == item.completion_request_id]
                if (len(attempts) != 1 or attempts[0].status != "EXECUTED"
                        or not attempts[0].business_success
                        or not attempts[0].interaction_completed
                        or attempts[0].result_json is None):
                    raise ActionRejected("PREDECESSOR_CONTEXT_UNAVAILABLE")
                try:
                    result = json.loads(attempts[0].result_json)
                    card = json.loads(item.display_json)
                    selected_id = result["selectedOptionId"]
                    options = card["data"]["options"]
                    selected = [option for option in options
                                if option["value"] == selected_id]
                except (KeyError, TypeError, ValueError, RecursionError):
                    raise ActionRejected("PREDECESSOR_CONTEXT_UNAVAILABLE") from None
                if len(selected) != 1:
                    raise ActionRejected("PREDECESSOR_CONTEXT_UNAVAILABLE")
                results.append({
                    "nodeId": node_id, "interactionId": item.interaction_id,
                    "applicationKey": item.application_key,
                    "actionName": attempts[0].request.action_name,
                    "result": result, "selectedOption": selected[0],
                })
            if len(results) == result_count:
                raise ActionRejected("PREDECESSOR_CONTEXT_UNAVAILABLE")
    return json.loads(json.dumps(results, ensure_ascii=False, allow_nan=False))


def _close_model(model):
    client = getattr(model, "client", None)
    if callable(getattr(client, "close", None)):
        client.close()
    async_client = getattr(model, "async_client", None)
    close = getattr(async_client, "close", None)
    if callable(close):
        result = close()
        if hasattr(result, "__await__"):
            asyncio.run(result)


class MvpRuntimeHost:
    """One environment-bound host; browser input cannot select owner or assets."""

    def __init__(
        self, *, conninfo, database, environment, namespace, bundle_validator,
        application_validator, operation_specs, model_factory, identity_resolver,
        model_reference="deepseek-v4-flash", static_directory=None,
        checkpointer_factory=None, unexpected_error_observer=None,
        application_data_validator=None, event_sink=None,
        personal_memory=None,
    ):
        if not callable(identity_resolver):
            raise ValueError("VERIFIED_IDENTITY_RESOLVER_REQUIRED")
        if not callable(application_validator):
            raise ValueError("APPLICATION_VALIDATOR_REQUIRED")
        self.environment = environment
        self.identity_resolver = identity_resolver
        self.application_validator = application_validator
        self.operation_specs = dict(operation_specs)
        self.application_data_validator = application_data_validator
        self.model_factory = model_factory
        self.model_reference = model_reference
        self.personal_memory = personal_memory
        self.static_directory = static_directory
        self.unexpected_error_observer = unexpected_error_observer
        self._checkpointer_factory = checkpointer_factory or (
            lambda: PostgresSaver.from_conn_string(conninfo)
        )

        self.asset_repository = PostgresAssetRepository(
            conninfo, environment=environment, database=database,
            validator=bundle_validator,
        )
        self.reader = AssetReader(self.asset_repository, namespace)
        self.run_repository = PostgresRunRepository(conninfo)
        self.lifecycle = RunLifecycle(self.run_repository, event_sink=event_sink)
        self.interactions = PostgresInteractionRepository(conninfo)
        self.projection = PostgresProjection(conninfo)
        self.progress_repository = PostgresProgress(conninfo)
        self.progress = ProgressWriter(self.progress_repository)
        self.views = PostgresMvpView(conninfo)

        self.service = RuntimeService(
            self.lifecycle, self.projection, self.execution_session,
            self.resolve_entry, progress=self.progress_repository,
            validate_inputs=self.validate_inputs,
        )

    def _owner(self, scope):
        owner = require_owner(self.identity_resolver(scope))
        if owner.environment != self.environment:
            raise ActionRejected("TRUSTED_CONTEXT_REQUIRED")
        return owner

    def validate_inputs(self, owner, definition_key, inputs):
        validate_workflow_inputs(inputs)
        self.reader.resolve_workflow(definition_key, owner)

    def resolve_entry(self, owner, definition_key):
        return self.reader.resolve_workflow(definition_key, owner).definition["entryNodeId"]

    def workflow_catalog(self, owner, *, after=None, limit=20):
        rows = sorted(self.reader.list_workflows(owner), key=lambda item: item["definitionKey"])
        keys = [item["definitionKey"] for item in rows]
        start = 0
        if after is not None:
            if not after.startswith(WORKFLOW_CURSOR) or after[len(WORKFLOW_CURSOR):] not in keys:
                raise ActionRejected("INVALID_VIEW_CURSOR")
            start = keys.index(after[len(WORKFLOW_CURSOR):]) + 1
        page = rows[start:start + limit]
        more = start + limit < len(rows)
        return {
            "items": page,
            "nextCursor": WORKFLOW_CURSOR + page[-1]["definitionKey"] if more and page else None,
        }

    def _system_prompt(self, node, required_tool_names):
        required = ", ".join(required_tool_names)
        return (
            "This is one compiled workflow node. First call use_skill with exactly "
            f"skillKey={node['skillKey']!r}. Follow that Skill and use only the "
            "Tools exposed to this node. Before producing any terminal text, the "
            f"Finalizer requires these Tools to have returned successfully: {required}. "
            "Do not claim confirmation before the "
            "interactive Tool returns a saved successful Action result."
        )

    @contextmanager
    def execution_session(self, owner):
        require_owner(owner)
        models = []
        built = {}
        with self._checkpointer_factory() as saver:
            def graph_factory(run, lifecycle):
                resolved = self.reader.resolve_workflow(run.definition_key, run.owner)
                definition = resolved.definition
                configuration = RuntimeAssets(
                    self.reader, run, self.operation_specs, definition,
                )
                service = ActionService(
                    self.interactions, configuration, configuration.executor, None,
                    lifecycle=lifecycle,
                )
                agents = {}
                available_validators = validators()
                for node in definition["nodes"]:
                    assets = RuntimeAssets(
                        self.reader, run, self.operation_specs, definition,
                        bound_node_id=node["nodeId"],
                    )
                    all_tools = build_tools(
                        assets, service, self.application_validator, self.application_data_validator,
                    )
                    material = self.reader.load_skill(
                        node["skillKey"], run.context(node["nodeId"]),
                    )
                    required = tuple(dict.fromkeys(("use_skill", *material.required_tool_names)))
                    by_name = {item.name: item for item in all_tools}
                    if not required or any(name not in by_name for name in required):
                        raise ActionRejected("SKILL_TOOL_BINDING_MISMATCH")
                    model = self.model_factory.create(self.model_reference, run.owner)
                    models.append(model)
                    agents[node["nodeId"]] = build_engine(
                        model, [by_name[name] for name in required],
                        {name: available_validators[name] for name in required},
                        required, harness_profile_key=model.configuration.harness_profile_key,
                        terminal_guard=service.assert_finalizable,
                        run_lifecycle=lifecycle, progress=self.progress,
                        node_context=run.context(node["nodeId"]),
                        system_prompt=self._system_prompt(node, required),
                        personal_memory=self.personal_memory,
                    )
                context_loader = lambda node_ids: confirmed_context(
                    self.interactions, run, node_ids,
                )
                graph = compose_workflow(
                    run, lifecycle, definition, agents, self.views, context_loader, saver,
                )
                service.continuation = LangGraphContinuation(graph, lifecycle=lifecycle)
                built[run.run_id] = service
                inputs = validate_workflow_inputs(json.loads(run.initial_inputs_json))
                return graph, {"messages": [{
                    "role": "user", "content": inputs["requirement"],
                }]}

            runner = ControlledRunRunner(
                self.lifecycle, graph_factory,
                lambda current_owner, key: self.reader.versions(current_owner, key),
            )

            def action_service(run):
                if run.run_id not in built:
                    graph_factory(run, self.lifecycle)
                return built[run.run_id]

            try:
                yield ExecutionSession(runner, action_service)
            finally:
                for model in reversed(models):
                    _close_model(model)

    @asynccontextmanager
    async def lifespan(self, app):
        del app
        self.asset_repository.setup()
        self.run_repository.setup()
        self.interactions.setup()
        self.progress_repository.setup()
        self.views.setup()
        with self._checkpointer_factory() as saver:
            saver.setup()
        self.progress.start()
        try:
            yield
        finally:
            if not self.progress.shutdown():
                raise RuntimeError("PROGRESS_WRITER_SHUTDOWN_UNCONFIRMED")

    def create_app(self):
        return create_mvp_app(
            self.service, self.views, self.workflow_catalog, self._owner,
            lifespan=self.lifespan, static_directory=self.static_directory,
            unexpected_error_observer=self.unexpected_error_observer,
        )
