package dev.a2flow.management.lifecycle.domain.graph;

import java.util.List;

import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

/**
 * Workflow Router 节点领域对象（nodeType=ROUTER）。
 *
 * <p>Router Node 是 Adviser 拥有的系统路由步骤，不调用 Skill。配置态保存：必填的
 * {@code routerPrompt}（说明如何基于现有业务事实选择路径）、平台固定版本化 Router
 * JSON Schema 契约标识 {@code routerContractVersion}（int，目前仅支持 1）和
 * {@code routerSchemaDigest}，以及至少两条候选路由 {@code candidates}。
 *
 * <p>模型只能从 {@code candidates} 中的 routeKey 中选择唯一一个，不能创造新路由、
 * 直接指定 nodeCode 或一次选择多个目标。
 *
 * <p>上游：WorkflowGraphAggregateParser（nodeType=ROUTER 时路由到此类）。
 * <p>下游：WorkflowGraphAggregate（nodes 列表）、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：路由模型调用、Route Decision 运行态对象、候选 Schema 注册。
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Accessors(chain = true)
public class WorkflowRouterNode extends WorkflowNode {

    private String routerPrompt;
    private int routerContractVersion;
    private String routerSchemaDigest;
    private List<WorkflowRouterCandidate> candidates;
}
