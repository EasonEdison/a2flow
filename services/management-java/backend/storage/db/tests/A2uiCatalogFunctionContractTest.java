package dev.a2flow.management.a2ui.catalog;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.a2ui.catalog
        .A2uiCatalogFunctionContractValidator.ValidatedFunctionContract;
import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.support.JsonSupport;

/** 不访问数据库，验证 published Catalog 函数 allowlist 与递归 FunctionCall schema 门禁。 */
public final class A2uiCatalogFunctionContractTest {

    private static final String CATALOG_ID = "a2flow.digital-employee.pc.v1";
    private static final String CONTRACT_ID =
            "https://a2flow.dev/catalogs/digital-employee/functions.json";
    private static final String OFFICIAL_CATALOG =
            "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json";
    private static final String COMMON_TYPES =
            "https://a2ui.org/specification/v0_9/common_types.json";

    private A2uiCatalogFunctionContractTest() { }

    public static void main(String[] args) throws Exception {
        A2uiCatalogFunctionContractValidator validator =
                new A2uiCatalogFunctionContractValidator();
        if (args.length == 1) {
            ValidatedFunctionContract actual = validator.validateProjectContract(
                    CATALOG_ID, JsonSupport.fromJSON(
                            Files.readString(Path.of(args[0]), StandardCharsets.UTF_8), Object.class));
            if (actual.functionCodes().size() != 15
                    || !actual.functionCodes().contains("equals")) {
                throw new AssertionError("deployed renderer function contract changed");
            }
        }
        ValidatedFunctionContract project = validator.validateProjectContract(
                CATALOG_ID, projectContract());
        if (!project.functionCodes().equals(List.of("equals", "required"))) {
            throw new AssertionError("project function codes were not server-derived");
        }
        Map<String, Object> catalogInput = new LinkedHashMap<>();
        catalogInput.put("catalogId", CATALOG_ID);
        catalogInput.put("nameCn", "函数合同测试 Catalog");
        catalogInput.put("protocolVersion", "v0.9.1");
        catalogInput.put("componentCodes", List.of("Text"));
        catalogInput.put("functionContract", projectContract());
        ComponentAsset storedCatalog = new A2uiCatalogRegistryService()
                .toManagedRegistryAsset(catalogInput, "admin");
        Map<String, Object> storedSource = source(storedCatalog);
        if (!storedSource.containsKey("functionContract")
                || !List.of("equals", "required").equals(storedSource.get("functionCodes"))) {
            throw new AssertionError("project function contract was not persisted canonically");
        }

        Map<String, Object> nestedRequired = call("required",
                Map.of("value", Map.of("path", "/draftTitle")), "boolean");
        Map<String, Object> equals = call("equals", Map.of(
                "a", nestedRequired,
                "b", Map.of("path", "/savedTitle")), "boolean");
        validator.validateMessageTemplateCalls(messages(equals), project);

        expectInvalid(() -> validator.validateMessageTemplateCalls(
                messages(call("unknown", Map.of(), "boolean")), project));
        expectInvalid(() -> validator.validateMessageTemplateCalls(
                messages(Map.of("call", "equals", "returnType", "boolean")), project));
        expectInvalid(() -> validator.validateMessageTemplateCalls(
                messages(call("equals", Map.of("a", Map.of("path", "/draftTitle")),
                        "boolean")), project));
        expectInvalid(() -> validator.validateMessageTemplateCalls(
                messages(call("equals", Map.of(
                        "a", Map.of("path", "/draftTitle"),
                        "b", Map.of("path", "/savedTitle")), "string")), project));

        Map<String, Object> businessCall = Map.of("updateDataModel", Map.of(
                "surfaceId", "main", "path", "/business",
                "value", Map.of("call", "ordinaryBusinessField", "args", Map.of())));
        validator.validateMessageTemplateCalls(List.of(businessCall), project);

        Map<String, Object> externalReference = projectContract();
        functions(externalReference).put("external", Map.of(
                "$ref", "https://untrusted.example/functions.json#/external"));
        expectInvalid(() -> validator.validateProjectContract(CATALOG_ID, externalReference));
        Map<String, Object> deepContract = projectContract();
        Map<String, Object> deepSchema = Map.of("type", "string");
        for (int depth = 0; depth < 70; depth++) {
            deepSchema = Map.of("allOf", List.of(deepSchema));
        }
        functions(deepContract).put("tooDeep", deepSchema);
        expectInvalid(() -> validator.validateProjectContract(CATALOG_ID, deepContract));

        ComponentAsset official = new A2uiOfficialBasicCatalogImporter()
                .loadLockedSnapshot("admin").getCatalogAsset();
        ValidatedFunctionContract officialContract = validator.publishedContract(
                A2uiOfficialBasicCatalogImporter.CATALOG_ID, source(official));
        if (officialContract.functionCodes().size() != 14
                || officialContract.functionCodes().contains("equals")) {
            throw new AssertionError("locked official function contract changed");
        }
        System.out.println("PASS: published A2UI function contracts and recursive calls");
    }

    private static Map<String, Object> projectContract() {
        Map<String, Object> functions = new LinkedHashMap<>();
        functions.put("required", Map.of("$ref", OFFICIAL_CATALOG + "#/functions/required"));
        functions.put("equals", Map.of(
                "type", "object",
                "properties", Map.of(
                        "call", Map.of("const", "equals"),
                        "args", Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "a", Map.of("$ref", COMMON_TYPES + "#/$defs/DynamicValue"),
                                        "b", Map.of("$ref", COMMON_TYPES + "#/$defs/DynamicValue")),
                                "required", List.of("a", "b"),
                                "unevaluatedProperties", false),
                        "returnType", Map.of("const", "boolean")),
                "required", List.of("call", "args"),
                "unevaluatedProperties", false));
        Map<String, Object> contract = new LinkedHashMap<>();
        contract.put("$schema", "https://json-schema.org/draft/2020-12/schema");
        contract.put("$id", CONTRACT_ID);
        contract.put("catalogId", CATALOG_ID);
        contract.put("functions", functions);
        contract.put("$defs", Map.of("anyFunction", Map.of("oneOf", List.of(
                Map.of("$ref", "#/functions/required"),
                Map.of("$ref", "#/functions/equals")))));
        return contract;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> functions(Map<String, Object> contract) {
        return (Map<String, Object>) contract.get("functions");
    }

    private static Map<String, Object> call(
            String function, Map<String, Object> args, String returnType) {
        return Map.of("call", function, "args", args, "returnType", returnType);
    }

    private static List<Map<String, Object>> messages(Map<String, Object> expression) {
        return List.of(Map.of("updateComponents", Map.of("surfaceId", "main", "components",
                List.of(Map.of("id", "button", "component", "Button",
                        "checks", List.of(Map.of("condition", expression,
                                "message", "check failed")))))));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> source(ComponentAsset asset) {
        return JsonSupport.fromJSON(asset.getRuntimeConfigJson(), Map.class);
    }

    private static void expectInvalid(Runnable runnable) {
        try {
            runnable.run();
            throw new AssertionError("invalid function contract or call was accepted");
        } catch (A2uiRegistryValidationException expected) { }
    }
}
