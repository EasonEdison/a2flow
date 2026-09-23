package dev.a2flow.management.lifecycle.domain.graph;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 聚合草稿中的 Summary 配置段。
 *
 * <p>该对象对应聚合 JSON 顶层 {@code summaryConfig} 字段，保存简版总结提示词、可选详细总结提示词和处理建议。
 * 与 {@link WorkflowSummaryNode} 的区别在于：本类是聚合级别的完整配置快照，不是图拓扑中的节点对象；
 * prompt 与 Summary 节点在发布时统一校验一致，处理建议则随发布正文原样冻结给 Adviser 使用。
 *
 * <p>上游：WorkflowGraphAggregateParser（从 JSON {@code summaryConfig} 字段解析）。
 * <p>下游：WorkflowGraphAggregate、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：Summary 节点执行、FINAL_CONCLUSION Observation 写入。
 */
@Data
@Accessors(chain = true)
public class WorkflowSummaryConfig {

    private String prompt;
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String detailSummaryPrompt;
    private List<WorkflowHandlingSuggestion> handlingSuggestions;
}
