package dev.a2flow.management.lifecycle;

import java.util.ArrayList;
import java.util.List;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.domain.WorkflowGraphPreviewResult;
import dev.a2flow.management.lifecycle.domain.graph.CompiledPlan;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowCompiledPlanBuilder;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregate;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregateParser;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphCompilationException;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphDataException;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphValidationError;
import dev.a2flow.management.release.ReleaseAssetType;

import lombok.extern.slf4j.Slf4j;

/**
 * Workflow 图控制面预览服务。
 *
 * <p>上游是 sellerdata 统一 SkillFactory dispatcher 的 WORKFLOW_COMPILED_PLAN_PREVIEW 方法，
 * 下游依次调用稳定授权、强类型 parser、Skill 引用重验和 compiled-plan builder。
 * 预览把可定位错误收敛为 List；JSON 无法解析时无法安全继续图校验，
 * 返回单个 parse 错误；结构解析成功后依次收集相互独立的引用和图编译错误。
 * 正式保存、发布和执行入口仍直接抛异常并失败关闭。
 */
@Service
@Slf4j
public class WorkflowGraphPreviewService {

    private static final String ERROR_CODE_UNKNOWN = "WORKFLOW_GRAPH_VALIDATION_UNKNOWN";
    private static final String ERROR_MESSAGE_UNKNOWN = "Workflow图校验失败";
    private static final String ERROR_CODE_WORKFLOW_CODE_MISMATCH =
            "WORKFLOW_DRAFT_WORKFLOW_CODE_MISMATCH";
    private static final String ERROR_MESSAGE_WORKFLOW_CODE_MISMATCH =
            "草稿内嵌workflowCode与路径参数不一致";
    private static final String FIELD_PATH_WORKFLOW_CODE = "workflowCode";

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private WorkflowDefinitionService workflowDefinitionService;

    /** 预览当前 Workflow 的候选草稿，不写 DB、不创建发布记录。 */
    public WorkflowGraphPreviewResult preview(
            String operator, String workflowCode, String draftPayloadJson) {
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.EDIT);
        List<WorkflowGraphValidationError> errors = new ArrayList<>();
        WorkflowGraphAggregate aggregate;
        try {
            aggregate = WorkflowGraphAggregateParser.parse(draftPayloadJson);
        } catch (WorkflowGraphDataException exception) {
            errors.add(fromDataException(exception));
            return result(null, errors);
        }
        if (!StringUtils.equals(workflowCode, aggregate.getWorkflowCode())) {
            errors.add(new WorkflowGraphValidationError(
                    ERROR_CODE_WORKFLOW_CODE_MISMATCH,
                    ERROR_MESSAGE_WORKFLOW_CODE_MISMATCH,
                    FIELD_PATH_WORKFLOW_CODE, null, null, null));
            return result(null, errors);
        }

        try {
            workflowDefinitionService.validatePreviewSkillReferences(operator, workflowCode, aggregate);
        } catch (WorkflowSkillReferenceValidationException exception) {
            errors.add(new WorkflowGraphValidationError(
                    exception.getErrorCode(), exception.getMessage(), exception.getFieldPath(),
                    exception.getNodeCode(), null, null));
        }

        CompiledPlan plan = null;
        try {
            plan = WorkflowCompiledPlanBuilder.build(aggregate);
        } catch (WorkflowGraphCompilationException exception) {
            errors.add(new WorkflowGraphValidationError(
                    exception.getErrorCode(), exception.getMessage(), exception.getFieldPath(),
                    exception.getNodeCode(), exception.getEdgeId(), exception.getCyclePath()));
        } catch (RuntimeException exception) {
            log.error("Workflow图预览遇到未知编译错误, workflowCode:{}", workflowCode, exception);
            errors.add(new WorkflowGraphValidationError(
                    ERROR_CODE_UNKNOWN, ERROR_MESSAGE_UNKNOWN, null, null, null, null));
        }
        return result(errors.isEmpty() ? plan : null, errors);
    }

    private WorkflowGraphValidationError fromDataException(WorkflowGraphDataException exception) {
        return new WorkflowGraphValidationError(
                exception.getErrorCode(), exception.getMessage(), exception.getFieldPath(),
                null, null, null);
    }

    private WorkflowGraphPreviewResult result(
            CompiledPlan plan, List<WorkflowGraphValidationError> errors) {
        return new WorkflowGraphPreviewResult().setCompiledPlan(plan).setErrors(errors);
    }
}
