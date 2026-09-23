package dev.a2flow.management.a2ui.runtime.action;

import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

import org.springframework.stereotype.Component;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledActionBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledBusinessPredicateClause;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledBusinessSuccessPredicate;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledResultAdapter;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultOutcome;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledSuccessBranch;
import dev.a2flow.management.a2ui.runtime.show
        .A2uiJsonPointerValueMapper;
import dev.a2flow.management.a2ui.runtime.show
        .A2uiJsonPointerValueMapper.LookupValue;
import dev.a2flow.management.a2ui.runtime.show
        .A2uiJsonPointerValueMapper.MappingException;
import dev.a2flow.management.a2ui.runtime.capability
        .CapabilityExecutionResult;

import lombok.Value;

/**
 * A2UI Capability 业务成功条件求值器。
 *
 * <p>本类只消费已通过 Artifact Reader 校验的结构化 predicate，并且只读取 Capability data。
 * 路径缺失、显式 null 或运行值类型不兼容均按业务失败处理；它不改变 transport success、
 * 不解释具体业务字段；返回一次性选择的冻结管线与完成意图，Workflow 提交仍由 Gateway 负责。</p>
 */
@Component
public class A2uiCapabilityOutcomeEvaluator {

    private final A2uiJsonPointerValueMapper valueMapper = new A2uiJsonPointerValueMapper();

    /** 先隔离 transport/业务失败，再按声明顺序选首个成功分支，未命中沿用显式根成功管线。 */
    public SelectedOutcome select(A2uiCompiledActionBinding binding, CapabilityExecutionResult result) {
        if (result == null || !result.isSuccess() || !matches(binding.getBusinessSuccessPredicate(), result)) {
            return new SelectedOutcome(false, null, binding.getFailureOutcome(),
                    binding.getFailureResultAdapters(), false);
        }
        // NON_EMPTY 冻结JSON省略空分支；原运行DTO缺省为空列表，保留相同的根成功管线语义。
        for (A2uiCompiledSuccessBranch branch : binding.getSuccessBranches() == null
                ? java.util.List.<A2uiCompiledSuccessBranch>of() : binding.getSuccessBranches()) {
            if (matches(branch.getWhen(), result)) {
                return new SelectedOutcome(true, branch.getBranchId(), branch.getOutcome(),
                        branch.getResultAdapters(), branch.isCompleteWorkflowInteractionOnSuccess());
            }
        }
        return new SelectedOutcome(true, null, binding.getSuccessOutcome(), binding.getResultAdapters(),
                binding.isCompleteWorkflowInteractionOnSuccess());
    }

    /** 无 predicate 的非完成型 Action 保留原 transport-only 语义。 */
    public boolean matches(A2uiCompiledBusinessSuccessPredicate predicate,
            CapabilityExecutionResult capabilityResult) {
        if (predicate == null) {
            return true;
        }
        if (capabilityResult == null) {
            return false;
        }
        Object capabilityData = capabilityResult.getData();
        List<A2uiCompiledBusinessPredicateClause> clauses = predicate.getAllOf();
        for (A2uiCompiledBusinessPredicateClause clause : clauses) {
            if (!matchesClause(capabilityData, clause)) {
                return false;
            }
        }
        return true;
    }

    private boolean matchesClause(Object capabilityData, A2uiCompiledBusinessPredicateClause clause) {
        LookupValue actual;
        try {
            actual = valueMapper.read(capabilityData, clause.getSourcePath());
        } catch (MappingException exception) {
            return false;
        }
        if (!actual.isFound() || actual.getValue() == null) {
            return false;
        }
        Object expected = clause.getExpectedValue();
        if ("EQUALS".equals(clause.getOperator())) {
            return equalsValue(actual.getValue(), expected);
        }
        if ("GREATER_THAN".equals(clause.getOperator())) {
            return greaterThan(actual.getValue(), expected);
        }
        if ("IS_ARRAY".equals(clause.getOperator())) {
            return Boolean.TRUE.equals(expected) && actual.getValue() instanceof List;
        }
        return false;
    }

    private boolean equalsValue(Object actual, Object expected) {
        if (actual instanceof Number && expected instanceof Number) {
            BigDecimal actualNumber = toDecimal(actual);
            BigDecimal expectedNumber = toDecimal(expected);
            return actualNumber != null && expectedNumber != null
                    && actualNumber.compareTo(expectedNumber) == 0;
        }
        return Objects.equals(actual, expected);
    }

    private boolean greaterThan(Object actual, Object expected) {
        BigDecimal actualNumber = toDecimal(actual);
        BigDecimal expectedNumber = toDecimal(expected);
        return actualNumber != null && expectedNumber != null
                && actualNumber.compareTo(expectedNumber) > 0;
    }

    private BigDecimal toDecimal(Object value) {
        if (!(value instanceof Number)) {
            return null;
        }
        try {
            return new BigDecimal(value.toString());
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    /** 同一次结果选择同时驱动渲染和完成，避免两处重复求值产生不同分支。 */
    @Value
    public static class SelectedOutcome {
        private boolean succeeded;
        private String branchId;
        private A2uiResultOutcome outcome;
        private List<A2uiCompiledResultAdapter> adapters;
        private boolean completesWorkflowInteraction;
    }
}
