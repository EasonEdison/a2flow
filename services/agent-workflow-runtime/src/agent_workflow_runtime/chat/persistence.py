"""PostgreSQL conversation admission around the native LangGraph saver.

The session lock spans the entire worker turn, not the HTTP connection. A
crashed/incomplete turn is blocked instead of automatically replaying tools.
"""

from contextlib import contextmanager
from hashlib import sha256
import json
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from langgraph.checkpoint.postgres import PostgresSaver

from ..service import require_owner


# 会话表记录线程及准入状态；轮次表保存已完成的公开事件，用于修复产品侧消息。
SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_conversations (
    environment text NOT NULL,
    user_id BIGINT NOT NULL,
    conversation_id text NOT NULL,
    thread_id text NOT NULL UNIQUE,
    state text NOT NULL CHECK (state IN ('READY', 'RUNNING', 'FAILED')),
    last_turn_id text,
    PRIMARY KEY (environment, user_id, conversation_id)
);
CREATE TABLE IF NOT EXISTS agent_chat_turns (
    environment text NOT NULL,
    user_id BIGINT NOT NULL,
    conversation_id text NOT NULL,
    turn_id text NOT NULL,
    state text NOT NULL CHECK (state IN ('RUNNING', 'COMPLETED', 'NEEDS_REVIEW')),
    events jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    PRIMARY KEY (environment, user_id, conversation_id, turn_id)
)
"""


class ConversationAdmissionError(Exception):
    pass


class ConversationStore:
    def __init__(self, conninfo):
        self._conninfo = conninfo

    # 初始化运行态表与 SDK 检查点表；该迁移入口不负责创建业务数据。
    def setup(self):
        with psycopg.connect(self._conninfo, autocommit=True,
                             connect_timeout=5) as connection:
            connection.execute(SCHEMA)
            PostgresSaver(connection).setup()

    @staticmethod
    def _identity(owner, conversation_id, turn_id):
        # 先验证可信身份，再构造包含环境、用户、会话的隔离键。
        require_owner(owner)
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError("CONVERSATION_ID_REQUIRED")
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("TURN_ID_REQUIRED")
        identity = (owner.environment, owner.user_id, conversation_id)
        # 将稳定的会话身份映射为有符号 64 位锁键，同一会话各轮共享执行锁。
        lock_key = int.from_bytes(
            sha256(json.dumps(identity).encode()).digest()[:8], "big", signed=True,
        )
        return identity, lock_key

    def inspect_turn(self, owner, conversation_id, turn_id):
        """Inspect facts under the execution lock; never infer safety from age.

        Missing turn evidence is retryable only if the whole conversation has no
        unfinished execution. Legacy completed turns without a replay payload
        remain review-only rather than being presented as new work.
        """
        # 检查与执行使用同一锁域；拿不到锁只能说明忙碌，不能推断上次失败。
        identity, lock_key = self._identity(owner, conversation_id, turn_id)
        with psycopg.connect(self._conninfo, autocommit=True,
                             row_factory=dict_row, connect_timeout=5) as connection:
            # 使用独立数据库会话持锁，避免 HTTP 连接结束导致准入提前释放。
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key,),
            ).fetchone()["acquired"]
            if not acquired:
                return {"status": "BUSY", "events": []}
            try:
                # 优先读取目标轮次的持久化事实，不能仅凭会话当前 READY 判断该轮可重跑。
                turn = connection.execute(
                    "SELECT state,events FROM agent_chat_turns WHERE "
                    "environment=%s AND user_id=%s AND conversation_id=%s AND turn_id=%s",
                    (*identity, turn_id),
                ).fetchone()
                # 有完整完成事件才允许重建展示；未完成或缺证据的轮次统一要求核对。
                if turn:
                    if turn["state"] == "COMPLETED" and turn["events"]:
                        return {"status": "COMPLETED", "events": turn["events"]}
                    return {"status": "NEEDS_REVIEW", "events": []}
                # 兼容已有会话记录：历史失败、执行中或同轮次记录都不能当作新任务。
                conversation = connection.execute(
                    "SELECT state,last_turn_id FROM agent_conversations WHERE "
                    "environment=%s AND user_id=%s AND conversation_id=%s", identity,
                ).fetchone()
                if conversation and (conversation["state"] != "READY"
                                     or conversation["last_turn_id"] == turn_id):
                    return {"status": "NEEDS_REVIEW", "events": []}
                # 有历史轮次时还需确认检查点存在，避免丢失工具上下文后重新执行。
                if conversation and conversation["last_turn_id"] is not None:
                    row = connection.execute(
                        "SELECT thread_id FROM agent_conversations WHERE environment=%s "
                        "AND user_id=%s AND conversation_id=%s", identity,
                    ).fetchone()
                    # 通过 SDK 查询真实检查点；业务表存在不代表 Agent 状态完整。
                    if PostgresSaver(connection).get_tuple({
                        "configurable": {"thread_id": row["thread_id"]},
                    }) is None:
                        return {"status": "NEEDS_REVIEW", "events": []}
                # 只有既无该轮执行事实、又无历史恢复障碍，才声明尚未开始。
                return {"status": "NOT_STARTED", "events": []}
            finally:
                # 无论查询返回哪种状态都释放锁；锁空闲本身不是业务未执行的证据。
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))

    # 会话作用域包住整轮模型和工具执行；正常退出时才提交完成证据。
    @contextmanager
    def session(self, owner, conversation_id, turn_id, *, completion_events=None):
        identity, lock_key = self._identity(owner, conversation_id, turn_id)
        # A dedicated connection keeps this session-level lock through model IO.
        with psycopg.connect(self._conninfo, autocommit=True,
                             row_factory=dict_row, connect_timeout=5) as connection:
            # 非阻塞竞争会话锁，重复执行者立即退出，不在应用中再排一个 Agent 循环。
            locked = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key,),
            ).fetchone()["acquired"]
            if not locked:
                raise ConversationAdmissionError("CONVERSATION_BUSY")
            try:
                # 首次访问分配内部线程标识；请求方不能指定其他会话的检查点线程。
                connection.execute(
                    "INSERT INTO agent_conversations "
                    "(environment,user_id,conversation_id,thread_id,state) "
                    "VALUES (%s,%s,%s,%s,'READY') ON CONFLICT DO NOTHING",
                    (*identity, str(uuid4())),
                )
                # 在持锁状态读取会话准入信息，后续检查与状态切换不会被同域执行者穿插。
                row = connection.execute(
                    "SELECT thread_id,state,last_turn_id FROM agent_conversations "
                    "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                    identity,
                ).fetchone()
                # 检查本轮是否已有记录，完成轮次与未确认轮次都禁止再次进入模型。
                prior = connection.execute(
                    "SELECT state FROM agent_chat_turns WHERE environment=%s "
                    "AND user_id=%s AND conversation_id=%s AND turn_id=%s",
                    (*identity, turn_id),
                ).fetchone()
                # 完成事实直接阻止重复执行；其他旧记录需要人工核对，不能靠超时重置。
                if prior and prior["state"] == "COMPLETED":
                    raise ConversationAdmissionError("TURN_ALREADY_COMPLETED")
                if prior or row["state"] != "READY":
                    raise ConversationAdmissionError("CONVERSATION_REQUIRES_REVIEW")
                if row["last_turn_id"] == turn_id:
                    raise ConversationAdmissionError("TURN_ALREADY_COMPLETED")
                # 复用本轮持锁连接创建检查点适配器，并核对历史线程状态没有遗失。
                saver = PostgresSaver(connection)
                if row["last_turn_id"] is not None and saver.get_tuple({
                    "configurable": {"thread_id": row["thread_id"]},
                }) is None:
                    raise ConversationAdmissionError("CONVERSATION_CHECKPOINT_MISSING")
                # 原子记录轮次 RUNNING 与会话 RUNNING，先落执行事实再交出执行权。
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO agent_chat_turns "
                        "(environment,user_id,conversation_id,turn_id,state) "
                        "VALUES (%s,%s,%s,%s,'RUNNING')", (*identity, turn_id),
                    )
                    connection.execute(
                        "UPDATE agent_conversations SET state='RUNNING',last_turn_id=%s "
                        "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                        (turn_id, *identity),
                    )
                try:
                    # 控制权交给调用方执行 Agent；作用域返回后再校验结束事件。
                    yield saver, row["thread_id"]
                    # 公开事件必须以 done 结束且不含 error，才能作为完成与展示恢复的证据。
                    if completion_events is not None and (
                        not completion_events or completion_events[-1].get("type") != "done"
                        or any(event.get("type") == "error" for event in completion_events)
                    ):
                        raise ConversationAdmissionError("TURN_COMPLETION_EVIDENCE_MISSING")
                    # Persist the final projection before releasing admission. A
                    # lost B-side response can now be repaired without agent IO.
                    # 完成事件与会话 READY 同事务提交，避免下一轮进入时上一轮证据尚未落库。
                    with connection.transaction():
                        connection.execute(
                            "UPDATE agent_chat_turns SET state='COMPLETED',events=%s,"
                            "completed_at=now() WHERE environment=%s AND user_id=%s "
                            "AND conversation_id=%s AND turn_id=%s",
                            (Jsonb(completion_events or []), *identity, turn_id),
                        )
                        connection.execute(
                            "UPDATE agent_conversations SET state='READY' "
                            "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                            identity,
                        )
                # 普通异常和进程内控制异常都按未确认处理，保留事实并阻止自动重放工具。
                except BaseException:
                    with connection.transaction():
                        connection.execute(
                            "UPDATE agent_chat_turns SET state='NEEDS_REVIEW' "
                            "WHERE environment=%s AND user_id=%s AND conversation_id=%s "
                            "AND turn_id=%s", (*identity, turn_id),
                        )
                        # 同时关闭会话后续准入，避免绕过未确认的上一轮继续执行。
                        connection.execute(
                            "UPDATE agent_conversations SET state='FAILED' "
                            "WHERE environment=%s AND user_id=%s AND conversation_id=%s",
                            identity,
                        )
                    raise
            finally:
                # 最终释放会话级锁；已提交的轮次状态独立保留供下次检查。
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
