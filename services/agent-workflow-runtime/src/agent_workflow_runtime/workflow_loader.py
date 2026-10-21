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


# 节点准入 ID 由运行及节点确定，使原生中断恢复能复用同一节点边界事实。
def node_operation_id(run_id, node_id):
    return "mvp08-node:" + sha256(f"{run_id}\0{node_id}".encode()).hexdigest()


class NodeBoundary:
    """Keep one NODE fact open across a native child-graph interrupt."""

    def __init__(self, run, lifecycle, views, node_id, predecessor_ids, context_loader):
        # 边界对象持有可信运行和前驱集合，子 Agent 不自行选择可见的上游范围。
        self.run, self.lifecycle, self.views = run, lifecycle, views
        self.node_id = node_id
        self.predecessor_ids = tuple(predecessor_ids)
        self.context_loader = context_loader
        self.operation_id = node_operation_id(run.run_id, node_id)

    def before(self, state):
        # 节点开始前持久化准入，等待中断期间该 NODE 事实保持打开。
        self.lifecycle.admit_idempotent(
            self.run.owner, self.run.run_id, self.node_id, "NODE", self.operation_id)
        self.views.node(self.run.owner, self.run.run_id, self.node_id, "RUNNING")
        # 工作流首条消息必须是原始任务；后续消息必须是已完成前驱的明确结果。
        messages = state.get("messages", ())
        task = messages[0] if messages else None
        if (not isinstance(task, HumanMessage) or type(task.content) is not str
                or not task.content):
            raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
        # 根据稳定节点结果标记收集前驱，拒绝工具调用残片、空输出或重复节点。
        finals = {}
        for message in messages[1:]:
            name = getattr(message, "name", None)
            if (not isinstance(message, AIMessage) or message.tool_calls
                    or type(message.content) is not str or not message.content
                    or type(name) is not str or not name.startswith(NODE_RESULT_PREFIX)):
                raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
            # 从明确的消息标签提取节点 ID，并校验同节点只出现一个最终结果。
            previous_id = name[len(NODE_RESULT_PREFIX):]
            if previous_id in finals:
                raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
            finals[previous_id] = message.content
        # 前驱身份必须恰好等于定义中的集合，不能混入未授权节点或遗漏已完成步骤。
        if set(finals) != set(self.predecessor_ids):
            raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
        # 子图只接收原始任务及整理后的前驱事实，不继承其他节点全部内部工具消息。
        permitted = [HumanMessage(content=task.content)]
        if self.predecessor_ids:
            confirmations = self.context_loader(self.predecessor_ids)
            if type(confirmations) is not list:
                raise ActionRejected("WORKFLOW_CONTEXT_UNAVAILABLE")
            # 把前驱最终输出和保存的确认事实作为数据封装，供下一节点引用。
            payload = json_copy({
                "predecessors": [{
                    "nodeId": node_id, "status": "SUCCEEDED",
                    "finalOutput": finals[node_id],
                } for node_id in self.predecessor_ids],
                "confirmations": confirmations,
            })
            # 使用固定前缀标明可信前驱上下文，JSON 内容本身不获得额外指令权限。
            permitted.append(HumanMessage(
                content=CONTEXT_PREFIX + json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ),
            ))
        return {"messages": permitted}

    # 子图结束时必须产出无待调用工具的最终 AI 文本，不能把半完成状态传给下游。
    def after(self, state):
        messages = state.get("messages", ())
        message = messages[-1] if messages else None
        if (not isinstance(message, AIMessage) or message.tool_calls
                or type(message.content) is not str or not message.content):
            raise ActionRejected("MODEL_TEXT_UNAVAILABLE")
        # 先关闭节点事实，再检查停止并更新展示；后续展示异常不能重做已完成业务。
        self.lifecycle.finish(
            self.run.owner, self.run.run_id, self.operation_id,
            {"output": message.content},
        )
        self.lifecycle.assert_active(self.run.owner, self.run.run_id)
        # 保存节点可读输出，同时用稳定节点标签构造传给下游的结果消息。
        self.views.complete(
            self.run.owner, self.run.run_id, self.node_id, message.content,
        )
        return {"messages": [AIMessage(
            content=message.content, name=NODE_RESULT_PREFIX + self.node_id,
        )]}


def compose_workflow(
    run, lifecycle, definition, agents, views, context_loader, checkpointer, *, summary_agent=None,
    initialize_view=True,
):
    """Compose a bounded sequential asset workflow with native subgraph continuation."""

    # 当前编译器只接受有界顺序工作流，先校验节点数、入口与节点身份唯一性。
    nodes = definition.get("nodes") if type(definition) is dict else None
    if (type(nodes) is not list or not 1 <= len(nodes) <= 8
            or definition.get("entryNodeId") != nodes[0].get("nodeId")
            or definition.get("entryNodeId") != run.entry_node_id
            or len({node.get("nodeId") for node in nodes}) != len(nodes)
            or set(agents) != {node.get("nodeId") for node in nodes}):
        raise ActionRejected("UNSUPPORTED_WORKFLOW_DEFINITION")
    # 前驱事实加载器必须由宿主显式提供，不能静默使用空上下文替代。
    if not callable(context_loader):
        raise ActionRejected("WORKFLOW_CONTEXT_LOADER_REQUIRED")
    progress = None
    for node in nodes:
        # 业务能力节点与 Skill 节点使用各自固定引用字段，拒绝定义夹带额外执行参数。
        capability = node.get("type") == "BUSINESS_CAPABILITY"
        reference = "abilityKey" if capability else "skillKey"
        allowed = {"nodeId", reference, "displayName", "nodePrompt"}
        if capability:
            allowed.add("type")
        if set(node) - allowed or not {"nodeId", reference} <= set(node):
            raise ActionRejected("UNSUPPORTED_WORKFLOW_DEFINITION")
        # 每个子图必须绑定同一生命周期，进度组件也必须一致。
        agent = agents[node["nodeId"]]
        if not isinstance(agent, RunGraphBinding) or agent.lifecycle is not lifecycle:
            raise ActionRejected("CONTROLLED_GRAPH_BINDING_REQUIRED")
        if progress is None:
            progress = agent.progress
        elif agent.progress is not progress:
            raise ActionRejected("PROGRESS_BINDING_MISMATCH")

    # 最终总结是平台追加的专门节点，需有受控绑定并避免与业务节点重名。
    if "summaryPrompt" in definition:
        if (type(definition["summaryPrompt"]) is not str
                or not definition["summaryPrompt"].strip()
                or len(definition["summaryPrompt"]) > 4096
                or "workflow-summary" in agents
                or not isinstance(summary_agent, RunGraphBinding)
                or summary_agent.lifecycle is not lifecycle
                or summary_agent.progress is not progress):
            raise ActionRejected("INVALID_WORKFLOW_SUMMARY_BINDING")
        # 通过复制定义追加总结，不原地改写调用方保存的工作流资产。
        nodes = [*nodes, {"nodeId": "workflow-summary", "skillKey": "workflow-summary",
                         "displayName": "流程总结"}]
        agents = {**agents, "workflow-summary": summary_agent}
        definition = {**definition, "nodes": nodes}
    elif summary_agent is not None:
        raise ActionRejected("INVALID_WORKFLOW_SUMMARY_BINDING")

    # 可选初始化运行视图；恢复已有运行时由宿主决定是否跳过初始化。
    if initialize_view:
        views.ensure(run, definition, run.versions)
    builder = StateGraph(MessagesState, context_schema=type(run.context()))
    predecessor_ids = []
    # 为每个业务节点组装进入边界、子图执行、离开边界三段流程。
    for node in nodes:
        node_id = node["nodeId"]
        boundary = NodeBoundary(
            run, lifecycle, views, node_id, predecessor_ids, context_loader,
        )
        # 原生子图直接作为 Runnable 组合，检查点中断与恢复仍由 LangGraph 负责。
        sequence = (
            RunnableLambda(boundary.before)
            | agents[node_id].graph
            | RunnableLambda(boundary.after)
        )
        builder.add_node(node_id, sequence)
        predecessor_ids.append(node_id)
    # 按照已验证定义连接顺序边，最后一个节点完成后进入 END。
    builder.add_edge(START, nodes[0]["nodeId"])
    for before, after in zip(nodes, nodes[1:]):
        builder.add_edge(before["nodeId"], after["nodeId"])
    builder.add_edge(nodes[-1]["nodeId"], END)

    def record_failure(error: BaseException) -> None:
        # The sequential composition leaves a NODE permit open across native
        # interrupts. A real graph exception must close that permit as unknown,
        # without converting prior completed nodes/Actions into failed writes.
        # 图真实失败时查找仍在途的节点边界，已完成节点及动作结果不受影响。
        with lifecycle.repository.run_scope(run.owner, run.run_id):
            pending = tuple(fact for fact in lifecycle.repository.operations(
                run.owner, run.run_id)
                if fact.kind == "NODE" and fact.status == "IN_FLIGHT")
        # 关闭未结束节点为 UNCONFIRMED，不把失败误解释成业务从未发生。
        for fact in pending:
            lifecycle.finish(run.owner, run.run_id, fact.operation_id,
                             {"errorType": type(error).__name__}, status="UNCONFIRMED")
            if lifecycle.read(run.owner, run.run_id).status != "STOPPED":
                # 仅把已审查的能力及补参错误码展示为节点摘要，不透传任意异常详情。
                code = error.code if isinstance(error, ActionRejected) else None
                summary = code if isinstance(code, str) and code.startswith(
                    ("WORKFLOW_CAPABILITY_", "WORKFLOW_PARAMETERS_")) else None
                views.node(run.owner, run.run_id, fact.node_id, "UNCONFIRMED", summary)

    # 编译图与检查点、生命周期及失败观察器统一绑定后，交给受控入口执行。
    return RunGraphBinding(
        builder.compile(checkpointer=checkpointer), lifecycle, progress, record_failure,
    )
