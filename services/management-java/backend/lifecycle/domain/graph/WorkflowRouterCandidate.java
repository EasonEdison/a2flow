package dev.a2flow.management.lifecycle.domain.graph;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Router Node 单条候选路由描述。
 *
 * <p>每条候选路由包含在本 Router 内唯一的业务 {@code routeKey}、供模型理解的业务说明
 * 和目标节点 {@code targetNodeCode}。模型只能从已发布候选 routeKey 中选择一个，
 * 不能创造新 routeKey 或直接指定 nodeCode。
 *
 * <p>上游：WorkflowGraphAggregateParser（从 Router Node 的 {@code candidates} 数组解析）。
 * <p>下游：WorkflowRouterNode、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：路由选择逻辑、Route Decision 运行态对象、路由结果持久化。
 */
@Data
@Accessors(chain = true)
public class WorkflowRouterCandidate {

    private String routeKey;
    private String description;
    private String targetNodeCode;
}
