"""Trusted Deep Agent assembly using public SDK hooks and injected Tools."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from deepagents.backends import StateBackend

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from .finalizer import RequiredToolFinalizerAdmission
from .tool_admission import (
    ClosedModelArgsAdmission,
    ModelArgsValidator,
)


# 默认屏蔽宿主文件、命令执行及委派工具，模型只能使用本次显式注入的工具。
IMPLICIT_DEEP_AGENT_TOOLS = frozenset({
    "delete", "edit_file", "execute", "glob", "grep", "ls",
    "read_file", "task", "write_file",
})


def build_agent(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    validators: Mapping[str, ModelArgsValidator],
    *,
    harness_profile_key: str,
    middleware: Sequence[AgentMiddleware] = (),
    checkpointer: Any = None,
    context_schema: type[Any] | None = None,
    system_prompt: str | None = None,
    control_middleware: Sequence[AgentMiddleware] = (),
    session_result_backend: StateBackend | None = None,
) -> CompiledStateGraph:
    """Shared SDK construction; scope-specific lifecycle stays in middleware.

    No native Skill directory, filesystem execution or delegated agents are
    enabled here. Conversation mode does not require a tool for a greeting.
    """
    # 会话中间结果只接受 SDK 的状态后端，避免把结果读取扩展为宿主文件访问。
    if session_result_backend is not None and type(session_result_backend) is not StateBackend:
        raise ValueError("SESSION_RESULTS_REQUIRE_STATE_BACKEND")
    # 仅启用会话结果后端时放开 read_file，其实际可读范围仍由调用方中间件限制。
    excluded_tools = IMPLICIT_DEEP_AGENT_TOOLS
    if session_result_backend is not None:
        excluded_tools = excluded_tools - {"read_file"}
    # 注册受限的 SDK 工具配置，同时关闭默认通用子 Agent。
    register_harness_profile(
        harness_profile_key,
        HarnessProfile(
            excluded_tools=excluded_tools,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    # 模型与工具的循环由 Deep Agents 创建；这里仅注入工具、持久化和中间件。
    return create_deep_agent(
        model=model, tools=list(tools), checkpointer=checkpointer,
        backend=session_result_backend,
        context_schema=context_schema,
        system_prompt=system_prompt or (
            "Use authorized Skills and operations only through Runtime-owned Tools."
        ),
        # 先应用运行控制，再校验模型原始参数，随后执行场景中间件。
        middleware=[*control_middleware, ClosedModelArgsAdmission(validators),
                    *middleware],
    )


def build_engine(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    validators: Mapping[str, ModelArgsValidator],
    required_tool_names: Sequence[str],
    *,
    harness_profile_key: str,
    checkpointer: Any = None,
    terminal_guard: Callable[[Any], None] | None = None,
    run_lifecycle: Any = None,
    progress: Any = None,
    node_context: Any = None,
    system_prompt: str | None = None,
    personal_memory: Any = None,
    tool_alternatives: Mapping[str, Sequence[str]] | None = None,
    model_middleware: Sequence[AgentMiddleware] = (),
    allow_tool_free: bool = False,
) -> CompiledStateGraph:
    """Build from trusted backend inputs, never request-selected Python internals.

    The service requires run_lifecycle and verifies RunGraphBinding. The optional
    unbound mode is retained only for standalone admission/Finalizer experiments.
    """

    # 纯文本模式不能同时声明工具权限，防止配置含义互相矛盾。
    if allow_tool_free and (tools or validators or required_tool_names or tool_alternatives):
        raise ValueError("Tool-free execution cannot declare Tool permissions")
    # 节点上下文必须绑定生命周期；个人记忆也必须具备可信节点身份。
    if node_context is not None and run_lifecycle is None:
        raise ValueError("Node context requires run lifecycle")
    if personal_memory is not None and node_context is None:
        raise ValueError("Personal memory requires a trusted node context")
    # 提示词必须非空；带交互动作的工具还必须提供结束门禁。
    if system_prompt is not None and (not isinstance(system_prompt, str) or not system_prompt):
        raise ValueError("System prompt must be a nonempty string")
    if terminal_guard is None and any(
        (item.metadata or {}).get("requires_action_guard") for item in tools
    ):
        raise ValueError("Interactive Action Tools require a terminal guard")
    # 工作流模式按需组装节点身份绑定和运行准入，普通会话不强行套用生命周期。
    control_middleware = []
    if run_lifecycle is not None:
        from agent_workflow_runtime.native_control import (
            BoundNodeMiddleware, RunAdmissionMiddleware,
        )
        # 节点身份先绑定到执行上下文，再由运行门禁检查是否仍允许推进。
        control_middleware = (
            [BoundNodeMiddleware(node_context)] if node_context is not None else []
        )
        control_middleware.append(RunAdmissionMiddleware(run_lifecycle, node_context))
    # 进度观察与个人记忆分别作为中间件注入，不在装配层新增执行循环。
    observation_middleware = []
    memory_middleware = []
    # 个人记忆使用已认证的用户上下文，不能从模型参数选择其他用户。
    if personal_memory is not None:
        from .personal_memory import PersonalMemoryMiddleware
        memory_middleware = [PersonalMemoryMiddleware(
            personal_memory, node_context.trusted_context,
        )]
    # 仅在宿主提供进度组件时启用观察，具体事实仍由执行边界采集。
    if progress is not None:
        from .progress_observer import ProgressMiddleware
        observation_middleware = [ProgressMiddleware(node_context)]
    # 复用唯一的 Agent 构建入口，所有场景沿用同一套参数校验和 SDK 行为。
    graph = build_agent(
        model=model,
        checkpointer=checkpointer,
        tools=list(tools),
        validators=validators,
        harness_profile_key=harness_profile_key,
        control_middleware=control_middleware,
        system_prompt=system_prompt or (
            "Use authorized Skills and operations only through Runtime-owned Tools."
        ),
        middleware=[
            *observation_middleware,
            *memory_middleware,
            *model_middleware,
            # 最终回复必须具备本次实际工具成功证据，并通过交互完成检查。
            RequiredToolFinalizerAdmission(
                required_tool_names, terminal_guard, lifecycle=run_lifecycle,
                node_context=node_context,
                tool_alternatives=tool_alternatives, allow_empty=allow_tool_free,
            ),
        ],
    )

    if run_lifecycle is not None:
        from agent_workflow_runtime.native_control import RunGraphBinding
        # 返回显式绑定的图，使执行入口能够验证图与生命周期属于同一装配。
        return RunGraphBinding(graph, run_lifecycle, progress)
    return graph
