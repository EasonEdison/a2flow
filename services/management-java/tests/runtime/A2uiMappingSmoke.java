import java.util.List;
import java.util.Map;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledBusinessPredicateClause;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledActionBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledSuccessBranch;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledBusinessSuccessPredicate;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledRequestMapping;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledRequestTransform;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMappingSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiRequestTransformType;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultOutcome;
import dev.a2flow.management.a2ui.runtime.action.A2uiCapabilityOutcomeEvaluator;
import dev.a2flow.management.a2ui.runtime.capability.CapabilityExecutionResult;
import dev.a2flow.management.a2ui.runtime.mapping.A2uiCapabilityRequestMapper;
import dev.a2flow.management.a2ui.runtime.mapping.A2uiCapabilityRequestMapper.MappingException;
import dev.a2flow.management.a2ui.runtime.mapping.A2uiCapabilityRequestMapper.MappingInputs;

/** 独立核心冒烟入口：不连接业务后端，不把本验证当作 RPC 或页面联调。 */
public final class A2uiMappingSmoke {
    public static void main(String[] args) {
        var mapper = new A2uiCapabilityRequestMapper();
        long userId = Long.MAX_VALUE;
        var input = new MappingInputs(Map.of("userId", 7, "title", "click"),
                Map.of("title", "params", "items", List.of("a", "b"), "mask", List.of(false, true)),
                Map.of("data", Map.of("count", 2)), userId, "PC", "operator", "PRT");
        var fields = List.of(
                field(A2uiMappingSource.TRUSTED_CONTEXT, "/userId", "/userId"),
                field(A2uiMappingSource.ACTION_CONTEXT, "/title", "/clicked"),
                field(A2uiMappingSource.APP_PARAMS, "/title", "/original"),
                field(A2uiMappingSource.CAPABILITY_PREVIOUS_RESULT, "/data/count", "/count"),
                new A2uiCompiledRequestMapping(A2uiMappingSource.CONSTANT, null, "/constant", 3));
        var result = mapper.map(fields, input);
        require(result.equals(Map.of("userId", userId, "clicked", "click", "original", "params",
                "count", 2, "constant", 3)), "source isolation and signed64 userId");
        var filter = new A2uiCompiledRequestMapping(A2uiMappingSource.APP_PARAMS, "/items", "/selected",
                null, new A2uiCompiledRequestTransform(A2uiRequestTransformType.ARRAY_FILTER_BY_BOOLEAN_MASK,
                null, "/mask"));
        require(mapper.map(List.of(filter), input).get("selected").equals(List.of("b")), "boolean mask");
        expectFailure(() -> mapper.map(List.of(fields.get(0), fields.get(0)), input), "target conflict");
        expectFailure(() -> mapper.map(List.of(field(A2uiMappingSource.APP_PARAMS, "/absent", "/x")), input),
                "missing source");
        expectFailure(() -> mapper.map(fields, new MappingInputs(Map.of(), Map.of(), null,
                userId, "PC", "operator", "PRT", Map.of("userId", 7))), "reserved trusted override");
        var evaluator = new A2uiCapabilityOutcomeEvaluator();
        var predicate = new A2uiCompiledBusinessSuccessPredicate("v1", List.of(
                new A2uiCompiledBusinessPredicateClause("CAPABILITY_DATA", "/result", "EQUALS", 1)));
        require(evaluator.matches(predicate, CapabilityExecutionResult.builder().data(Map.of("result", 1L)).build()),
                "numeric predicate");
        require(!evaluator.matches(predicate, CapabilityExecutionResult.builder().data(Map.of("result", "1")).build()),
                "no string to number coercion");
        require(!evaluator.matches(predicate, CapabilityExecutionResult.builder().data(Map.of()).build()),
                "missing predicate field fails");
        var binding = new A2uiCompiledActionBinding("binding", "surface", "button", "submit", "digest",
                List.of("button"), Map.of(), null, List.of(), A2uiResultOutcome.NO_UI_MESSAGES,
                A2uiResultOutcome.NO_UI_MESSAGES, List.of(), List.of(), predicate, false, List.of(
                new A2uiCompiledSuccessBranch("first", predicate, A2uiResultOutcome.NO_UI_MESSAGES, List.of(), true),
                new A2uiCompiledSuccessBranch("second", predicate, A2uiResultOutcome.NO_UI_MESSAGES, List.of(), false)));
        var selected = evaluator.select(binding,
                CapabilityExecutionResult.builder().success(true).data(Map.of("result", 1)).build());
        require(selected.isSucceeded() && "first".equals(selected.getBranchId())
                && selected.isCompletesWorkflowInteraction(), "first matching branch and same completion intent");
        var failed = evaluator.select(binding,
                CapabilityExecutionResult.builder().success(false).data(Map.of("result", 1)).build());
        require(!failed.isSucceeded() && !failed.isCompletesWorkflowInteraction(),
                "transport failure cannot be overridden by business payload");
        System.out.println("A2UI_MAPPING_SMOKE_OK: sources, long userId, transforms, rejection and predicates");
    }

    private static A2uiCompiledRequestMapping field(A2uiMappingSource source, String from, String to) {
        return new A2uiCompiledRequestMapping(source, from, to, null);
    }

    private static void require(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    private static void expectFailure(Runnable operation, String name) {
        try {
            operation.run();
        } catch (MappingException expected) {
            return;
        }
        throw new AssertionError(name);
    }
}
