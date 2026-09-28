package dev.a2flow.management.a2ui.application;

import java.util.List;
import java.lang.reflect.Method;
import java.util.Map;

import dev.a2flow.management.lifecycle.SkillFactoryMethodDispatcher;
import dev.a2flow.management.model.SkillFactoryExecutionResult;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiLoadBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMessageTemplateBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultAdapter;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultAdapterType;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowTemplate;

/** Offline checks for statically addressable Show/Load DataModel single-source rules. */
public final class A2uiActivationDataSourceContractTest {

    private A2uiActivationDataSourceContractTest() { }

    public static void main(String[] args) throws Exception {
        var compiler = new A2uiApplicationBuildCompiler(digest -> "test-build");

        // Initial template placeholders are not sources; a Load may populate them.
        compiler.validateActivationDataModelSources(show(List.of()), List.of(
                load("a", List.of(adapter("load-status", "main", "/status")), List.of())));

        expectConflict(() -> compiler.validateActivationDataModelSources(
                show(List.of(showBinding(0, "/updateDataModel/value/title"))),
                List.of(load("a", List.of(adapter("load-title", "main", "/title")), List.of()))));
        expectConflict(() -> compiler.validateActivationDataModelSources(
                show(List.of(showBinding(0, "/updateDataModel/value/profile/name"))),
                List.of(load("a", List.of(adapter("load-profile", "main", "/profile")), List.of()))));

        // Same pointer on another surface is independent.
        compiler.validateActivationDataModelSources(
                show(List.of(showBinding(0, "/updateDataModel/value/title"))),
                List.of(load("a", List.of(adapter("load-title", "secondary", "/title")), List.of())));

        expectConflict(() -> compiler.validateActivationDataModelSources(show(List.of()), List.of(
                load("a", List.of(adapter("first-status", "main", "/status")), List.of()),
                load("b", List.of(adapter("second-status", "main", "/status")), List.of()))));

        // One Load's success and failure outcomes are mutually exclusive.
        compiler.validateActivationDataModelSources(show(List.of()), List.of(
                load("a", List.of(adapter("success-status", "main", "/status")),
                        List.of(adapter("failure-status", "main", "/status")))));

        // A failed earlier Load stops the chain, so its failure target cannot meet a later Load.
        compiler.validateActivationDataModelSources(show(List.of()), List.of(
                load("a", List.of(adapter("success-first", "main", "/first")),
                        List.of(adapter("failure-status", "main", "/status"))),
                load("b", List.of(adapter("later-status", "main", "/status")), List.of())));

        // Earlier success state remains when a later Load fails.
        expectConflict(() -> compiler.validateActivationDataModelSources(show(List.of()), List.of(
                load("a", List.of(adapter("success-status", "main", "/status")), List.of()),
                load("b", List.of(adapter("success-second", "main", "/second")),
                        List.of(adapter("failure-status", "main", "/status"))))));

        // Dynamic addresses and PASSTHROUGH targets are deliberately outside static analysis.
        compiler.validateActivationDataModelSources(
                show(List.of(showBinding(0, "/updateDataModel/value/status"))),
                List.of(load("a", List.of(dynamicPathAdapter()), List.of()),
                        load("b", List.of(passthroughAdapter()), List.of())));

        verifyFieldPathProjection();
        System.out.println("A2UI_ACTIVATION_DATA_SOURCE_PASS: static Show/Load conflicts rejected, "
                + "placeholders and mutually exclusive outcomes preserved");
    }

    private static A2uiShowTemplate show(List<A2uiShowInputBinding> bindings) {
        return new A2uiShowTemplate()
                .setMessageTemplates(List.of(updateDataModel("main", "/", Map.of(
                        "title", "", "profile", Map.of("name", ""), "status", ""))))
                .setInputBindings(bindings);
    }

    private static A2uiShowInputBinding showBinding(int messageIndex, String targetPath) {
        return new A2uiShowInputBinding()
                .setTargetMessageIndex(messageIndex)
                .setTargetPath(targetPath)
                .setSource(A2uiShowInputSource.APP_PARAMS)
                .setSourcePath("/value")
                .setRequired(true);
    }

    private static A2uiLoadBinding load(String bindingId, List<A2uiResultAdapter> success,
            List<A2uiResultAdapter> failure) {
        return new A2uiLoadBinding()
                .setBindingId(bindingId)
                .setResultAdapters(success)
                .setFailureResultAdapters(failure);
    }

    private static A2uiResultAdapter adapter(String adapterId, String surfaceId, String path) {
        return new A2uiResultAdapter()
                .setAdapterId(adapterId)
                .setOrder(1)
                .setType(A2uiResultAdapterType.MESSAGE_TEMPLATE)
                .setMessageTemplate(updateDataModel(surfaceId, path, ""))
                .setBindings(List.of());
    }

    private static A2uiResultAdapter dynamicPathAdapter() {
        return new A2uiResultAdapter()
                .setAdapterId("dynamic-path")
                .setOrder(1)
                .setType(A2uiResultAdapterType.MESSAGE_TEMPLATE)
                .setMessageTemplate(updateDataModel("main", "/status", ""))
                .setBindings(List.of(new A2uiMessageTemplateBinding()
                        .setTargetPath("/updateDataModel/path")
                        .setSource(A2uiResultSource.CONSTANT)
                        .setConstantValue("/other")));
    }

    private static A2uiResultAdapter passthroughAdapter() {
        return new A2uiResultAdapter()
                .setAdapterId("passthrough")
                .setOrder(1)
                .setType(A2uiResultAdapterType.A2UI_PASSTHROUGH)
                .setSource(A2uiResultSource.CAPABILITY_DATA)
                .setSourcePath("/messages")
                .setCardinality("MANY");
    }

    private static Map<String, Object> updateDataModel(
            String surfaceId, String path, Object value) {
        return Map.of(
                "version", "v0.9.1",
                "updateDataModel", Map.of(
                        "surfaceId", surfaceId,
                        "path", path,
                        "value", value));
    }

    private static void expectConflict(Runnable action) {
        try {
            action.run();
        } catch (A2uiApplicationValidationException expected) {
            if (!"A2UI_APPLICATION_DRAFT_INVALID".equals(expected.getErrorCode())) {
                throw expected;
            }
            if (expected.getFieldPath() == null
                    || !expected.getFieldPath().startsWith("/activationDataModel/")) {
                throw new AssertionError("conflict omitted its safe fieldPath");
            }
            return;
        }
        throw new AssertionError("competing Activation DataModel sources were accepted");
    }

    private static void verifyFieldPathProjection() throws Exception {
        SkillFactoryMethodDispatcher dispatcher = new SkillFactoryMethodDispatcher();
        Method knownFailure = SkillFactoryMethodDispatcher.class.getDeclaredMethod(
                "knownFailure", Exception.class);
        knownFailure.setAccessible(true);
        SkillFactoryExecutionResult result = (SkillFactoryExecutionResult) knownFailure.invoke(
                dispatcher, new A2uiApplicationValidationException(
                        A2uiApplicationErrorCode.DRAFT_INVALID,
                        "/activationDataModel/show/load/main/status"));
        if (!(result.getData() instanceof Map)
                || !"/activationDataModel/show/load/main/status".equals(
                ((Map<?, ?>) result.getData()).get("fieldPath"))) {
            throw new AssertionError("dispatcher dropped Application fieldPath");
        }
    }
}
