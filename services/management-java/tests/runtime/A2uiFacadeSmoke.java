import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.*;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogSourceType;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiActionInvocation;
import dev.a2flow.management.a2ui.runtime.*;
import dev.a2flow.management.a2ui.runtime.A2uiRuntimeContracts.*;
import dev.a2flow.management.capabilityrpc.*;
import dev.a2flow.management.model.CapabilityToolResult;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.support.JsonSupport;

/** 纯计算测试替身，不代表业务 RPC 或已部署联调。 */
public class A2uiFacadeSmoke {
    static int checks;
    public static void main(String[] args) throws Exception {
        var build = build();
        // 验证生产 provider 的实际完整构造器解码，非另造测试 codec。
        var provider = new ReleaseStatePublishedApplicationProvider(null, null);
        var field = provider.getClass().getDeclaredField("mapper");
        field.setAccessible(true);
        var codec = (ObjectMapper) field.get(provider);
        var decoded = codec.readValue(JsonSupport.toJSON(build), A2uiApplicationBuild.class);
        check(JsonSupport.mapper().readTree(JsonSupport.toJSON(build)).equals(
                JsonSupport.mapper().readTree(JsonSupport.toJSON(decoded))), "typed manifest lossless roundtrip");
        var requestTransform = new A2uiCompiledRequestMapping(A2uiMappingSource.APP_PARAMS, "/label", "/label", null,
                new A2uiCompiledRequestTransform(A2uiRequestTransformType.STRING_PREFIX, "prefix", null));
        check(codec.readValue(JsonSupport.toJSON(requestTransform), A2uiCompiledRequestMapping.class)
                .getTransform().getPrefix().equals("prefix"), "request transform retained");
        var resultBinding = new A2uiCompiledMessageTemplateBinding("/updateDataModel/value", A2uiResultSource.CAPABILITY_DATA,
                "/value", true, null, new A2uiCompiledResultTransform(A2uiResultTransformType.MINOR_UNIT_TO_DECIMAL_STRING,
                        2, null, null, null, null));
        check(codec.readValue(JsonSupport.toJSON(resultBinding), A2uiCompiledMessageTemplateBinding.class)
                .getTransform().getScale() == 2, "result transform retained");
        check(codec.readValue(JsonSupport.toJSON(new A2uiCompiledSurfaceDeclaration("s", "r", List.of("footer"))),
                A2uiCompiledSurfaceDeclaration.class).getFooterComponentIds().equals(List.of("footer")), "footer retained");
        var noBranches = new A2uiCompiledActionBinding("b", "surface", "button", "click", "declaration",
                List.of("button"), Map.of(), new A2uiCompiledCapabilityActionRef("action"), List.of(),
                A2uiResultOutcome.NO_UI_MESSAGES, A2uiResultOutcome.NO_UI_MESSAGES, List.of(), List.of(),
                null, true, List.of());
        var absentBranches = codec.readValue(JsonSupport.toJSON(noBranches), A2uiCompiledActionBinding.class);
        var rootOutcome = new dev.a2flow.management.a2ui.runtime.action.A2uiCapabilityOutcomeEvaluator().select(
                absentBranches, dev.a2flow.management.a2ui.runtime.capability.CapabilityExecutionResult.builder()
                        .success(true).data(Map.of()).build());
        check(rootOutcome.isSucceeded() && rootOutcome.isCompletesWorkflowInteraction()
                && rootOutcome.getBranchId() == null, "omitted empty successBranches retains root outcome");
        var identity = new ReleaseIdentity("app", "source", "digest", "build", ReleaseEnvironment.PRT);
        var published = new PublishedApplication(identity, decoded);
        var calls = new AtomicInteger();
        CapabilityExecutionPort port = port((key, json, ctx) -> {
            int count = calls.incrementAndGet();
            var mapped = JsonSupport.fromJson(json);
            check(ctx.userId() == Long.MIN_VALUE && ctx.environment() == ReleaseEnvironment.PRT, "trusted identity");
            if ("second".equals(key)) { check(mapped.get("previous").equals(7), "ordered previous result"); }
            return CapabilityToolResult.builder().success(true).actionCode(key).capabilityVersion(1)
                    .resolvedEnvironment(ReleaseEnvironment.PRT).data(Map.of("value", 7)).build();
        });
        var facade = new A2uiRuntimeFacade((key, env, user) -> published, port);
        var context = new CapabilityRpcContext(Long.MIN_VALUE, ReleaseEnvironment.PRT, "request", "PC");
        check(facade.describe(context, "app").actions().size() == 1 && calls.get() == 0, "describe no calls");
        var activated = facade.activate(context, new ActivateRequest("app", Map.of("label", "hello")));
        check(calls.get() == 2 && activated.executions().size() == 2, "ordered loads");
        check(activated.businessSuccess() && !activated.session().getRuntimeSessionToken().isBlank(), "session and success");
        check(JsonSupport.toJSON(activated.snapshot()).contains("hello"), "show APP_PARAMS binding");
        var card = new TrustedCard(Long.MIN_VALUE, "app", activated.params(), activated.snapshot());
        var invocation = new A2uiActionInvocation("correlation", "request",
                Map.of("version", "v0.9.1", "action", Map.of(
                "name", "click", "surfaceId", "surface", "sourceComponentId", "button",
                "timestamp", "2026-01-01T00:00:00Z", "context", Map.of())));
        var action = facade.act(context, new ActionRequest(card, invocation));
        check(action.businessSuccess() && "first".equals(action.selectedBranchId()) && action.completeInteraction(),
                "first branch and completion intent only");
        var changed = new A2uiRuntimeFacade((key, env, user) -> new PublishedApplication(
                new ReleaseIdentity("app", "new-source", "new-digest", "build", ReleaseEnvironment.PRT), decoded), port);
        int before = calls.get();
        var current = changed.act(context, new ActionRequest(card, invocation));
        check("new-source".equals(current.release().sourceId()), "old card uses current release");
        check(calls.get() == before + 1, "current action dispatched once");
        expect("A2UI_CARD_CONTEXT_MISMATCH", () -> facade.act(
                new CapabilityRpcContext(0, ReleaseEnvironment.PRT, "request", "PC"), new ActionRequest(card, invocation)));
        // Load失败后不再执行第二条；NO_UI_MESSAGES保留完整可恢复首屏。
        var failCalls = new AtomicInteger();
        var failed = new A2uiRuntimeFacade((key, env, user) -> published, port((key, json, ctx) -> {
            failCalls.incrementAndGet();
            return CapabilityToolResult.builder().success(false).actionCode(key).data(Map.of()).build();
        })).activate(new CapabilityRpcContext(0, ReleaseEnvironment.PRT, "zero", "PC"),
                new ActivateRequest("app", Map.of("label", "zero")));
        check(failCalls.get() == 1 && !failed.businessSuccess() && failed.executions().size() == 1, "failure stops loads, userId zero");
        System.out.println("A2UI_FACADE_SMOKE_PASS checks=" + checks);
    }
    static A2uiApplicationBuild build() {
        var predicate = new A2uiCompiledBusinessSuccessPredicate("v1", List.of(
                new A2uiCompiledBusinessPredicateClause("CAPABILITY_DATA", "/value", "EQUALS", 7)));
        var action = new A2uiCompiledActionBinding("action-binding", "surface", "button", "click", "declaration",
                List.of("button"), Map.of("type", "object", "properties", Map.of(), "additionalProperties", false),
                new A2uiCompiledCapabilityActionRef("action"), List.of(), A2uiResultOutcome.NO_UI_MESSAGES,
                A2uiResultOutcome.NO_UI_MESSAGES, List.of(), List.of(), predicate, false,
                List.of(new A2uiCompiledSuccessBranch("first", predicate, A2uiResultOutcome.NO_UI_MESSAGES, List.of(), true)));
        var first = new A2uiCompiledLoadBinding("first-binding", new A2uiCompiledCapabilityActionRef("first"),
                List.of(new A2uiCompiledRequestMapping(A2uiMappingSource.TRUSTED_CONTEXT, "/userId", "/identity", null)),
                A2uiResultOutcome.NO_UI_MESSAGES, A2uiResultOutcome.NO_UI_MESSAGES, List.of(), List.of());
        var second = new A2uiCompiledLoadBinding("second-binding", new A2uiCompiledCapabilityActionRef("second"),
                List.of(new A2uiCompiledRequestMapping(A2uiMappingSource.CAPABILITY_PREVIOUS_RESULT, "/data/value", "/previous", null)),
                A2uiResultOutcome.NO_UI_MESSAGES, A2uiResultOutcome.NO_UI_MESSAGES, List.of(), List.of());
        return new A2uiApplicationBuild("build", "app", "description", "source-digest", "v0.9.1", "ACTIVE", "commit", Map.of(), "PRT",
                new A2uiCompiledCatalogRef("catalog", "1", "catalog-digest",
                        A2uiCatalogSourceType.PLATFORM_MANAGED, Map.of(), Map.of()),
                "show", "show-digest", Map.of("type", "object", "properties", Map.of("label", Map.of("type", "string")),
                        "required", List.of("label"), "additionalProperties", false),
                List.of(new A2uiCompiledSurfaceDeclaration("surface", "button", List.of())),
                List.of(message("createSurface", Map.of("surfaceId", "surface")),
                        message("updateComponents", Map.of("surfaceId", "surface", "components", List.of(Map.of("id", "button", "component", "Button")))),
                        message("updateDataModel", Map.of("surfaceId", "surface", "path", "/", "value", Map.of("label", "initial")))),
                List.of(new A2uiCompiledShowInputBinding(2, "/updateDataModel/value/label", A2uiShowInputSource.APP_PARAMS, "/label", true, null)),
                List.of("Button"), List.of(), List.of(new A2uiActionDeclaration("surface", "button", "click", "declaration")),
                List.of(first, second), List.of(action), A2uiInteractionMode.INTERACTIVE);
    }
    static Map<String, Object> message(String op, Map<String, Object> body) { return Map.of("version", "v0.9.1", op, body); }
    @FunctionalInterface interface Call {
        CapabilityToolResult execute(String key, String json, CapabilityRpcContext context);
    }
    static CapabilityExecutionPort port(Call call) {
        return new CapabilityExecutionPort() {
            public CapabilityToolResult execute(String key, String json, CapabilityRpcContext context) {
                throw new AssertionError("A2UI must resolve actionCode, not treat it as draftId");
            }
            public CapabilityToolResult executeActionCode(String key, String json, CapabilityRpcContext context) {
                return call.execute(key, json, context);
            }
        };
    }
    static void check(boolean value, String name) { if (!value) throw new AssertionError(name); checks++; }
    static void expect(String code, Runnable operation) {
        try { operation.run(); } catch (RuntimeFailure e) { check(code.equals(e.getCode()), code); return; }
        throw new AssertionError("Expected " + code);
    }
}
