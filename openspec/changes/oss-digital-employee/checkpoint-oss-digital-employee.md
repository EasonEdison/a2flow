# oss-digital-employee 执行检查点

## 当前状态

- 任务：`oss-digital-employee`
- 阶段：首轮独立设计草案
- 设计状态：`PROPOSED`
- Runtime 准备度：`NO READY`
- 工作分支：`codex/oss-digital-employee/design`
- 目标分支：`origin/main`
- 起始基线：`3fa291bf4ec1f175ce2d259fb4ddf20640f945eb`

## 已确认边界

- 只修改 `openspec/changes/oss-digital-employee/`。
- 数字员工前后端拥有业务场景、用户会话视图、人工确认体验、业务适配和结果呈现。
- 通用 Runtime 拥有运行、checkpoint、恢复、重试和幂等执行语义；本任务不自建运行状态机。
- Web 端负责消费并呈现可复用 A2UI Host；协议版本仍由主控统一裁决。
- PostgreSQL 是开发、测试和部署唯一关系型数据库；应用按多实例正确性设计。
- 不实现代码、不安装依赖、不修改服务、数据库、端口或部署状态。

## 已完成

- [x] 读取本机项目入口、平台边界和 clean-room 门禁。
- [x] 核验服务器 worktree、分支和状态。
- [x] 获取并合入最新 `origin/main`；当前基线无新增提交。
- [x] 查阅 A2UI 与 AG-UI 公开官方资料，作为候选协议边界依据。
- [x] 首次六文件大补丁因手工 hunk 行数不一致失败且未写入；已改为逐文件 patch 并核对。
- [x] 新文件后续增量不能直接用 git apply 更新；设置 intent-to-add 后使用系统 patch，清理了任务自产生的 reject 文件。
- [x] 范围检查确认仅 7 个约定文件；spec 与 regression 各 8 个场景/用例，实现任务勾选数为 0。
- [x] git diff --check、公开来源清单、敏感信息和占位符检查通过；OpenSpec CLI 不可用，未执行 strict validate。
- [x] 完成六份设计文档；能力 spec 收敛为 8 条可验收 Scenario，所有实现任务保持未勾选。

- [x] 提交前再次 fetch/merge 最新 origin/main，已快进到 5be65edd8c1247119b8b5680847bdabaf4fb2e93；本任务文件无冲突。

- [x] 7 个本任务文件已通过提交前门禁并形成设计提交；最终 worker/main SHA 以 Git 和交付回报为准，避免 checkpoint 自引用。

## 下一可执行动作

完成 worker 与 origin/main 源码集成后停止执行，等待 main-brain 审查；未经批准不进入实现。

## 禁止与未决

- 禁止读取其他任务 checkpoint 或 proprietary 项目材料。
- 禁止把设计集成误报为设计批准、实现完成、部署完成或 runtime 可用。
- 待主控裁决 Runtime 语言、运行事件/控制协议、A2UI 版本与发布资产身份。
