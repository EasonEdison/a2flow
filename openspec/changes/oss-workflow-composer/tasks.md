# Phase 1 实现任务

## 状态

本文件只跟踪待实现工作。统一基线对齐、OpenSpec 修订和非规范 fixture 证据记录在 checkpoint/regression，不将它们冒充服务实现。共享 graph revision 未经 main-brain 审查前，以下任务全部保持未勾选。

## 0. 共享契约与打包门禁

- [ ] 0.1 接入 main-brain 批准的 graph identity/version、exact `skillKey`/typed mapping、trusted context 和 environment-local resolver revision。
- [ ] 0.2 接入 interaction/result references、control request dedupe 和配置版本比较契约。
- [ ] 0.3 与 Runtime 固化发布图到 Python LangGraph 的版本化 consumer contract。
- [ ] 0.4 按 ENG-01 提交可导入的 Python workflow-registry 模块布局；根 `pyproject`/lock 仍由 main-brain 单一协调。

## 1. Workflow registry 最小骨架

- [ ] 1.1 在 `services/workflow-registry/` 创建最小 Python 模块，不修改共享根 manifest，也不默认启动独立常驻服务。
- [ ] 1.2 实现 PostgreSQL-only draft/revision repository 和 expected-revision 乐观并发。
- [ ] 1.3 通过共享 publication/resolver 保存 PRT/ONLINE 分离资产，不自建 gray/fallback。
- [ ] 1.4 验证两个无状态实例共享 PostgreSQL 时草稿写入和发布控制请求不丢更新。

## 2. 图模型与静态校验

- [ ] 2.1 实现 sequence、AI decision、condition MERGE、parallel split/JOIN、FINALIZER 的受限无环模型。
- [ ] 2.2 拒绝循环、孤儿节点、未知 candidate、缺失/重复 branch、未配对 join 和嵌套 parallel。
- [ ] 2.3 校验 decision candidate 与 A2UI selection Application 引用，不要求 Skill 路由字段。
- [ ] 2.4 校验 REQUIRED/ALLOW_SKIP 传播边界和真实状态不改写。
- [ ] 2.5 输出稳定 issue code 和 node/edge/region 定位。

## 3. 发布与读取适配

- [ ] 3.1 对指定 draft revision 重新校验并生成确定性发布图，剥离 layout。
- [ ] 3.2 通过共享 publish control request dedupe 返回同一发布结果，不声明业务 exactly-once。
- [ ] 3.3 实现 Runtime 按共享 identity/version 读取图候选的适配端口。
- [ ] 3.4 对跨环境、未授权、版本不支持和引用不可解析失败关闭。

## 4. Consumer contract 验证

- [ ] 4.1 与 Skill registry 验证 exact `skillKey` 和统一 `use_skill`，同一 Skill 无 Workflow 适配或前缀猜测。
- [ ] 4.2 与 A2UI registry 验证 selection Application、interaction mode 和 Action success/completion。
- [ ] 4.3 与 Runtime 验证 A WAITING 时 B1→B2 继续且 JOIN 等 A。
- [ ] 4.4 与 Runtime 验证 ALLOW_SKIP failure/真实 skip 可 join、REQUIRED failure 阻断。
- [ ] 4.5 与 Runtime 验证 A2UI-only retry、Finalizer/stop、版本失配 reset 门禁。
- [ ] 4.6 与 Runtime 验证 A→B→C 的 C 获得 A、B，以及 join 后只汇总真实执行分支祖先。

## 5. 准出

- [ ] 5.1 执行 PostgreSQL focused integration 和双实例竞争控制请求验证。
- [ ] 5.2 在 `regression.md` 记录 method、params、success data、字段断言和真实输出。
- [ ] 5.3 只有 shared contract、服务实现和 Runtime 证据齐全后才更新 `readiness.md`，否则保持 `NO READY`。
