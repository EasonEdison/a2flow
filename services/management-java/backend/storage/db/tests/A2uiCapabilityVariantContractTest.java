package dev.a2flow.management.a2ui.application;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCurrentCapabilityContract;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCurrentCapabilityVariantContract;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMappingSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMessageTemplateBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiRequestMapping;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiSideEffectLevel;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowTemplate;
import dev.a2flow.management.model.CapabilityActionDraft;

/** Published client variants are preserved and every declared schema is validated. */
public final class A2uiCapabilityVariantContractTest {
    private static final String ACTION_CODE = "content.project.create";
    private static final Map<String, Object> RESULT_CONTRACT = Map.of(
            "technicalOutputSchema", Map.of("type", "object"));

    public static void main(String[] args) {
        var resolver = new A2uiCurrentCapabilityResolver();
        var compiler = new A2uiApplicationBuildCompiler(digest -> "test-build");

        A2uiCurrentCapabilityContract pc = resolver.contract(
                draft(List.of("PC"), variants("PC", modelContract("title"))), ACTION_CODE);
        check(pc.getClientVariants().keySet().equals(java.util.Set.of("PC")),
                "PC capability was rewritten as COMMON");
        compiler.validateCapabilitySchemas(pc, mappings("title"), Map.of(), null);

        A2uiCurrentCapabilityContract legacyCommon = new A2uiCurrentCapabilityContract(
                ACTION_CODE, modelContract("title"), RESULT_CONTRACT, A2uiSideEffectLevel.READ_ONLY);
        check(legacyCommon.getClientVariants().containsKey("COMMON"),
                "legacy COMMON constructor did not enter typed variants");
        compiler.validateCapabilitySchemas(legacyCommon, mappings("title"), Map.of(), null);

        LinkedHashMap<String, Object> different = new LinkedHashMap<>();
        different.put("APP", variant(modelContract("body")));
        different.put("PC", variant(modelContract("title")));
        A2uiCurrentCapabilityContract pcAndApp = resolver.contract(
                draft(List.of("PC", "APP"), different), ACTION_CODE);
        check(pcAndApp.getClientVariants().keySet().equals(
                new java.util.LinkedHashSet<>(List.of("PC", "APP"))),
                "declared variant order changed");
        mustSchemaFailure(() -> compiler.validateCapabilitySchemas(
                pcAndApp, mappings("title"), Map.of(), null));

        LinkedHashMap<String, A2uiCurrentCapabilityVariantContract> reversedTyped = new LinkedHashMap<>();
        reversedTyped.put("APP", typedVariant("APP", "title"));
        reversedTyped.put("PC", typedVariant("PC", "title"));
        compiler.validateCapabilitySchemas(new A2uiCurrentCapabilityContract(
                ACTION_CODE, reversedTyped, A2uiSideEffectLevel.READ_ONLY),
                mappings("title"), Map.of(), null);

        LinkedHashMap<String, Object> missing = new LinkedHashMap<>();
        missing.put("PC", variant(modelContract("title")));
        mustSchemaFailure(() -> resolver.contract(
                draft(List.of("PC", "APP"), missing), ACTION_CODE));
        LinkedHashMap<String, Object> extra = variants("PC", modelContract("title"));
        extra.put("APP", variant(modelContract("title")));
        mustSchemaFailure(() -> resolver.contract(draft(List.of("PC"), extra), ACTION_CODE));
        verifyPhaseLocalSingleSource(compiler);
        System.out.println("A2UI_CAPABILITY_VARIANTS_PASS: PC preserved, COMMON compatible, "
                + "map order ignored, all variants validated, missing and extra keys rejected");
    }

    private static void verifyPhaseLocalSingleSource(A2uiApplicationBuildCompiler compiler) {
        A2uiShowInputBinding title = showBinding(0, "/updateDataModel/value/title");
        A2uiShowInputBinding titleChild = showBinding(0, "/updateDataModel/value/title/value");
        mustValidationFailure("A2UI_SHOW_INVALID", () ->
                new A2uiShowTemplateAnalyzer().validateInputBindings(new A2uiShowTemplate()
                        .setMessageTemplates(List.of(Map.of()))
                        .setInputBindings(List.of(title, titleChild))));
        new A2uiShowTemplateAnalyzer().validateInputBindings(new A2uiShowTemplate()
                .setMessageTemplates(List.of(Map.of(), Map.of()))
                .setInputBindings(List.of(title, showBinding(1, title.getTargetPath()))));

        compiler.validateRequestMappingTargets(List.of(
                mapping("/profile/name"), mapping("/profile/age")));
        mustValidationFailure("A2UI_APPLICATION_DRAFT_INVALID", () ->
                compiler.validateRequestMappingTargets(List.of(
                        mapping("/title"), mapping("/request/title"))));
        mustValidationFailure("A2UI_APPLICATION_DRAFT_INVALID", () ->
                compiler.validateRequestMappingTargets(List.of(
                        mapping("/profile"), mapping("/request/profile/name"))));

        A2uiMessageTemplateBinding parent = new A2uiMessageTemplateBinding()
                .setTargetPath("/updateDataModel/value/export")
                .setSource(A2uiResultSource.CONSTANT)
                .setConstantValue(Map.of());
        A2uiMessageTemplateBinding child = new A2uiMessageTemplateBinding()
                .setTargetPath("/updateDataModel/value/export/content")
                .setSource(A2uiResultSource.CONSTANT)
                .setConstantValue("text");
        mustValidationFailure("A2UI_RESULT_ADAPTER_INVALID", () ->
                compiler.validateMessageTemplateBindingTargets(List.of(parent, child)));
    }

    private static A2uiShowInputBinding showBinding(int messageIndex, String targetPath) {
        return new A2uiShowInputBinding()
                .setTargetMessageIndex(messageIndex)
                .setTargetPath(targetPath)
                .setSource(A2uiShowInputSource.APP_PARAMS)
                .setSourcePath("/title")
                .setRequired(true);
    }

    private static A2uiRequestMapping mapping(String targetPath) {
        return new A2uiRequestMapping()
                .setSource(A2uiMappingSource.CONSTANT)
                .setTargetPath(targetPath)
                .setConstantValue("test");
    }

    private static A2uiCurrentCapabilityVariantContract typedVariant(String client, String field) {
        return new A2uiCurrentCapabilityVariantContract(
                client, modelContract(field), RESULT_CONTRACT);
    }

    private static CapabilityActionDraft draft(List<String> supportedClients,
            LinkedHashMap<String, Object> clientVariants) {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("supportedClients", supportedClients);
        root.put("clientVariants", clientVariants);
        root.put("governance", Map.of("sideEffectLevel", "READ"));
        return new CapabilityActionDraft().setDraft(root);
    }

    private static LinkedHashMap<String, Object> variants(
            String client, Map<String, Object> modelContract) {
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        result.put(client, variant(modelContract));
        return result;
    }

    private static Map<String, Object> variant(Map<String, Object> modelContract) {
        return Map.of("modelContract", modelContract, "resultContract", RESULT_CONTRACT);
    }

    private static Map<String, Object> modelContract(String requiredField) {
        return Map.of("inputFields", List.of(Map.of(
                "toolField", requiredField,
                "type", "string",
                "source", "MODEL_INPUT",
                "required", true)));
    }

    private static List<A2uiRequestMapping> mappings(String targetField) {
        return List.of(new A2uiRequestMapping()
                .setSource(A2uiMappingSource.CONSTANT)
                .setTargetPath("/request/" + targetField)
                .setConstantValue("test"));
    }

    private static void mustSchemaFailure(Runnable action) {
        try {
            action.run();
        } catch (A2uiApplicationValidationException expected) {
            check("A2UI_CAPABILITY_SCHEMA_INCOMPATIBLE".equals(expected.getErrorCode()),
                    "unexpected error code: " + expected.getErrorCode());
            return;
        }
        throw new AssertionError("incompatible capability variants were accepted");
    }

    private static void mustValidationFailure(String errorCode, Runnable action) {
        try {
            action.run();
        } catch (A2uiApplicationValidationException expected) {
            check(errorCode.equals(expected.getErrorCode()),
                    "unexpected error code: " + expected.getErrorCode());
            return;
        }
        throw new AssertionError("conflicting target paths were accepted");
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
