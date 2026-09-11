"""Compile the bounded sequential MVP workflow without scenario logic in core."""

from hashlib import sha256

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, MessagesState, StateGraph

from .models import ActionRejected
from .native_control import RunGraphBinding


def node_operation_id(run_id, node_id):
    return "mvp08-node:" + sha256(f"{run_id}\0{node_id}".encode()).hexdigest()


class NodeBoundary:
    """Keep one NODE fact open across a native child-graph interrupt."""

    def __init__(self, run, lifecycle, views, node_id):
        self.run, self.lifecycle, self.views = run, lifecycle, views
        self.node_id = node_id
        self.operation_id = node_operation_id(run.run_id, node_id)

    def before(self, state):
        self.lifecycle.admit_idempotent(
            self.run.owner, self.run.run_id, self.node_id, "NODE", self.operation_id)
        self.views.node(self.run.owner, self.run.run_id, self.node_id, "RUNNING")
        return state

    def after(self, state):
        messages = state.get("messages", ())
        message = messages[-1] if messages else None
        if (not isinstance(message, AIMessage) or message.tool_calls
                or type(message.content) is not str or not message.content):
            raise ActionRejected("MODEL_TEXT_UNAVAILABLE")
        self.lifecycle.finish(
            self.run.owner, self.run.run_id, self.operation_id,
            {"output": message.content},
        )
        self.lifecycle.assert_active(self.run.owner, self.run.run_id)
        self.views.complete(
            self.run.owner, self.run.run_id, self.node_id, message.content,
        )
        return state


def compose_workflow(run, lifecycle, definition, agents, views, checkpointer):
    """Compose the strict two-node asset subset with native subgraph continuation."""

    nodes = definition.get("nodes") if type(definition) is dict else None
    if (type(nodes) is not list or len(nodes) != 2
            or definition.get("entryNodeId") != nodes[0].get("nodeId")
            or definition.get("entryNodeId") != run.entry_node_id
            or len({node.get("nodeId") for node in nodes}) != 2
            or set(agents) != {node.get("nodeId") for node in nodes}):
        raise ActionRejected("UNSUPPORTED_WORKFLOW_DEFINITION")
    progress = None
    for node in nodes:
        if set(node) != {"nodeId", "skillKey"}:
            raise ActionRejected("UNSUPPORTED_WORKFLOW_DEFINITION")
        agent = agents[node["nodeId"]]
        if not isinstance(agent, RunGraphBinding) or agent.lifecycle is not lifecycle:
            raise ActionRejected("CONTROLLED_GRAPH_BINDING_REQUIRED")
        if progress is None:
            progress = agent.progress
        elif agent.progress is not progress:
            raise ActionRejected("PROGRESS_BINDING_MISMATCH")

    views.ensure(run, definition, run.versions)
    builder = StateGraph(MessagesState, context_schema=type(run.context()))
    for node in nodes:
        node_id = node["nodeId"]
        boundary = NodeBoundary(run, lifecycle, views, node_id)
        sequence = (
            RunnableLambda(boundary.before)
            | agents[node_id].graph
            | RunnableLambda(boundary.after)
        )
        builder.add_node(node_id, sequence)
    builder.add_edge(START, nodes[0]["nodeId"])
    builder.add_edge(nodes[0]["nodeId"], nodes[1]["nodeId"])
    builder.add_edge(nodes[1]["nodeId"], END)
    return RunGraphBinding(builder.compile(checkpointer=checkpointer), lifecycle, progress)
