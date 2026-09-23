package dev.a2flow.management.lifecycle.domain;

import java.util.ArrayList;
import java.util.List;

import dev.a2flow.management.lifecycle.domain.graph.CompiledPlan;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphValidationError;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 图编译预览结果。
 *
 * <p>上游由 WorkflowGraphPreviewService 组装；下游供统一 dispatcher 的编译预览方法使用。
 * errors 始终是列表，成功时返回 compiledPlan，失败时 compiledPlan 为空。该模型不改变正式发布与
 * 执行编译的 fail-closed 行为。
 */
@Data
@Accessors(chain = true)
public class WorkflowGraphPreviewResult {

    private CompiledPlan compiledPlan;
    private List<WorkflowGraphValidationError> errors = new ArrayList<>();
}
