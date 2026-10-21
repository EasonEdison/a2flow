"""HTTP client for the Runtime control interface (v1 proxy, stdlib only).

The b-side service never imports Runtime internals; it talks to the reviewed
control routes. Delivery is proxied verbatim; ownership is enforced by the
b-side run_ownership table before any call is forwarded.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Protocol
from skillweave_contracts.user_id import require_user_id, user_id_to_wire

from .errors import RemoteRuntimeError

# 只对已识别的执行错误映射 HTTP 状态, 未知远端失败保持网关错误。
_STATUS_BY_CODE = {
    "CAPACITY_EXHAUSTED": 503,
    "INVALID_INPUT": 400,
    "TEMPORARY_INTERACTION_SUBMISSION_INVALID": 400,
    "INVALID_SERVICE_INPUT": 400,
    "CONTROL_NOT_FOUND": 404,
    "RUN_NOT_FOUND": 404,
    "RESTART_SOURCE_OUTSIDE_THIS_SLICE": 409,
    "RUN_STOPPED": 409,
}


# 产品侧依赖控制协议, 不导入执行服务内部的图或状态仓库。
class RuntimeClient(Protocol):
    def for_user(self, user_id: int, environment: str) -> "RuntimeClient": ...

    def start(self, control_request_id: str, definition_key: str,
              inputs: dict) -> dict: ...

    def control(self, control_id: str) -> dict: ...

    def stop(self, run_id: str, control_request_id: str) -> dict: ...

    def action(self, run_id: str, node_id: str, payload: dict) -> dict: ...

    def view(self, run_id: str) -> dict: ...

    def cards(self, run_id: str) -> dict[str, object]: ...

    # 卡片提交与卡片恢复分成独立协议, 提交完成不直接冒充节点恢复完成。
    def card_action(
        self, run_id: str, card_id: str, payload: dict[str, object],
    ) -> dict[str, object]: ...

    def resume_card(
        self, run_id: str, card_id: str, payload: dict[str, object],
    ) -> dict[str, object]: ...

    def resume_status(
        self, run_id: str, card_id: str, query: dict[str, str],
    ) -> dict[str, object]: ...

    def action_stream(self, run_id: str, node_id: str,
                      payload: dict) -> Iterator[str]: ...

    def surface_stream(self, run_id: str) -> Iterator[str]: ...

    # 进度目录、历史和流分开读取, 共用真实运行与执行实例身份。
    def progress_catalog(self, run_id: str, query: list[tuple[str, str]]) -> dict[str, object]: ...

    def progress_history(
        self, run_id: str, node_id: str, execution_id: str, query: list[tuple[str, str]],
    ) -> dict[str, object]: ...

    def progress_stream(
        self, run_id: str, node_id: str, execution_id: str,
        query: list[tuple[str, str]], last_event_id: str | None,
    ) -> Iterator[str]: ...


# HTTP 客户端负责序列化和错误转换, 不承担业务自动重试。
class HttpRuntimeClient:
    """Minimal JSON client over the reviewed runtime control interface."""

    def __init__(self, base_url: str, timeout: float = 10.0, *,
                 user_id: int | None = None, environment: str | None = None):
        # 基础地址与超时固定保存; 用户绑定时另建客户端, 避免并发串用身份。
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._user_id = require_user_id(user_id) if user_id is not None else None
        self._environment = environment

    # 每次产生用户专属客户端, 可信身份不能修改共享实例。
    def for_user(self, user_id: int, environment: str) -> "HttpRuntimeClient":
        # A new client per invocation: never mutate a shared client's identity.
        require_user_id(user_id)
        # 环境只允许 PRT 或 ONLINE, 非法环境不能进入内部请求。
        if environment not in {"PRT", "ONLINE"}:
            raise ValueError("TRUSTED_CONTEXT_REQUIRED")
        return HttpRuntimeClient(self._base, self._timeout,
                                 user_id=user_id, environment=environment)

    # 所有内部请求都必须显式具备用户和环境, 缺少上下文立即拒绝。
    def _identify(self, request):
        if self._user_id is None or self._environment is None:
            raise ValueError("TRUSTED_CONTEXT_REQUIRED")
        # 身份头由服务端绑定值生成, 不能直接转发浏览器伪造头。
        request.add_header("X-A2Flow-User-Id", user_id_to_wire(self._user_id))
        request.add_header("X-A2Flow-Environment", self._environment)

    # 普通调用按 JSON 协议编码, 只有请求体存在时设置 JSON 内容类型。
    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self._base + path, data=data, method=method)
        # 发出请求前补齐可信身份, 不依赖 URL 或业务参数承载用户信息。
        self._identify(request)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request,
                                        timeout=self._timeout) as response:
                return json.load(response)
        # 远端拒绝只提取协议错误码, 不向产品层透传完整错误响应。
        except urllib.error.HTTPError as error:
            code = "RUNTIME_REJECTED"
            try:
                payload = json.load(error)
                code = payload.get("error", {}).get("code", code)
            except Exception:
                pass
            # 已知错误映射到稳定状态, 通信或超时错误统一标记不可达。
            status = _STATUS_BY_CODE.get(code, 502)
            raise RemoteRuntimeError(code, status) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RemoteRuntimeError("RUNTIME_UNREACHABLE", 502) from None

    # 启动同时传递稳定控制请求号、资产键与结构化入参。
    def start(self, control_request_id: str, definition_key: str,
              inputs: dict) -> dict:
        return self._request("POST", "/runtime/runs", {
            "controlRequestId": control_request_id,
            "definitionKey": definition_key,
            "inputs": inputs,
        })

    # 单独编码路径标识, 控制查询不会发起新的执行。
    def control(self, control_id: str) -> dict:
        quoted = urllib.parse.quote(control_id, safe="")
        return self._request("GET", "/runtime/controls/" + quoted)

    # 运行视图读取生命周期和结果, 区别于只表示提交事实的控制回执。
    def view(self, run_id: str) -> dict:
        quoted = urllib.parse.quote(run_id, safe="")
        return self._request("GET", "/runtime/runs/" + quoted + "/view")

    # 卡片查询读取运行当前权威交互状态, 不由页面历史猜测。
    def cards(self, run_id: str) -> dict[str, object]:
        return self._request(
            "GET", "/runtime/runs/" + urllib.parse.quote(run_id, safe="") + "/cards",
        )

    # 动作路径中的运行和卡片标识分别编码, 负载保持原提交协议。
    def card_action(
        self, run_id: str, card_id: str, payload: dict[str, object],
    ) -> dict[str, object]:
        return self._request(
            "POST", "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/cards/" + urllib.parse.quote(card_id, safe="") + "/actions", payload,
        )

    # 提交后的节点恢复使用独立入口, 幂等身份由恢复负载提供。
    def resume_card(
        self, run_id: str, card_id: str, payload: dict[str, object],
    ) -> dict[str, object]:
        return self._request(
            "POST", "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/cards/" + urllib.parse.quote(card_id, safe="") + "/resume", payload,
        )

    # 恢复状态为只读查询, 参数使用标准 URL 编码而非字符串拼接。
    def resume_status(
        self, run_id: str, card_id: str, query: dict[str, str],
    ) -> dict[str, object]:
        return self._request(
            "GET", "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/cards/" + urllib.parse.quote(card_id, safe="") + "/resume-status?"
            + urllib.parse.urlencode(query),
        )

    # 旧交互流发送节点动作后原样转发 SSE, 不合成执行进度。
    def action_stream(self, run_id: str, node_id: str, payload: dict) -> Iterator[str]:
        """POST the action and yield the runtime SSE chunks verbatim."""
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._base + "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/nodes/" + urllib.parse.quote(node_id, safe="") + "/actions",
            data=data, method="POST")
        request.add_header("Accept", "text/event-stream")
        request.add_header("Content-Type", "application/json")
        return self._stream(request)

    # 展示流订阅快照及后续更新, 订阅本身不启动运行。
    def surface_stream(self, run_id: str) -> Iterator[str]:
        """Subscribe to snapshot + surface updates for one run."""
        request = urllib.request.Request(
            self._base + "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/surface")
        request.add_header("Accept", "text/event-stream")
        return self._stream(request)

    # 集中构造运行、节点和执行实例路径, 各部分独立转义。
    @staticmethod
    def _progress_path(run_id: str, node_id: str, execution_id: str) -> str:
        quote = urllib.parse.quote
        return ("/runtime/runs/" + quote(run_id, safe="")
                + "/nodes/" + quote(node_id, safe="")
                + "/executions/" + quote(execution_id, safe=""))

    # 查询参数保留键值对列表, 重复字段仍交原生接口拒绝。
    def progress_catalog(self, run_id: str, query: list[tuple[str, str]]) -> dict[str, object]:
        return self._request(
            "GET", "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/progress?" + urllib.parse.urlencode(query),
        )

    def progress_history(
        self, run_id: str, node_id: str, execution_id: str, query: list[tuple[str, str]],
    ) -> dict[str, object]:
        return self._request(
            "GET", self._progress_path(run_id, node_id, execution_id)
            + "/history?" + urllib.parse.urlencode(query),
        )

    def progress_stream(
        self, run_id: str, node_id: str, execution_id: str,
        query: list[tuple[str, str]], last_event_id: str | None,
    ) -> Iterator[str]:
        request = urllib.request.Request(
            self._base + self._progress_path(run_id, node_id, execution_id)
            + "/stream?" + urllib.parse.urlencode(query),
        )
        request.add_header("Accept", "text/event-stream")
        # 仅在提供游标时透传 Last-Event-ID, 不自己推算下一个事件号。
        if last_event_id is not None:
            request.add_header("Last-Event-ID", last_event_id)
        return self._stream(request)

    # 连接建立阶段区分远端拒绝与网络不可达, 流消费阶段始终负责关闭响应。
    def _stream(self, request: urllib.request.Request) -> Iterator[str]:
        self._identify(request)
        try:
            response = urllib.request.urlopen(request, timeout=180.0)
        except urllib.error.HTTPError as error:
            self._raise_http_error(error)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RemoteRuntimeError("RUNTIME_UNREACHABLE", 502) from None

        # 逐行解码原生 UTF-8 SSE, 消费结束或异常都会释放连接。
        def chunks():
            try:
                for raw in response:
                    yield raw.decode("utf-8")
            finally:
                response.close()
        return chunks()

    # 流式和普通请求采用相同错误协议, 无法解析的响应不泄露原文。
    def _raise_http_error(self, error):
        code = "RUNTIME_REJECTED"
        try:
            payload = json.load(error)
            code = payload.get("error", {}).get("code", code)
        except Exception:
            pass
        status = _STATUS_BY_CODE.get(code, 502)
        raise RemoteRuntimeError(code, status) from None

    # 停止是新的控制请求, 不能通过关闭浏览器流来替代。
    def stop(self, run_id: str, control_request_id: str) -> dict:
        return self._request(
            "POST",
            "/runtime/runs/" + urllib.parse.quote(run_id, safe="") + "/stop",
            {"controlRequestId": control_request_id})

    # 非流式动作复用同一身份绑定和 JSON 错误转换逻辑。
    def action(self, run_id: str, node_id: str, payload: dict) -> dict:
        return self._request(
            "POST",
            "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/nodes/" + urllib.parse.quote(node_id, safe="") + "/actions",
            payload)
