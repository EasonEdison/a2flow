import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.*;
import dev.a2flow.management.a2ui.runtime.adapter.A2uiResultAdapterEngine;
import dev.a2flow.management.a2ui.runtime.capability.CapabilityExecutionResult;
import dev.a2flow.management.a2ui.runtime.ledger.A2uiMessageSnapshotReducer;
import dev.a2flow.management.a2ui.runtime.ledger.A2uiRuntimeSurfaceLedger;

/** 纯确定性结果适配冒烟检查；不调用网络或业务服务。 */
public final class A2uiAdapterSmoke {
    private static final A2uiResultAdapterEngine ENGINE = new A2uiResultAdapterEngine();
    private static final A2uiMessageSnapshotReducer REDUCER = new A2uiMessageSnapshotReducer();
    private static int checks;

    public static void main(String[] args) {
        A2uiRuntimeSurfaceLedger ledger = REDUCER.reduce(A2uiRuntimeSurfaceLedger.empty(),
                List.of(message("createSurface", Map.of("surfaceId", "s"))));
        var original = REDUCER.toSnapshotMessages(ledger);
        equal("12.5", transform(ledger, A2uiResultTransformType.NUMBER_TO_STRING,
                new BigDecimal("12.500"), null, null, null));
        rejects(() -> transform(ledger, A2uiResultTransformType.NUMBER_TO_STRING, "12", null, null, null));
        equal("1.23", transform(ledger, A2uiResultTransformType.MINOR_UNIT_TO_DECIMAL_STRING,
                123, 2, null, null));
        rejects(() -> transform(ledger, A2uiResultTransformType.MINOR_UNIT_TO_DECIMAL_STRING,
                new BigDecimal("1.2"), 2, null, null));
        rejects(() -> transform(ledger, A2uiResultTransformType.MINOR_UNIT_TO_DECIMAL_STRING,
                123, 3, null, null));
        equal(2, transform(ledger, A2uiResultTransformType.BOOLEAN_ARRAY_TRUE_COUNT,
                List.of(true, false, true), null, null, null));
        rejects(() -> transform(ledger, A2uiResultTransformType.BOOLEAN_ARRAY_TRUE_COUNT,
                List.of(true, "true"), null, null, null));
        var pagination = (Map<?, ?>) transform(ledger, A2uiResultTransformType.PAGINATION_STATE,
                21, null, null, 2);
        equal(3L, pagination.get("totalPages"));
        equal(2, pagination.get("pageNum"));
        rejects(() -> transform(ledger, A2uiResultTransformType.PAGINATION_STATE,
                21, null, null, 4));
        equal(List.of("first", "second"), transform(ledger,
                A2uiResultTransformType.ARRAY_TO_CHILDREN_PREFIX,
                List.of("ignored", "ignored", "ignored"), null, List.of("first", "second"), null));
        rejects(() -> transform(ledger, A2uiResultTransformType.ARRAY_TO_CHILDREN_PREFIX,
                List.of(1), null, List.of("duplicate", "duplicate"), null));

        var pass = passthrough();
        var update = message("updateDataModel", Map.of("surfaceId", "s", "path", "/", "value", Map.of("ok", true)));
        var success = ENGINE.adapt(ledger, A2uiResultOutcome.ADAPTER_PIPELINE, List.of(pass),
                result(List.of(update)), Map.of(), Map.of());
        equal(List.of(update), success.toWireMessages());
        equal(2, REDUCER.toSnapshotMessages(success.getNextLedger()).size());
        // 第一条消息已更新 staging；第二条引用不存在的 Surface，整批失败且原账本保持逐字段相同。
        var invalid = message("updateDataModel", Map.of("surfaceId", "missing", "path", "/", "value", 1));
        rejects(() -> ENGINE.adapt(ledger, A2uiResultOutcome.ADAPTER_PIPELINE, List.of(pass),
                result(List.of(update, invalid)), Map.of(), Map.of()));
        equal(original, REDUCER.toSnapshotMessages(ledger));
        System.out.println("A2UI_ADAPTER_SMOKE_PASS checks=" + checks);
    }

    private static Object transform(A2uiRuntimeSurfaceLedger ledger, A2uiResultTransformType type,
            Object value, Integer scale, List<String> children, Integer page) {
        boolean child = type == A2uiResultTransformType.ARRAY_TO_CHILDREN_PREFIX;
        var transform = new A2uiCompiledResultTransform(type, scale, children,
                type == A2uiResultTransformType.PAGINATION_STATE ? 10 : null, page, null);
        String target = child ? "/updateComponents/components/0/children" : "/updateDataModel/value";
        var binding = new A2uiCompiledMessageTemplateBinding(target, A2uiResultSource.CAPABILITY_DATA,
                "/value", true, null, transform);
        var template = child
                ? message("updateComponents", Map.of("surfaceId", "s", "components",
                        List.of(Map.of("id", "root", "component", "Column", "children", List.of()))))
                : message("updateDataModel", Map.of("surfaceId", "s", "path", "/", "value", "initial"));
        var adapter = new A2uiCompiledResultAdapter("template", 1, A2uiResultAdapterType.MESSAGE_TEMPLATE,
                "template", "1", "digest", template, List.of(binding), null, null, null, true, List.of());
        var batch = ENGINE.adapt(ledger, A2uiResultOutcome.ADAPTER_PIPELINE, List.of(adapter),
                result(Map.of("value", value)), Map.of(), Map.of());
        var body = (Map<?, ?>) batch.toWireMessages().get(0).get(child ? "updateComponents" : "updateDataModel");
        if (!child) {
            return body.get("value");
        }
        return ((Map<?, ?>) ((List<?>) body.get("components")).get(0)).get("children");
    }

    private static A2uiCompiledResultAdapter passthrough() {
        return new A2uiCompiledResultAdapter("pass", 1, A2uiResultAdapterType.A2UI_PASSTHROUGH,
                null, null, null, null, List.of(), A2uiResultSource.CAPABILITY_DATA,
                "/messages", "MANY", true, List.of());
    }

    private static CapabilityExecutionResult result(Object value) {
        return CapabilityExecutionResult.builder().success(true)
                .data(value instanceof List<?> ? Map.of("messages", value) : value).build();
    }

    private static Map<String, Object> message(String operation, Map<String, Object> body) {
        return Map.of("version", "v0.9.1", operation, body);
    }

    private static void equal(Object expected, Object actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError("Expected " + expected + " but got " + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (A2uiResultAdapterEngine.AdapterException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected adapter rejection");
    }
}
