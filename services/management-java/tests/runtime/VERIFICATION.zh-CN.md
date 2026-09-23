# A2UI 确定性核心验证

日期：2026-09-23。此处记录局部源码验证，不是 RPC、数据库发布或页面验收。

- Java 17 Maven `-DskipTests test-compile`：通过。
- `A2uiMappingSmoke`：通过。五类参数来源隔离、signed64 最大 userId、卡片不能覆盖可信 userId、布尔掩码转换、缺字段和重复目标拒绝、业务谓词数值比较/类型拒绝、首个成功分支选择、传输失败不被业务字段覆盖。
- `A2uiAdapterSmoke`：16 项通过。MESSAGE_TEMPLATE、A2UI_PASSTHROUGH MANY、批次后续消息失败后原 Surface 状态不变。
- 五种结果转换覆盖代表性合法/非法值：NUMBER_TO_STRING、MINOR_UNIT_TO_DECIMAL_STRING、BOOLEAN_ARRAY_TRUE_COUNT、PAGINATION_STATE、ARRAY_TO_CHILDREN_PREFIX。

仅运行纯内存核心，没有调用模型或业务接口，也未改动数据库。实例初始化、持久化、RPC 服务及客户端、前端消费、完整编译产物读回仍需联调。

通过依赖 classpath 和 `target/classes`，使用 Java 17 编译并执行两个独立 `main` 入口即可复验。不依赖 JUnit，不生成运行成功的伪造业务回执。
