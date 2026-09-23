package dev.a2flow.management.a2ui.application;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultOutcome;

/**
 * 成功分支原始作者态校验器，供 Registry 保存与发布 manifest 解析共用。
 *
 * <p>在 Jackson 反序列化前拒绝非列表、非字符串身份和非布尔完成标记，避免隐式类型转换。
 * 谓词内容、adapter、Action 闭包及交互模式由领域 compiler 校验；本类不读写存储或执行业务。
 */
public final class A2uiSuccessBranchValidator {

    static final int MAX_SUCCESS_BRANCHES = 20;
    static final int MAX_SUCCESS_BRANCH_ID_LENGTH = 64;
    private static final String FIELD_ACTION_BINDINGS = "actionBindings";
    private static final String FIELD_SUCCESS_BRANCHES = "successBranches";
    private static final String FIELD_BRANCH_ID = "branchId";
    private static final String FIELD_WHEN = "when";
    private static final String FIELD_OUTCOME = "outcome";
    private static final String FIELD_RESULT_ADAPTERS = "resultAdapters";
    private static final String FIELD_COMPLETION = "completeWorkflowInteractionOnSuccess";
    private static final Set<String> BRANCH_FIELDS = Set.of(
            FIELD_BRANCH_ID, FIELD_WHEN, FIELD_OUTCOME, FIELD_RESULT_ADAPTERS, FIELD_COMPLETION);

    private A2uiSuccessBranchValidator() {
    }

    /** 缺省或空分支列表表示沿用根管线；显式 null 与错误类型直接拒绝。 */
    public static void validate(Map<String, Object> source) {
        Object rawBindings = source.get(FIELD_ACTION_BINDINGS);
        if (rawBindings == null) {
            return;
        }
        if (!(rawBindings instanceof List)) {
            throw invalid();
        }
        for (Object rawBinding : (List<?>) rawBindings) {
            if (!(rawBinding instanceof Map)) {
                throw invalid();
            }
            Map<?, ?> binding = (Map<?, ?>) rawBinding;
            validateCompletion(binding);
            if (binding.containsKey(FIELD_SUCCESS_BRANCHES)) {
                validateBranches(binding.get(FIELD_SUCCESS_BRANCHES));
            }
        }
    }

    /** 检查单个 Binding 的局部身份及结构，不对分支排序或改写作者态值。 */
    private static void validateBranches(Object rawBranches) {
        if (!(rawBranches instanceof List) || ((List<?>) rawBranches).size() > MAX_SUCCESS_BRANCHES) {
            throw invalid();
        }
        Set<String> branchIds = new HashSet<>();
        for (Object rawBranch : (List<?>) rawBranches) {
            if (!(rawBranch instanceof Map)) {
                throw invalid();
            }
            Map<?, ?> branch = (Map<?, ?>) rawBranch;
            if (!BRANCH_FIELDS.containsAll(branch.keySet())) {
                throw invalid();
            }
            Object branchId = branch.get(FIELD_BRANCH_ID);
            if (!(branchId instanceof String) || StringUtils.isBlank((String) branchId)
                    || ((String) branchId).length() > MAX_SUCCESS_BRANCH_ID_LENGTH
                    || !branchIds.add((String) branchId)) {
                throw invalid();
            }
            if (!(branch.get(FIELD_WHEN) instanceof Map)) {
                throw new A2uiApplicationValidationException(
                        branch.get(FIELD_WHEN) == null
                                ? A2uiApplicationErrorCode.BUSINESS_SUCCESS_PREDICATE_REQUIRED
                                : A2uiApplicationErrorCode.BUSINESS_SUCCESS_PREDICATE_INVALID);
            }
            Object outcome = branch.get(FIELD_OUTCOME);
            if (!A2uiResultOutcome.ADAPTER_PIPELINE.name().equals(outcome)
                    && !A2uiResultOutcome.NO_UI_MESSAGES.name().equals(outcome)
                    || branch.containsKey(FIELD_RESULT_ADAPTERS)
                    && !(branch.get(FIELD_RESULT_ADAPTERS) instanceof List)) {
                throw new A2uiApplicationValidationException(A2uiApplicationErrorCode.RESULT_ADAPTER_INVALID);
            }
            validateCompletion(branch);
        }
    }

    /** 仅布尔值或缺省值可进入完成语义，不接受字符串及数字强转。 */
    private static void validateCompletion(Map<?, ?> source) {
        Object completion = source.get(FIELD_COMPLETION);
        if (completion != null && !(completion instanceof Boolean)) {
            throw invalid();
        }
    }

    private static A2uiApplicationValidationException invalid() {
        return new A2uiApplicationValidationException(A2uiApplicationErrorCode.DRAFT_INVALID);
    }
}
