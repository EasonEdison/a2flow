package dev.a2flow.management.release;

import dev.a2flow.management.lifecycle.domain.graph.CompiledPlan;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregate;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 在 common-v2 Build/Version 中冻结的自包含发布正文。
 *
 * <p>正文同时保存完整 Workflow graph 与编译后的完整执行计划，并以固定三层 contract version 和
 * canonical digest 约束读写一致性。上游由 WorkflowReleaseAssetAdapter 从当前草稿一次性构造，
 * 下游由发布、依赖展开、历史恢复和 Adviser 发布快照读取链消费。本模型不保存环境指针、Skill
 * 版本选择或运行态状态，也不允许从当前草稿补齐历史正文。
 */
@Data
@Accessors(chain = true)
public class WorkflowReleasePayload {

    private Integer payloadContractVersion;
    private Integer workflowSnapshotContractVersion;
    private Integer compiledPlanContractVersion;
    private String workflowCode;
    private String specialistCode;
    private Long draftRevision;
    private String draftDigest;
    private String displayName;
    private String description;
    private WorkflowGraphAggregate workflowGraph;
    private CompiledPlan compiledPlan;
    private String compiledPlanDigest;
    private String canonicalDigest;
}
