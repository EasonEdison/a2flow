# 实现任务

## 状态

本文件只跟踪实现进度。当前设计为 `PROPOSED`，所有实现任务均未开始；设计文档写入和 Git 集成不勾选实现项。

## 0. 共享契约门禁

- [ ] 0.1 接入 main-brain 批准的 `AssetRef`、`ReleaseRef`、摘要和发布幂等契约。
- [ ] 0.2 与 Skill registry 固化按 release 查询发布状态及输入/输出 schemaRef 的只读端口。
- [ ] 0.3 与 Runtime 固化 execution manifest 版本协商、解析方向和失败关闭语义。
- [ ] 0.4 固化首版 schema 兼容规则及 Adapter Skill 边界。

## 1. PostgreSQL 草稿与发布物

- [ ] 1.1 实现 draft head、draft snapshot、Workflow release、release dependency 和 idempotency repositories。
- [ ] 1.2 增加 revision、release identity 与 requestKey 唯一约束和事务测试。
- [ ] 1.3 验证多 API 实例并发保存/发布不依赖本地锁或缓存。

## 2. 应用端口与校验

- [ ] 2.1 实现创建、读取、保存 Workflow draft 的应用端口和乐观并发。
- [ ] 2.2 实现结构、拓扑、Skill release 和 schema 链四层校验器。
- [ ] 2.3 实现稳定 issue code、nodeId/fieldPath 定位和失败关闭行为。
- [ ] 2.4 实现确定性线性编译和 layout/展示字段剥离。

## 3. 幂等发布与读取

- [ ] 3.1 实现指定 draft revision 的服务端重新校验与原子发布。
- [ ] 3.2 实现相同 requestKey 返回同一 release 的响应丢失恢复。
- [ ] 3.3 实现按 Workflow release ref 读取不可变 manifest 与摘要的端口。
- [ ] 3.4 实现依赖超时、撤销和不支持 contractVersion 的失败关闭测试。

## 4. React + TypeScript 编辑器

- [ ] 4.1 评估并锁定 React Flow 或经批准的替代依赖及许可证。
- [ ] 4.2 实现 START/SKILL/END 受限画布和已发布 Skill release 选择器。
- [ ] 4.3 实现受控连接、节点级校验展示、保存状态和发布确认。
- [ ] 4.4 增加键盘操作、错误可访问性和 1 至 8 个 Skill 节点边界测试。

## 5. 跨域集成与准出

- [ ] 5.1 接入真实 Skill registry contract test，覆盖发布/不可用/无权 release。
- [ ] 5.2 接入 Runtime manifest consumer contract test，验证顺序、摘要和版本拒绝。
- [ ] 5.3 执行并记录 `regression.md` 全部 planned 场景。
- [ ] 5.4 在 PostgreSQL 上完成双 API 实例并发与发布幂等测试。
- [ ] 5.5 更新 `readiness.md`；只有全部必需门禁有运行证据后才改变 `NO READY`。
