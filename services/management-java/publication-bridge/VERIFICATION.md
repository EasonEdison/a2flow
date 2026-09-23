# 发布验证 — 2026-09-22

源码编译：强类型 HTTP 协议调整后，Java 17 Maven `test-compile` 通过。
这里不声称 Maven 测试执行器已运行；集成测试 main 方法是另行执行的。

独立本机 PostgreSQL 测试通过，使用两个新初始化的数据库和临时回环 HTTP 发布桥。
测试结束后已停止临时数据库集群。

已验证链路：

- 真实 Java HTTP 适配器 → Python 发布桥 → 已提交的 PRT 发布；重试返回相同 receipt。
- 真实写入 PRT CURRENT 和 ONLINE STABLE，并通过现有 Python AssetReader 读取。
- 保留冻结的 Application 和 Ability 引用；未修改的 Python 读取器能够解析既有 Application/Component/Ability 依赖闭包。
- 拒绝错误服务令牌、过期 serving CAS、相同 requestId 对应不同内容、错误包摘要、缺失目标依赖及环境标记不匹配。
- Receipt 插入失败时，不可变候选版本和 serving 选择一并回滚。
- 不支持的旧组件绑定明确失败，不会从发布的 Skill 中静默消失。

复用的 Python 源码来自项目版本 `4710ec0801bb8cf65129e138eb8e69c6d6cc3e0c` 的只读归档。
本次测试使用的上游文件精确摘要如下：

| Asset-store 模块 | SHA-256 |
| --- | --- |
| postgres.py | `195da4c9d34b812a4f75e46da64cce914e4dbacd2ac9f9d9119aa7c43807eb2c` |
| reader.py | `3537335960b825fe7a9cecc9ce770d705996a18d71889e56a855f3fe7b338e93` |
| validation.py | `d994e30d68289637852d79d5dad34d271e3e07117b4591b8c696db53d4668f58` |

本次验证的是 **Skill** 适配器，不是四类资产的编写及发布全链路。
目标 Ability、Application、Component 和 Workflow 发布器仍是独立且未完成的集成工作。
依赖测试使用现有、已验证的公开演示资产，不代表 Java 已发布这些资产。
本次测试没有修改远程数据库、部署服务、开放公网访问、调用模型或执行浏览器验收。
