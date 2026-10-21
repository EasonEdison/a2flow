"""PostgreSQL repositories for b-side rows; each method owns a short connection.

Rows are userId-scoped everywhere; write methods additionally filter by
user_id so a caller bug can never mutate another user's row (defense in
depth, mirroring the management repository conventions).
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from psycopg.errors import UniqueViolation
from skillweave_contracts.user_id import require_user_id

from .errors import BsideError
from .interaction_continuation import continuation_reference
from .persistence_types import ConnectionFactory, DatabaseRow, MessageRecord, message_record


# 序列化只转换时间值, 不在仓库层改变其余数据含义。
def _iso(value: object) -> object:
    return value.isoformat() if isinstance(value, dt.datetime) else value


# 账号仓库只保存密码摘要, 用户身份由数据库序列分配。
class UsersRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    def create(self, *, username: str, password_hash: str, role: str = "USER") -> int:
        """Insert and return the signed 64-bit database user identity."""
        with self._factory() as connection:
            try:
                # 先取得数据库 64 位身份, 并经过共享用户 ID 校验后再插入。
                row = connection.execute(
                    "SELECT nextval(pg_get_serial_sequence('users', 'id')) AS user_id"
                ).fetchone()
                assert row is not None  # nextval SELECT always returns one row.
                user_id = require_user_id(row["user_id"])
                # 同一身份同时写入数据库主键和对外用户字段, 避免两套身份漂移。
                connection.execute(
                    "INSERT INTO users (id, user_id, username, password_hash, role) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (user_id, user_id, username, password_hash, role),
                )
                return user_id
            # 用户名唯一冲突转为可预期错误, 不泄露原 SQL 或摘要。
            except UniqueViolation:
                raise BsideError("USERNAME_TAKEN", 409) from None

    # 登录按用户名读取摘要及服务端角色, 不接受客户端声明角色。
    def find_by_username(self, username: str) -> DatabaseRow | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id, username, password_hash, role FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        return dict(row) if row is not None else None


# 会话表只保存令牌摘要, 认证查询同时关联账号和过期条件。
class SessionsRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    # 签发会话前验证用户 ID, 令牌有效期由上层可信时钟计算。
    def create(self, *, token_sha256: str, user_id: int, expires_at: dt.datetime) -> None:
        require_user_id(user_id)
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO sessions (token_sha256, user_id, expires_at) VALUES (%s, %s, %s)",
                (token_sha256, user_id, expires_at),
            )

    # 过期令牌不返回身份, 用户名和角色取当前数据库账号记录。
    def find_identity(self, token_sha256: str, now: dt.datetime) -> DatabaseRow | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT s.user_id, u.username, u.role "
                "FROM sessions s JOIN users u ON u.user_id = s.user_id "
                "WHERE s.token_sha256 = %s AND s.expires_at > %s",
                (token_sha256, now),
            ).fetchone()
        if row is None:
            return None
        # 转成固定认证协议供请求中间件使用, 不返回令牌和密码字段。
        return {"userId": row["user_id"], "username": row["username"], "role": row["role"]}

    # 退出按令牌摘要删除, 原始浏览器凭据不会进入持久化参数。
    def delete(self, token_sha256: str) -> None:
        with self._factory() as connection:
            connection.execute("DELETE FROM sessions WHERE token_sha256 = %s", (token_sha256,))


# 会话读写围绕所属用户, 消息方法由上层先检查会话权限。
class ConversationsRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    # 创建会话绑定服务端用户, 并返回数据库生成的标识和时间。
    def create(self, *, user_id: int, title: str | None) -> DatabaseRow:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, %s) "
                "RETURNING id, title, created_at",
                (user_id, title),
            ).fetchone()
        assert row is not None  # INSERT RETURNING must produce the inserted row.
        return dict(row)

    # 列表按用户过滤并倒序限量读取, 不扫描全部账号的会话。
    def list_for(self, user_id: int, limit: int = 50) -> list[DatabaseRow]:
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at FROM conversations "
                "WHERE user_id = %s ORDER BY id DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # 归属查询供入口验证使用, 不代表消息仓库自行完成了身份认证。
    def owner(self, conversation_id: int) -> int | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM conversations WHERE id = %s", (conversation_id,)
            ).fetchone()
        return row["user_id"] if row is not None else None


# 这里保存产品展示消息, 不与 Agent 原生消息和检查点争夺执行状态。
class MessagesRepository:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    # 正文与引用分列保存, 运行和恢复关系不依赖正文字符串匹配。
    def append(
        self,
        *,
        conversation_id: int,
        role: str,
        content: dict[str, Any],
        ref_kind: str | None = None,
        ref_id: str | None = None,
    ) -> MessageRecord:
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO messages (conversation_id, role, content, "
                "ref_kind, ref_id) VALUES (%s, %s, %s::jsonb, %s, %s) "
                "RETURNING id, role, content, ref_kind, ref_id, created_at",
                (conversation_id, role, json.dumps(content), ref_kind, ref_id),
            ).fetchone()
        return message_record(row)

    # 一个已提交卡片确认只创建一对恢复消息, 创建与读取既有消息必须区分。
    def claim_interaction_continuation(
        self,
        *,
        user_id: int,
        conversation_id: int,
        card_id: str,
        request_id: str,
        write_completed: bool = False,
    ) -> tuple[bool, MessageRecord, MessageRecord]:
        """Create one follow-up pair per submitted card under the conversation lock.

        Only the transaction that inserts may dispatch. Reading an existing pair
        never resumes an incomplete model turn, including after a process crash.
        """
        require_user_id(user_id)
        # A reusable A2UI card can complete several independently confirmed writes.
        # A repeated response for the same confirmation must never dispatch twice.
        # 普通临时表单按卡片去重, 可复用写卡片则按具体确认请求区分。
        reference = continuation_reference(card_id, request_id if write_completed else None)
        with self._factory() as connection:
            # 会话行锁串行创建恢复消息, 并在事务内再次校验所属用户。
            owner = connection.execute(
                "SELECT user_id FROM conversations WHERE id=%s FOR UPDATE",
                (conversation_id,),
            ).fetchone()
            if owner is None or owner["user_id"] != user_id:
                raise BsideError("CONVERSATION_NOT_FOUND", 404)
            # 按明确恢复引用读取既有消息, 进程重启不能据此重新执行原业务动作。
            rows = connection.execute(
                "SELECT id,role,content,ref_kind,ref_id,created_at FROM messages "
                "WHERE conversation_id=%s AND ref_kind='temporary_interaction' "
                "AND ref_id=%s ORDER BY id",
                (conversation_id, reference),
            ).fetchall()
            # 已有记录必须恰好是用户与助手一对, 否则保留未确认并拒绝继续。
            if rows:
                by_role = {row["role"]: message_record(row) for row in rows}
                if len(rows) != 2 or set(by_role) != {"user", "assistant"}:
                    raise BsideError("CHAT_CONTINUATION_UNCONFIRMED", 409)
                return False, by_role["user"], by_role["assistant"]
            # 恢复来源保存卡片和原动作请求号, 供页面关联真实提交。
            marker = {"cardId": card_id, "requestId": request_id}
            contents = (
                (
                    "user",
                    {
                        # 这是服务端续聊提示, 不是用户再次发送的业务指令, 真实结果仍从保存事实读取。
                        "text": (
                            "写操作已完成，请根据已保存的真实执行结果继续。"
                            if write_completed
                            else "临时交互已提交，请根据已保存的交互结果继续。"
                        ),
                        "delivery": "submitted",
                    },
                ),
                (
                    "assistant",
                    {"text": "", "delivery": "running", "parts": [], "continuation": marker},
                ),
            )
            # 输入与助手占位在同一事务插入, 返回创建标志供调用方区别新旧恢复。
            created: list[MessageRecord] = []
            for role, content in contents:
                row = connection.execute(
                    "INSERT INTO messages (conversation_id,role,content,ref_kind,ref_id) "
                    "VALUES (%s,%s,%s::jsonb,'temporary_interaction',%s) "
                    "RETURNING id,role,content,ref_kind,ref_id,created_at",
                    (conversation_id, role, json.dumps(content), reference),
                ).fetchone()
                created.append(message_record(row))
            return True, created[0], created[1]

    # 先取最近消息再按原顺序返回, 避免限量查询只显示最早历史。
    def list_for(self, conversation_id: int, limit: int = 200) -> list[MessageRecord]:
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT * FROM (SELECT id, role, content, ref_kind, ref_id, created_at "
                "FROM messages WHERE conversation_id = %s "
                "ORDER BY id DESC LIMIT %s) recent ORDER BY id ASC",
                (conversation_id, limit),
            ).fetchall()
        return [message_record(row) for row in rows]

    # 只允许更新目标会话的助手消息, 不能通过投影写入覆盖用户输入。
    def update_delivery(
        self, *, conversation_id: int, message_id: int, content: dict[str, Any]
    ) -> None:
        with self._factory() as connection:
            changed = connection.execute(
                "UPDATE messages SET content=%s::jsonb "
                "WHERE conversation_id=%s AND id=%s AND role='assistant'",
                (json.dumps(content), conversation_id, message_id),
            ).rowcount
            # 没有准确命中一条消息视为保存失败, 不把丢失投影当正常完成。
            if changed != 1:
                raise ValueError("CHAT_MESSAGE_MISSING")

    # 旧消息仅作为一次迁移输入, 不作为另一份持续维护的模型历史。
    def legacy_history(
        self, user_id: int, conversation_id: int, before_id: int
    ) -> list[MessageRecord]:
        """One-time migration input, not a second live model history source."""
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT m.id,m.role,m.content FROM messages m "
                "JOIN conversations c ON c.id=m.conversation_id "
                "WHERE c.user_id=%s AND c.id=%s AND m.id<%s "
                "AND m.role IN ('user','assistant') "
                "AND NOT (m.content ? 'delivery') ORDER BY m.id",
                (user_id, conversation_id, before_id),
            ).fetchall()
        return [message_record(row) for row in rows]


# 计划存储只维护调度配置, 触发投递和真实执行状态由其他模块负责。
class SchedulesRepository:
    # 动态更新列严格限制为固定白名单, 客户端不能提供任意 SQL 列名。
    _COLUMNS = frozenset(
        {
            "enabled",
            "rule_type",
            "rule_json",
            "timezone",
            "input_text",
            "next_run_at",
            "last_run_at",
        }
    )

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    # 下一触发时间由规则层预先计算, 仓库与原始配置一起保存。
    def create(
        self,
        *,
        user_id: int,
        workflow_key: str,
        environment: str,
        rule_type: str,
        rule_json: dict[str, Any],
        timezone: str,
        input_text: str,
        next_run_at: dt.datetime,
    ) -> DatabaseRow:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute(
                "INSERT INTO workflow_schedules "
                "(user_id, workflow_key, environment, rule_type, rule_json, "
                " timezone, input_text, next_run_at) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s) "
                "RETURNING id, workflow_key, environment, rule_type, rule_json,"
                " timezone, input_text, enabled, next_run_at, last_run_at, "
                " created_at",
                (
                    user_id,
                    workflow_key,
                    environment,
                    rule_type,
                    json.dumps(rule_json),
                    timezone,
                    input_text,
                    next_run_at,
                ),
            ).fetchone()
        assert row is not None  # INSERT RETURNING must produce the inserted row.
        return dict(row)

    # 按所属用户读取有限计划, 返回各自下次和上次触发时间。
    def list_for(self, user_id: int, limit: int = 100) -> list[DatabaseRow]:
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT id, workflow_key, environment, rule_type, rule_json,"
                " timezone, input_text, enabled, next_run_at, last_run_at,"
                " created_at FROM workflow_schedules WHERE user_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # 读取保留 user_id 与 environment, 调用方据此核对操作范围。
    def get(self, schedule_id: int) -> DatabaseRow | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT id, user_id, workflow_key, environment, rule_type,"
                " rule_json, timezone, input_text, enabled, next_run_at,"
                " last_run_at, created_at FROM workflow_schedules "
                "WHERE id = %s",
                (schedule_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    # 更新同时限定计划和用户, 防止检查之后的跨账号写入。
    def update(self, schedule_id: int, user_id: int, **fields: object) -> DatabaseRow | None:
        require_user_id(user_id)
        # 拒绝未知列及空更新, 列名不能由请求任意扩展。
        unknown = set(fields) - self._COLUMNS
        if unknown or not fields:
            raise BsideError("INVALID_SCHEDULE_UPDATE", 400)
        assignments = []
        values: list[Any] = []
        # 仅白名单列参与拼接, 所有具体值用参数绑定, 规则 JSON 额外编码。
        for name, value in fields.items():
            assignments.append(f"{name} = %s")
            if name == "rule_json":
                value = json.dumps(value)
                assignments[-1] = f"{name} = %s::jsonb"
            values.append(value)
        # 最终 WHERE 同时包含计划与用户身份, 未命中返回空值。
        values.extend([schedule_id, user_id])
        with self._factory() as connection:
            row = connection.execute(
                "UPDATE workflow_schedules SET "
                + ", ".join(assignments)
                + " WHERE id = %s AND user_id = %s "
                "RETURNING id, workflow_key, environment, rule_type, rule_json,"
                " timezone, input_text, enabled, next_run_at, last_run_at,"
                " created_at",
                values,
            ).fetchone()
        return dict(row) if row is not None else None

    # 删除同样携带用户条件, 返回是否命中而不是无条件宣称成功。
    def delete(self, schedule_id: int, user_id: int) -> bool:
        require_user_id(user_id)
        with self._factory() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_schedules WHERE id = %s AND user_id = %s",
                (schedule_id, user_id),
            )
        return cursor.rowcount > 0


# 产品归属记录连接控制请求与真实运行, 不能将控制号等同业务完成身份。
class RunOwnershipRepository:
    """B-side ownership of Runtime control requests (v1 run identity)."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._factory = connection_factory

    # 保留旧创建入口, 写入前仍检查可信用户身份。
    def create(self, *, control_id: str, user_id: int, workflow_key: str) -> None:
        require_user_id(user_id)
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO run_ownership (control_id, user_id, workflow_key) VALUES (%s, %s, %s)",
                (control_id, user_id, workflow_key),
            )

    # 远端调用前幂等预留控制身份, 网络超时后仍可读回归属。
    def reserve(
        self,
        *,
        control_id: str,
        user_id: int,
        workflow_key: str,
        environment: str | None = None,
        source_type: str = "unknown",
    ) -> None:
        """Idempotently bind a scheduled control before remote dispatch."""
        require_user_id(user_id)
        with self._factory() as connection:
            connection.execute(
                "INSERT INTO run_ownership (control_id, user_id, workflow_key, environment, source_type) "
                # 并发重发复用控制号, 不覆盖原始用户、资产和环境。
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (control_id) DO NOTHING",
                (control_id, user_id, workflow_key, environment, source_type),
            )
            row = connection.execute(
                # 插入后复核旧记录, 防止同控制号被用于不同用户或工作流。
                "SELECT user_id, workflow_key, environment FROM run_ownership WHERE control_id = %s",
                (control_id,),
            ).fetchone()
            # 归属、资产或已有环境不一致都报冲突, 不静默接管旧运行。
            if (
                row is None
                or row["user_id"] != user_id
                or row["workflow_key"] != workflow_key
                or (row["environment"] is not None and row["environment"] != environment)
            ):
                raise BsideError("RUN_CONTROL_ID_CONFLICT", 409)

    # 真实运行身份用于内部恢复归属校验, 与控制请求查询分开。
    def owner_by_run(self, run_id: str) -> int | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM run_ownership WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        return row["user_id"] if row is not None else None

    # 运行历史按创建时间倒序, 只返回用户已预留或启动的控制记录。
    def list_for(self, user_id: int, limit: int = 50) -> list[DatabaseRow]:
        require_user_id(user_id)
        with self._factory() as connection:
            rows = connection.execute(
                "SELECT control_id, workflow_key, created_at, run_id "
                "FROM run_ownership WHERE user_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # 只给尚未绑定的控制请求补真实运行号, 不覆盖已有运行关系。
    def bind_run_id(self, control_id: str, run_id: str) -> None:
        with self._factory() as connection:
            connection.execute(
                "UPDATE run_ownership SET run_id = %s WHERE control_id = %s AND run_id IS NULL",
                (run_id, control_id),
            )

    # 归属检查包含可信用户, 不允许单凭知道控制 ID 读取运行。
    def owned_by(self, user_id: int, control_id: str) -> bool:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute(
                "SELECT 1 FROM run_ownership WHERE user_id = %s AND control_id = %s",
                (user_id, control_id),
            ).fetchone()
        return row is not None

    # 控制归属未知返回空值, 调用方统一处理为不存在。
    def owner(self, control_id: str) -> int | None:
        with self._factory() as connection:
            row = connection.execute(
                "SELECT user_id FROM run_ownership WHERE control_id = %s", (control_id,)
            ).fetchone()
        return row["user_id"] if row is not None else None
