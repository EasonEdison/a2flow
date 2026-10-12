# 双路径 A2UI 与管理端分页准出

日期：2026-10-13。结论：**本轮约定范围 READY**。

## 交付

- 管理端 Capability/Application 列表 SQL 分页、轻量 DTO、查询条件与前端分页；编辑仍读完整详情。
- 稳定 `render_application` 保留；新增 `generate_a2ui`，内部专用隔离 SubAgent 仅生成受控候选布局。
- 共用真实 LoadBinding、受控 Action、卡片存储与历史恢复；生成定义为私有元数据，不自动发布管理资产。
- Chat 已验证真实分页、跨页选择回填及历史交互；Workflow 已验证生成阅读卡与两个稳定卡的混合执行、三次人工确认和终态历史。

## 源码、部署、运行证据

- M/静态基础交付：`c0167966bacbbe5a8757bb88853a0e0c85a2064d`。
- 最终 Python 修复：`1527d772e0922592680b51fe1acfefb45fe76e18`，双 main 一致；execution/runtime/bside 对应 `scoped-1527d77`。
- 最终公开页面验收 run：`d6cde8931de24eb68e00b49eb2bd52c2`，数据库 `SUCCEEDED`。
- 三张卡 `COMPLETED`，各一条 `FINISHED` Action；一张 GENERATED、两张 PUBLISHED，无重复生成卡。
- 浏览器刷新恢复完整过程与只读卡片，无 console warn/error。详细证据见 [regression.md](regression.md)。

## 保留边界

- 工程身份、业务参数、RPC、LoadBinding 与 Action 不由子 Agent 任意生成；未知数据路径和组件明确拒绝。
- 新只读字段许可仅覆盖同顶层 List 作用域中已声明的基础类型字段，不是通用复杂 JSON Schema 推导器。
- 模型生成可能失败；不增加自动重试、修复或退回稳定布局。四个失败验收运行保留，未重放业务操作。
- 不宣称覆盖任意组件、全仓测试、移动端专项或生产容量压测；约 481 MiB available 仅为验收时瞬时值。
- 本轮没有删除数据、数据库迁移、稿件导出或对外内容发布。保留原镜像与私有部署回退计划。
