package dev.a2flow.management.a2ui.application;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCurrentCapabilityContract;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMappingSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiRequestMapping;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiSideEffectLevel;
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
        different.put("PC", variant(modelContract("title")));
        different.put("APP", variant(modelContract("body")));
        A2uiCurrentCapabilityContract pcAndApp = resolver.contract(
                draft(List.of("PC", "APP"), different), ACTION_CODE);
        check(pcAndApp.getClientVariants().keySet().equals(
                new java.util.LinkedHashSet<>(List.of("PC", "APP"))),
                "declared variant order changed");
        mustSchemaFailure(() -> compiler.validateCapabilitySchemas(
                pcAndApp, mappings("title"), Map.of(), null));

        mustSchemaFailure(() -> resolver.contract(
                draft(List.of("PC"), variants("COMMON", modelContract("title"))), ACTION_CODE));
        System.out.println("A2UI_CAPABILITY_VARIANTS_PASS: PC preserved, COMMON compatible, "
                + "all declared variants validated, mismatched declarations rejected");
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

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
