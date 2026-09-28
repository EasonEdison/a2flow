package dev.a2flow.management.skillfactory.a2ui;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationBuild;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationCatalogRef;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationDraft;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowTemplate;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiSurfaceDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledCatalogRef;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledShowInputBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledSurfaceDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiInteractionMode;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationBuildCompiler;
import dev.a2flow.management.a2ui.application.A2uiApplicationValidationException;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogFunctionContractValidator;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogFunctionContractValidator.ValidatedFunctionContract;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogModels.A2uiCatalogComponentContract;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogSourceType;
import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;
import dev.a2flow.management.a2ui.runtime.show.A2uiApplicationShowRenderer;
import dev.a2flow.management.a2ui.runtime.show.A2uiApplicationShowRenderer.Code;
import dev.a2flow.management.a2ui.runtime.show.A2uiApplicationShowRenderer.RenderException;
import dev.a2flow.management.a2ui.runtime.show.A2uiApplicationShowRenderer.TrustedShowContext;

/** Offline contract checks for locked official component schemas and Show input binding values. */
public final class A2uiOfficialComponentSchemaValidatorTest {

    private static final String OFFICIAL_CATALOG =
            "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json";
    private static final String MANAGED_CATALOG = "a2flow.digital-employee.pc.v1";

    private A2uiOfficialComponentSchemaValidatorTest() { }

    public static void main(String[] args) {
        A2uiOfficialComponentSchemaValidator validator =
                new A2uiOfficialComponentSchemaValidator();
        Map<String, A2uiComponentOriginType> origins =
                Map.of("ChoicePicker", A2uiComponentOriginType.A2UI_OFFICIAL);

        validator.validateMessages(messages(List.of(), Map.of("path", "/selection")), origins);
        validator.validateMessages(messages(List.of(
                Map.of("label", "One", "value", "one")), Map.of("path", "/selection")), origins);
        expectInvalid(() -> validator.validateMessages(
                messages(Map.of("path", "/options"), Map.of("path", "/selection")), origins));
        verifyManagedFunctionAuthority(validator);

        verifyCompilerGate();
        verifyRenderedBinding(List.of(Map.of("label", "One", "value", "one")), true);
        verifyRenderedBinding(List.of(Map.of("label", "missing-value")), false);
        System.out.println("PASS: locked official props, managed functions, and Show binding validation");
    }

    private static void verifyManagedFunctionAuthority(
            A2uiOfficialComponentSchemaValidator validator) {
        Map<String, Object> contract = managedFunctionContract();
        ValidatedFunctionContract validated = new A2uiCatalogFunctionContractValidator()
                .validateProjectContract(MANAGED_CATALOG, contract);
        Map<String, A2uiComponentOriginType> origins =
                Map.of("Button", A2uiComponentOriginType.A2UI_OFFICIAL);
        Map<String, Object> equals = functionCall("equals", Map.of(
                "a", Map.of("path", "/draftTitle"),
                "b", Map.of("path", "/savedTitle")));

        // Manifest compilation consumes the already validated immutable authority.
        validator.validateMessages(buttonMessages(equals), origins, validated);
        // Show rendering revalidates the same authority frozen into the Build.
        validator.validateMessages(buttonMessages(equals), origins, MANAGED_CATALOG,
                A2uiCatalogSourceType.PLATFORM_MANAGED, contract);

        expectInvalid(() -> validator.validateMessages(buttonMessages(
                functionCall("unknown", Map.of("a", "x", "b", "x"))), origins, validated));
        expectInvalid(() -> validator.validateMessages(buttonMessages(
                functionCall("equals", Map.of("a", "x"))), origins, validated));
    }

    private static Map<String, Object> managedFunctionContract() {
        Map<String, Object> dynamicValue = Map.of("$ref", "#/$defs/operand");
        Map<String, Object> equals = Map.of(
                "type", "object",
                "properties", Map.of(
                        "call", Map.of("const", "equals"),
                        "args", Map.of(
                                "type", "object",
                                "properties", Map.of(
                                        "a", dynamicValue,
                                        "b", dynamicValue),
                                "required", List.of("a", "b"),
                                "additionalProperties", false),
                        "returnType", Map.of("const", "boolean")),
                "required", List.of("call", "args"),
                "unevaluatedProperties", false);
        return Map.of(
                "$schema", "https://json-schema.org/draft/2020-12/schema",
                "$id", "https://a2flow.dev/catalogs/digital-employee/functions.json",
                "catalogId", MANAGED_CATALOG,
                "$defs", Map.of("operand", Map.of("$ref",
                        "https://a2ui.org/specification/v0_9/common_types.json#/$defs/DynamicValue")),
                "functions", Map.of("equals", equals));
    }

    private static Map<String, Object> functionCall(String call, Map<String, Object> args) {
        return Map.of("call", call, "args", args, "returnType", "boolean");
    }

    private static List<Map<String, Object>> buttonMessages(Object condition) {
        return List.of(Map.of(
                "version", "v0.9.1",
                "updateComponents", Map.of(
                        "surfaceId", "main",
                        "components", List.of(Map.of(
                                "id", "confirm-button",
                                "component", "Button",
                                "child", "confirm-label",
                                "variant", "primary",
                                "action", Map.of("event", Map.of(
                                        "name", "confirmManuscript")),
                                "checks", List.of(Map.of(
                                        "condition", condition,
                                        "message", "请先保存修改")))))));
    }

    private static void verifyCompilerGate() {
        A2uiApplicationBuildCompiler compiler =
                new A2uiApplicationBuildCompiler(digest -> "test-build");
        compiler.compile(draft(List.of()), List.of(catalogComponent()), Map.of());
        try {
            compiler.compile(draft(Map.of("path", "/options")),
                    List.of(catalogComponent()), Map.of());
            throw new AssertionError("compiler accepted invalid official options object");
        } catch (A2uiApplicationValidationException exception) {
            if (!"A2UI_APPLICATION_DRAFT_INVALID".equals(exception.getErrorCode())) {
                throw exception;
            }
        }
    }

    private static A2uiApplicationDraft draft(Object options) {
        A2uiApplicationCatalogRef catalog = new A2uiApplicationCatalogRef()
                .setCatalogId(OFFICIAL_CATALOG)
                .setRevision("1")
                .setDigest("digest")
                .setCatalogSourceType(A2uiCatalogSourceType.A2UI_OFFICIAL)
                .setComponentOrigins(Map.of(
                        "ChoicePicker", A2uiComponentOriginType.A2UI_OFFICIAL));
        A2uiShowInputBinding binding = new A2uiShowInputBinding()
                .setTargetMessageIndex(1)
                .setTargetPath("/updateComponents/components/8/options")
                .setSource(A2uiShowInputSource.APP_PARAMS)
                .setSourcePath("/options")
                .setRequired(true);
        A2uiShowTemplate show = new A2uiShowTemplate()
                .setTemplateCode("show")
                .setParamsSchema(paramsSchema())
                .setSurfaceDeclarations(List.of(new A2uiSurfaceDeclaration()
                        .setSurfaceId("main")
                        .setRootComponentId("choice-8")))
                .setMessageTemplates(messages(options, Map.of("path", "/selection")))
                .setInputBindings(List.of(binding));
        return new A2uiApplicationDraft()
                .setAppCode("official-choice-test")
                .setNameCn("官方选择组件测试")
                .setDescription("locked schema contract")
                .setCatalogId(OFFICIAL_CATALOG)
                .setProtocolVersion("v0.9.1")
                .setProtocolStatus("CURRENT_PRODUCTION")
                .setProtocolSourceCommit("420c6183c400e4b84fe3f9e084906725062a6d56")
                .setProtocolSchemaDigests(Map.of("messages", "digest"))
                .setCatalog(catalog)
                .setShowTemplate(show);
    }

    private static A2uiCatalogComponentContract catalogComponent() {
        return new A2uiCatalogComponentContract()
                .setComponentCode("official.choice-picker")
                .setType("ChoicePicker")
                .setComponentOriginType(A2uiComponentOriginType.A2UI_OFFICIAL)
                .setCatalogId(OFFICIAL_CATALOG)
                .setCatalogRevision("1")
                .setCatalogDigest("digest");
    }

    private static void verifyRenderedBinding(Object options, boolean valid) {
        A2uiApplicationShowRenderer renderer = new A2uiApplicationShowRenderer();
        try {
            List<Map<String, Object>> rendered = renderer.render(
                    build(), Map.of("options", options),
                    new TrustedShowContext(1L, "PC", null, "PRT"));
            if (!valid) {
                throw new AssertionError("invalid rendered options passed official schema");
            }
            Object actual = component(rendered).get("options");
            if (!options.equals(actual)) {
                throw new AssertionError("Show binding did not inject concrete options");
            }
        } catch (RenderException exception) {
            if (valid || exception.getCode() != Code.MESSAGE_INVALID) {
                throw exception;
            }
        }
    }

    private static Map<String, Object> paramsSchema() {
        return Map.of(
                "type", "object",
                "properties", Map.of("options", Map.of(
                        "type", "array", "items", Map.of("type", "object"))),
                "required", List.of("options"));
    }

    private static A2uiApplicationBuild build() {
        Map<String, Object> paramsSchema = paramsSchema();
        A2uiCompiledCatalogRef catalog = new A2uiCompiledCatalogRef(
                "a2flow.digital-employee.pc.v1", "1", "digest",
                A2uiCatalogSourceType.PLATFORM_MANAGED,
                Map.of("ChoicePicker", A2uiComponentOriginType.A2UI_OFFICIAL),
                Map.of());
        A2uiCompiledShowInputBinding binding = new A2uiCompiledShowInputBinding(
                1, "/updateComponents/components/8/options",
                A2uiShowInputSource.APP_PARAMS, "/options", true, null);
        return new A2uiApplicationBuild(
                "build", "app", "locked schema contract", "source", "v0.9.1", "CURRENT_PRODUCTION",
                "420c6183c400e4b84fe3f9e084906725062a6d56",
                Map.of("messages", "digest"), "PRT", catalog, "show", "show-digest",
                paramsSchema,
                List.of(new A2uiCompiledSurfaceDeclaration("main", "choice-8")),
                messages(List.of(), Map.of("path", "/selection")),
                List.of(binding), List.of("ChoicePicker"), List.of(), List.of(),
                List.of(), List.of(), A2uiInteractionMode.INTERACTIVE);
    }

    private static List<Map<String, Object>> messages(Object options, Object value) {
        List<Map<String, Object>> result = new ArrayList<>();
        result.add(Map.of(
                "version", "v0.9.1",
                "createSurface", Map.of(
                        "surfaceId", "main",
                        "catalogId", OFFICIAL_CATALOG)));
        List<Map<String, Object>> choices = new ArrayList<>();
        for (int index = 0; index < 9; index++) {
            Map<String, Object> choice = new LinkedHashMap<>();
            choice.put("id", "choice-" + index);
            choice.put("component", "ChoicePicker");
            choice.put("options", index == 8 ? options : List.of());
            choice.put("value", value);
            choice.put("variant", "multipleSelection");
            choices.add(choice);
        }
        result.add(Map.of(
                "version", "v0.9.1",
                "updateComponents", Map.of(
                        "surfaceId", "main",
                        "components", choices)));
        result.add(Map.of(
                "version", "v0.9.1",
                "updateDataModel", Map.of(
                        "surfaceId", "main",
                        "path", "/",
                        "value", Map.of("selection", List.of()))));
        return result;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> component(List<Map<String, Object>> messages) {
        Map<String, Object> update = (Map<String, Object>) messages.get(1).get("updateComponents");
        return (Map<String, Object>) ((List<?>) update.get("components")).get(8);
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
            throw new AssertionError("invalid official component passed");
        } catch (A2uiOfficialComponentSchemaValidator.ValidationException expected) {
            // expected
        }
    }
}
