# oss-digital-employee 执行检查点

## 当前状态

- 任务：`oss-digital-employee`
- 阶段：`SW-P1-SUBSET-01` 已同步；数字员工实现仍未放行
- 设计状态：`PROPOSED`
- Runtime 准备度：`NO READY`
- 工作分支：`codex/oss-digital-employee/design`
- 目标分支：`origin/main`
- 起始基线：`3fa291bf4ec1f175ce2d259fb4ddf20640f945eb`
- 当前对齐基线：`SW-P1-20260907.2 + ENG-01 + SW-P1-SUBSET-01`；已同步到 `origin/main@7bc1aa0ad087ff33044ac5f0db47dee44d920b4e`

## 已确认边界

- 只修改 `openspec/changes/oss-digital-employee/`。
- 数字员工前后端拥有业务场景、用户会话视图、人工确认体验、业务适配和结果呈现。
- 通用 Runtime 拥有 run、checkpoint、事件、Action 与 stop 权威；只允许基线规定的 A2UI 节点 retry，本任务不自建状态机。
- Web 端负责消费并呈现可复用 A2UI Host；协议版本仍由主控统一裁决。
- PostgreSQL 是开发、测试和部署唯一关系型数据库；应用按多实例正确性设计。
- 不实现代码、不安装依赖、不修改服务、数据库、端口或部署状态。
- `SW-P1-SUBSET-01` 只批准列明的共享 Skill/Policy 薄包与对应 owner 源码；完整 BFF、Host、control/event/Action 仍不在本任务实现范围。

## 已完成

- [x] 读取本机项目入口、平台边界和 clean-room 门禁。
- [x] 核验服务器 worktree、分支和状态。
- [x] 合入最新 `origin/main@35282b6259eb6527a17bf359e92f2ec432d69681` 并读取 `SW-P1-20260907.2`。
- [x] 按新基线删除冻结旧版本继续、通用 retry、第二套 event/action、产品侧业务幂等与 stopped resume 语义。
- [x] 最小切片收敛为侧栏启动、节点输入、显示/交互、配置失配 reset、stop 后只读与 A2UI-only retry；真实业务写保持排除。
- [x] 向 contracts owner 发送操作、事件、错误、配置失配、stop/reset、A2UI 与 Tool 责任边界的 consumer requirements，并抄送 main-brain。
- [x] 查阅公开 Store/delete 原语并按 main-brain 反馈形成 A/B/B+ 成本档；基础偏好元数据/薄 facade 不自动延期，实际 adapter 与删除权限待代码验证。
- [x] 本轮远端 patch 发现多 hunk 对工作树偏移敏感；失败均原子退出，改用带上下文的单 hunk `git apply --recount` 并逐次核对。
- [x] proposal、design、tasks、spec、regression、readiness 已完成对齐；所有实现任务保持未勾选。
- [x] 范围、UTF-8、敏感信息、8 Requirement/8 Scenario、0 实现勾选与 `git diff --check` 通过；服务器无 OpenSpec CLI，未执行 strict validate。
- [x] 内容提交 `809ebaafbfeabdf331e04a639e295bc4025b846c` 已推送；合并最新 main 后的 worker `d7c3594602e75fae1a30938b26e73a9c24d7437f` 已集成到 `origin/main`。
- [x] 已读 `ENG-01`：M 后端四域采用 Python 模块，不自动改变数字员工 BFF 技术选择；未修改根依赖或启动服务。
- [x] 合入 `origin/main@7b1257aff3a157364387a7e55690984aa219d670` 的 A2UI 修订；fixture 测试 14/14 与 2 个合成 Application validator 通过，仅作为辅助证据。
- [x] 补充 Python/TypeScript BFF 最小选项、拒绝浏览器直连，以及 web/BFF/A2UI Host 职责路径清单；未锁定框架或创建代码。
- [x] BFF 选项与路径清单提交 `c1050b83ddbb5e8b604e690a90b8349e1bdb0ce9` 已推送并集成到 `origin/main`。
- [x] 按 main-brain 复核修正 R8 成本门禁与浏览器直连论证：最小偏好 schema/薄 adapter 不自动延期，否决依据是既定产品后端隔离职责。
- [x] 两处小修订提交 `7569c02e295cad0f65a6c74ede09f77aee039baa` 已推送并集成到 `origin/main`。
- [x] 完整读取 `implementation-release-01.md`，文件 SHA256 匹配 `c14eb61371562bf512b393ab347c80d2c4e3be082e4a7e838dc13e2a0f9743a4`。
- [x] 核对批准标识 `SW-P1-SUBSET-01`、schema snapshot `a1cb44e88ce5bb603c62b4618804c78ae0d5585c` 与 schema SHA256 `10fb8f2fb26529ba7850e981991bcb343037aa6defe7f22646e00f1cdf59fa3b`；不把 wire candidate 或整个 bundle 视为批准。
- [x] 独立 checker 尝试被本 worktree 的 `python3.11` 缺少 `jsonschema` 阻断；未安装依赖，未声称本任务复跑 57/57。schema 文件哈希已匹配。
- [x] release 边界检查点提交 `7bc1aa0ad087ff33044ac5f0db47dee44d920b4e` 已推送并集成到 `origin/main`；该事实只证明同步与边界记录，不代表数字员工实现放行或 Runtime READY。

## 下一可执行动作

等待 main-brain 下发数字员工产品的正式实施入口；不要求用户重复背景或开工确认，入口下发前不进入 `apps/digital-employee/` 或 `packages/a2ui-host/` 实现。

## 禁止与未决

- 禁止读取其他任务 checkpoint 或 proprietary 项目材料。
- 禁止把设计集成误报为设计批准、实现完成、部署完成或 runtime 可用。
- Runtime Python + Deep Agents SDK + LangGraph 已是基线；`SW-CONTRACTS-P1-CANDIDATE.1` 仍为 provisional wire，且本 release 不批准完整 BFF/Host/control/event/Action、数据库、服务或部署。
