package dev.a2flow.management.lifecycle.domain.graph;

import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 完整聚合草稿领域对象。
 *
 * <p>该对象表达一个完整 Workflow 配置的强类型视图，对应 {@code workflow_definition.draft_payload_json}
 * 的顶层结构。字段含义：
 * <ul>
 *   <li>{@code snapshotContractVersion} — 聚合 JSON 格式版本（当前只支持 v2，包含 SKILL
 *       节点可选 quickTriggerMessage；旧版本与未知版本均失败关闭）。</li>
 *   <li>{@code workflowCode} — Workflow 稳定身份，与 DB 行的 workflow_code 列保持一致。</li>
 *   <li>{@code metadata} — 扩展元数据，由配置前端维护，本服务当前透传不解析内部字段。</li>
 *   <li>{@code nodes} — 强类型节点列表，每个元素是具体节点子类（Skill/Router/Fork/Join/Summary）。</li>
 *   <li>{@code edges} — Edge 列表（NORMAL/ROUTING/PARALLEL 三种类型）。</li>
 *   <li>{@code summaryConfig} — 聚合级 Summary 配置段，持有 Summary 提示词。</li>
 * </ul>
 *
 * <p>上游：WorkflowGraphAggregateParser（从 draftPayloadJson 解析并返回此对象）。
 * <p>下游：WorkflowDefinitionService（updateWorkflowDraft 中的节点校验）、
 *         WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：运行态快照、compiledPlan 构建、DB 持久化（由 Service 将 JSON 字符串写入 DO）。
 */
@Data
@Accessors(chain = true)
public class WorkflowGraphAggregate {

    private int snapshotContractVersion;
    private String workflowCode;
    private Map<String, Object> metadata;
    private List<WorkflowNode> nodes;
    private List<WorkflowEdge> edges;
    private WorkflowSummaryConfig summaryConfig;
}
