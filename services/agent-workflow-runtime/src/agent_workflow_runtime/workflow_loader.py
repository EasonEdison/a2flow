"""Compile the bounded sequential MVP workflow without scenario logic in core."""

from hashlib import sha256
import json

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, MessagesState, StateGraph

from .models import ActionRejected, json_copy
from .native_control import RunGraphBinding

NODE_RESULT_PREFIX = "workflow-node:"
CONTEXT_PREFIX = "Trusted workflow predecessor context:\n"


def node_operation_id(run_id, node_id):
    return "mvp08-node:" + sha256(f"{run_id}\0{node_id}".encode()).hexdigest()


class NodeBoundary:
    """Keep one NODE fact open across a native child-graph interrupt."""

    def __init__(self, run, lifecycle, views, node_id, predecessor_ids, context_loader):
        self.run, self.lifecycle, self.views = run, lifecycle, views
        self.node_id = node_id
        self.predecessor_ids = tuple(predecessor_ids)
        self.context_loader = context_loader
        self.operation_id = node_operation_id(run.run_id, node_id)

    def before(self, state):
        self.lifecycle.admit_idempotent(
            self.run.owner, self.run.run_id, self.node_id, "NODE", self.operation_id)
        self.views.node(self.run.owner, self.run.run_id, self.node_id, "RUNNING")
        messages = state.get("messages", ())
        task = messages[0] if messages else None
        if (not isinstance(task, HumanMessage) or type(task.content) is not str
                or not task.content):
            raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
        finals = {}
        for message in messages[1:]:
            name = getattr(message, "name", None)
            if (not isinstance(message, AIMessage) or message.tool_calls
                    or type(message.content) is not str or not message.content
                    or type(name) is not str or not name.startswith(NODE_RESULT_PREFIX)):
                raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
            previous_id = name[len(NODE_RESULT_PREFIX):]
            if previous_id in finals:
                raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
            finals[previous_id] = message.content
        if set(finals) != set(self.predecessor_ids):
            raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
        permitted = [HumanMessage(content=task.content)]
        if self.predecessor_ids:
            confirmations = self.context_loader(self.predecessor_ids)
            if type(confirmations) is not list:
                raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
            payload = json_copy({
                "predecessors": [{
                    "nodeId": node_id, "status": "SUCCEEDED",
                    "finalOutput": finals[node_id],
                } for node_id in self.predecessor_ids],
                "confirmations": confirmations,
            })
            permitted.append(HumanMessage(
                content=CONTEXT_PREFIX + json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ),
            ))
        return {"messages": permitted}

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
        return {"messages": [AIMessage(
            content=message.content, name=NODE_RESULT_PREFIX + self.node_id,
        )]}


def compose_workflow(
    run, lifecycle, definition, agents, views, context_loader, checkpointer,
):
    """Compose a bounded sequential asset workflow with native subgraph continuation."""

    nodes = definition.get("nodes") if type(definition) is dict else None
    if (type(nodes) is not list or not 2 <= len(nodes) <= 8
            or definition.get("entryNodeId") != nodes[0].get("nodeId")
            or definition.get("entryNodeId") != run.entry_node_id
            or len({node.get("nodeId") for node in nodes}) != len(nodes)
            or set(agents) != {node.get("nodeId") for node in nodes}):
        raise ActionRejected("UNSUPPORTED_WORKFLOW_DEFINITION")
    if not callable(context_loader):
        raise ActionRejected("WORKFLOW_CONTEXT_LOADER_REQUIRED")
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
    predecessor_ids = []
    for node in nodes:
        node_id = node["nodeId"]
        boundary = NodeBoundary(
            run, lifecycle, views, node_id, predecessor_ids, context_loader,
        )
        sequence = (
            RunnableLambda(boundary.before)
            | agents[node_id].graph
            | RunnableLambda(boundary.after)
        )
        builder.add_node(node_id, sequence)
        predecessor_ids.append(node_id)
    builder.add_edge(START, nodes[0]["nodeId"])
    for before, after in zip(nodes, nodes[1:]):
        builder.add_edge(before["nodeId"], after["nodeId"])
    builder.add_edge(nodes[-1]["nodeId"], END)
    return RunGraphBinding(builder.compile(checkpointer=checkpointer), lifecycle, progress)
