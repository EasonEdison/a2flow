package dev.a2flow.management.a2ui.application;

import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.ACTION_BINDING_AMBIGUOUS;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.ACTION_BINDING_ORPHAN;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.ACTION_CODE_RESERVED;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.ACTION_CONTEXT_SCHEMA_MISMATCH;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.ACTION_UNBOUND;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.BINDING_PARAM_SCHEMA_INCOMPATIBLE;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.BUILD_ID_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.BUSINESS_SUCCESS_PREDICATE_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.BUSINESS_SUCCESS_PREDICATE_REQUIRED;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CAPABILITY_LOAD_SIDE_EFFECT_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CAPABILITY_REFERENCE_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CAPABILITY_SCHEMA_INCOMPATIBLE;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CATALOG_COMPONENT_AMBIGUOUS;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CATALOG_SUPPORT_MISSING;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.COMPONENT_NOT_AVAILABLE;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.DISPLAY_ONLY_COMPLETION_ACTION_FORBIDDEN;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.DRAFT_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.INTERACTIVE_COMPLETION_ACTION_REQUIRED;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.PROTOCOL_UNSUPPORTED;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.RESULT_ADAPTER_INVALID;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationActionScanResult;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationBuild;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationDraft;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiBusinessPredicateClause;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiBusinessSuccessPredicate;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCapabilityActionRef;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCapabilitySchemaAudit;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledActionBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledBusinessPredicateClause;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledBusinessSuccessPredicate;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledCapabilityActionRef;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledCatalogRef;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledEmittedActionDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledLoadBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledMessageTemplateBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledRequestMapping;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledRequestTransform;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledResultAdapter;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledResultTransform;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledShowInputBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledSuccessBranch;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledSurfaceDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCurrentCapabilityContract;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCurrentCapabilityVariantContract;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiInteractionMode;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiLoadBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMappingSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMessageTemplateBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiRequestMapping;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiRequestTransform;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiRequestTransformType;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultAdapter;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultAdapterType;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultOutcome;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultTransform;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiResultTransformType;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiScannedActionDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiSideEffectLevel;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiSuccessBranch;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiSurfaceDeclaration;
import dev.a2flow.management.a2ui.application.A2uiShowTemplateAnalyzer.ShowFacts;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogModels.A2uiCatalogComponentContract;
import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;
import dev.a2flow.management.release.ReleaseEnvironment;

/**
 * A2UI Application canonical draft 到不可变 Build 的纯领域 compiler。
 *
 * <p>上游提供一次读取完成的 draft、同环境 Catalog component snapshot 和目标发布环境；下游只接收
 * self-contained Build。本类验证协议、Catalog、Show/Surface/Action closure、当前生效
 * Capability schema 和 Binding-owned ResultAdapter（包含有序成功分支），并深冻结运行态配置。Capability 的 release/version
 * 不进入 Build；本类不查数据库、不发布、不执行能力，也不实现 HTTP/SSE 或
 * CARD/Adviser fallback。
 */
public class A2uiApplicationBuildCompiler {

    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final String PROTOCOL_STATUS = "CURRENT_PRODUCTION";
    private static final String PROTOCOL_SOURCE_COMMIT = "420c6183c400e4b84fe3f9e084906725062a6d56";
    private static final String FIELD_INPUT_FIELDS = "inputFields";
    private static final String FIELD_ITEMS = "items";
    private static final String FIELD_PROPERTIES = "properties";
    private static final String FIELD_TOOL_FIELD = "toolField";
    private static final String FIELD_REQUIRED = "required";
    private static final String FIELD_SOURCE = "source";
    private static final String FIELD_TYPE = "type";
    private static final String SOURCE_MODEL_INPUT = "MODEL_INPUT";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String CLIENT_COMMON = "COMMON";
    private static final List<String> CLIENT_MODE_PC = List.of(CLIENT_PC);
    private static final List<String> CLIENT_MODE_APP = List.of(CLIENT_APP);
    private static final List<String> CLIENT_MODE_DIFFERENT = List.of(CLIENT_PC, CLIENT_APP);
    private static final List<String> CLIENT_MODE_COMMON = List.of(CLIENT_COMMON);
    private static final String TARGET_REQUEST_WRAPPER = "request";
    private static final String BUSINESS_DATA_ROOT_POINTER = "/data";
    private static final String TYPE_INTEGER = "integer";
    private static final String TYPE_NUMBER = "number";
    private static final String TYPE_STRING = "string";
    private static final String TYPE_ARRAY = "array";
    private static final String TYPE_BOOLEAN = "boolean";
    private static final String BUSINESS_PREDICATE_VERSION = "JSON_POINTER_V1";
    private static final String BUSINESS_PREDICATE_SOURCE = "CAPABILITY_DATA";
    private static final String BUSINESS_PREDICATE_EQUALS = "EQUALS";
    private static final String BUSINESS_PREDICATE_GREATER_THAN = "GREATER_THAN";
    private static final String BUSINESS_PREDICATE_IS_ARRAY = "IS_ARRAY";
    private static final String FIELD_CREATE_SURFACE = "createSurface";
    private static final String FIELD_UPDATE_COMPONENTS = "updateComponents";
    private static final String FIELD_DELETE_SURFACE = "deleteSurface";
    private static final String FOOTER_COMPONENT_TYPE = "Container";
    private static final String FOOTER_TYPE_FIELD = "component";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_COMPONENT_ID = "id";
    private static final String FIELD_SURFACE_ID = "surfaceId";
    private static final String FIELD_CHILDREN = "children";
    private static final int MAX_CHILD_COMPONENT_IDS = 100;
    private static final int MINOR_UNIT_DECIMAL_SCALE = 2;

    private final A2uiBuildIdGenerator buildIdGenerator;
    private final A2uiShowTemplateAnalyzer showTemplateAnalyzer = new A2uiShowTemplateAnalyzer();
    private final A2uiApplicationParamsSchemaValidator paramsSchemaValidator =
            new A2uiApplicationParamsSchemaValidator();
    private final A2uiApplicationActionScanService actionScanService =
            new A2uiApplicationActionScanService();
    private final A2uiApplicationComponentCollector componentCollector =
            new A2uiApplicationComponentCollector();

    public A2uiApplicationBuildCompiler(A2uiBuildIdGenerator buildIdGenerator) {
        if (buildIdGenerator == null) {
            throw new IllegalArgumentException("buildIdGenerator must not be null");
        }
        this.buildIdGenerator = buildIdGenerator;
    }

    /** 编译一个自包含 Build；任一闭合失败时不返回部分 manifest。 */
    public A2uiApplicationBuild compile(A2uiApplicationDraft draft,
            List<A2uiCatalogComponentContract> catalogComponents,
            Map<String, A2uiCurrentCapabilityContract> currentCapabilities) {
        return compile(draft, catalogComponents, currentCapabilities, ReleaseEnvironment.ONLINE);
    }

    /** 编译一个绑定服务端可信目标环境的自包含 Build。 */
    public A2uiApplicationBuild compile(A2uiApplicationDraft draft,
            List<A2uiCatalogComponentContract> catalogComponents,
            Map<String, A2uiCurrentCapabilityContract> currentCapabilities,
            ReleaseEnvironment publicationEnvironment) {
        validateDraft(draft);
        A2uiInteractionMode interactionMode = interactionMode(draft);
        validateWorkflowInteraction(draft, interactionMode);
        if (publicationEnvironment == null) {
            throw failure(DRAFT_INVALID);
        }
        A2uiApplicationActionScanResult actionScan = actionScanService.scan(authoringSource(draft));
        actionScanService.requireReleaseClosure(actionScan);
        ShowFacts showFacts = showTemplateAnalyzer.analyze(
                draft.getShowTemplate(), draft.getCatalog().getCatalogId());
        showTemplateAnalyzer.validateInputBindings(draft.getShowTemplate());
        validateFooterComponents(draft);
        // 仅约束 Application 参数子集，编译时阻止运行时无法校验的规则进入不可变 Build。
        paramsSchemaValidator.validate(draft.getShowTemplate().getParamsSchema());
        validateReservedActionCodes(draft, showFacts);
        validateCatalogClosure(draft, catalogComponents, showFacts.getComponentTypes());
        List<A2uiActionDeclaration> actionDeclarations = actionDeclarations(actionScan);
        List<A2uiCompiledActionBinding> actionBindings = compileActionBindings(
                draft.getActionBindings(), actionDeclarations,
                contextFields(actionScan, showFacts), currentCapabilities,
                draft.getShowTemplate().getParamsSchema());
        List<A2uiCompiledLoadBinding> loadBindings = compileLoadBindings(
                draft.getLoadBindings(), currentCapabilities,
                draft.getShowTemplate().getParamsSchema());
        validateResultTransformComponentClosure(
                draft.getShowTemplate().getMessageTemplates(), actionBindings, loadBindings);
        List<String> componentTypes = componentCollector.collect(
                componentMessages(draft, actionBindings, loadBindings));
        validateCatalogClosure(draft, catalogComponents, componentTypes);
        Map<String, A2uiComponentOriginType> componentOrigins = compileComponentOrigins(
                catalogComponents, componentTypes);
        List<A2uiCapabilitySchemaAudit> capabilitySchemaAudits = compileCapabilityAudits(
                draft, currentCapabilities);
        List<A2uiCompiledShowInputBinding> inputBindings = compileInputBindings(
                draft.getShowTemplate().getInputBindings());
        List<A2uiCompiledSurfaceDeclaration> surfaces = compileSurfaces(
                draft.getShowTemplate().getSurfaceDeclarations());

        Map<String, Object> digestSource = new TreeMap<>();
        digestSource.put("actionBindings", actionBindings);
        digestSource.put("actionDeclarations", actionDeclarations);
        digestSource.put("appCode", draft.getAppCode());
        digestSource.put("catalog", A2uiImmutableJsonSupport.canonicalize(draft.getCatalog()));
        digestSource.put("componentTypes", componentTypes);
        digestSource.put("description", draft.getDescription());
        digestSource.put("inputBindings", inputBindings);
        digestSource.put("interactionMode", interactionMode.name());
        digestSource.put("loadBindings", loadBindings);
        digestSource.put("nameCn", draft.getNameCn());
        digestSource.put("paramsSchema", A2uiImmutableJsonSupport.canonicalize(
                draft.getShowTemplate().getParamsSchema()));
        digestSource.put("protocolSchemaDigests", A2uiImmutableJsonSupport.canonicalize(
                draft.getProtocolSchemaDigests()));
        digestSource.put("protocolSourceCommit", draft.getProtocolSourceCommit());
        digestSource.put("protocolStatus", draft.getProtocolStatus());
        digestSource.put("protocolVersion", draft.getProtocolVersion());
        digestSource.put("publicationEnvironment", publicationEnvironment.name());
        digestSource.put("resolvedInitialMessages", A2uiImmutableJsonSupport.canonicalize(
                draft.getShowTemplate().getMessageTemplates()));
        digestSource.put("showTemplateCode", draft.getShowTemplate().getTemplateCode());
        digestSource.put("surfaceDeclarations", surfaces);
        digestSource.put("capabilitySchemaAudits", capabilitySchemaAudits);
        String sourceDigest = A2uiImmutableJsonSupport.digest(digestSource);
        String buildId = buildIdGenerator.generate(sourceDigest);
        if (isBlank(buildId)) {
            throw failure(BUILD_ID_INVALID);
        }
        String showDigest = A2uiImmutableJsonSupport.digest(draft.getShowTemplate());
        return new A2uiApplicationBuild(
                buildId,
                draft.getAppCode(),
                sourceDigest,
                draft.getProtocolVersion(),
                draft.getProtocolStatus(),
                draft.getProtocolSourceCommit(),
                A2uiImmutableJsonSupport.immutableStringMap(draft.getProtocolSchemaDigests()),
                publicationEnvironment.name(),
                new A2uiCompiledCatalogRef(draft.getCatalog().getCatalogId(),
                        draft.getCatalog().getRevision(), draft.getCatalog().getDigest(),
                        draft.getCatalog().getCatalogSourceType(), componentOrigins),
                draft.getShowTemplate().getTemplateCode(),
                showDigest,
                A2uiImmutableJsonSupport.immutableMap(draft.getShowTemplate().getParamsSchema()),
                surfaces,
                A2uiImmutableJsonSupport.immutableMessageList(draft.getShowTemplate().getMessageTemplates()),
                inputBindings,
                componentTypes,
                capabilitySchemaAudits,
                actionDeclarations,
                loadBindings,
                actionBindings,
                interactionMode);
    }

    /** 汇总首屏与所有可选结果管线，保证分支专用组件进入 Catalog 校验、Build 依赖及摘要。 */
    private List<Map<String, Object>> componentMessages(A2uiApplicationDraft draft,
            List<A2uiCompiledActionBinding> actionBindings, List<A2uiCompiledLoadBinding> loadBindings) {
        List<Map<String, Object>> messages = new ArrayList<>(draft.getShowTemplate().getMessageTemplates());
        for (A2uiCompiledActionBinding binding : actionBindings) {
            addAdapterMessages(messages, binding.getResultAdapters());
            addAdapterMessages(messages, binding.getFailureResultAdapters());
            for (A2uiCompiledSuccessBranch branch : binding.getSuccessBranches()) {
                addAdapterMessages(messages, branch.getResultAdapters());
            }
        }
        for (A2uiCompiledLoadBinding binding : loadBindings) {
            addAdapterMessages(messages, binding.getResultAdapters());
            addAdapterMessages(messages, binding.getFailureResultAdapters());
        }
        return messages;
    }

    /** 仅静态 MESSAGE_TEMPLATE 可在编译期解析组件；PASSTHROUGH 继续使用显式 Action 声明。 */
    private void addAdapterMessages(List<Map<String, Object>> messages, List<A2uiCompiledResultAdapter> adapters) {
        for (A2uiCompiledResultAdapter adapter : adapters) {
            if (adapter.getType() == A2uiResultAdapterType.MESSAGE_TEMPLATE) {
                messages.add(adapter.getMessageTemplate());
            }
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> authoringSource(A2uiApplicationDraft draft) {
        return JsonSupport.fromJSON(JsonSupport.toJSON(draft), Map.class);
    }

    private List<A2uiActionDeclaration> actionDeclarations(
            A2uiApplicationActionScanResult actionScan) {
        return actionScan.getActionDeclarations().stream()
                .map(value -> new A2uiActionDeclaration(
                        value.getSurfaceId(), value.getSourceComponentId(), value.getActionCode(),
                        value.getContextTemplateDigest()))
                .collect(Collectors.toUnmodifiableList());
    }

    private Map<String, Set<String>> contextFields(
            A2uiApplicationActionScanResult actionScan, ShowFacts showFacts) {
        Map<String, Set<String>> result = new HashMap<>();
        showFacts.getContextFieldsByDeclarationKey().forEach(
                (key, value) -> result.put(key, new HashSet<>(value)));
        for (A2uiScannedActionDeclaration declaration : actionScan.getActionDeclarations()) {
            result.computeIfAbsent(declarationKey(declaration), ignored -> new HashSet<>())
                    .addAll(declaration.getContextFields());
        }
        return result;
    }

    private void validateDraft(A2uiApplicationDraft draft) {
        if (draft == null
                || isBlank(draft.getAppCode())
                || isBlank(draft.getNameCn())
                || draft.getDescription() == null
                || draft.getCatalog() == null
                || draft.getShowTemplate() == null
                || draft.getLoadBindings() == null
                || draft.getActionBindings() == null
                || draft.getProtocolSchemaDigests() == null
                || draft.getProtocolSchemaDigests().isEmpty()
                || draft.getProtocolSchemaDigests().values().stream().anyMatch(this::isBlank)) {
            throw failure(DRAFT_INVALID);
        }
        if (!PROTOCOL_VERSION.equals(draft.getProtocolVersion())
                || !PROTOCOL_STATUS.equals(draft.getProtocolStatus())
                || !PROTOCOL_SOURCE_COMMIT.equals(draft.getProtocolSourceCommit())) {
            throw failure(PROTOCOL_UNSUPPORTED);
        }
        if (isBlank(draft.getCatalog().getCatalogId())
                || isBlank(draft.getCatalog().getRevision())
                || isBlank(draft.getCatalog().getDigest())
                || draft.getCatalog().getCatalogSourceType() == null
                || draft.getCatalog().getComponentOrigins() == null) {
            throw failure(CATALOG_SUPPORT_MISSING);
        }
    }

    /** 校验显式交互模式与终态 Action 的发布组合，不按组件或 actionCode 推断。 */
    private void validateWorkflowInteraction(A2uiApplicationDraft draft,
            A2uiInteractionMode interactionMode) {
        boolean hasCompletingAction = draft.getActionBindings().stream()
                .filter(Objects::nonNull)
                .anyMatch(this::mayCompleteWorkflowInteraction);
        if (interactionMode == A2uiInteractionMode.INTERACTIVE && !hasCompletingAction) {
            throw failure(INTERACTIVE_COMPLETION_ACTION_REQUIRED);
        }
        if (interactionMode == A2uiInteractionMode.DISPLAY_ONLY && hasCompletingAction) {
            throw failure(DISPLAY_ONLY_COMPLETION_ACTION_FORBIDDEN);
        }
    }

    /** 根成功或任一成功分支可完成时，统一进入交互模式与根业务谓词校验。 */
    private boolean mayCompleteWorkflowInteraction(A2uiActionBinding binding) {
        return binding.isCompleteWorkflowInteractionOnSuccess()
                || binding.getSuccessBranches() != null && binding.getSuccessBranches().stream()
                        .filter(Objects::nonNull)
                        .anyMatch(A2uiSuccessBranch::isCompleteWorkflowInteractionOnSuccess);
    }

    private A2uiInteractionMode interactionMode(A2uiApplicationDraft draft) {
        return draft.getInteractionMode() == null
                ? A2uiInteractionMode.DISPLAY_ONLY : draft.getInteractionMode();
    }

    private void validateCatalogClosure(A2uiApplicationDraft draft,
            List<A2uiCatalogComponentContract> components, List<String> referencedTypes) {
        Map<String, A2uiCatalogComponentContract> byType = new HashMap<>();
        if (components != null) {
            for (A2uiCatalogComponentContract component : components) {
                if (component == null || isBlank(component.getType())) {
                    throw failure(COMPONENT_NOT_AVAILABLE);
                }
                if (component.getComponentOriginType() == null) {
                    throw failure(COMPONENT_NOT_AVAILABLE);
                }
                if (byType.putIfAbsent(component.getType(), component) != null) {
                    throw failure(CATALOG_COMPONENT_AMBIGUOUS);
                }
            }
        }
        for (String type : referencedTypes) {
            A2uiCatalogComponentContract component = byType.get(type);
            if (component == null
                    || component.getComponentOriginType()
                    != draft.getCatalog().getComponentOrigins().get(type)
                    || !Objects.equals(draft.getCatalog().getCatalogId(), component.getCatalogId())
                    || !Objects.equals(draft.getCatalog().getRevision(), component.getCatalogRevision())
                    || !Objects.equals(draft.getCatalog().getDigest(), component.getCatalogDigest())) {
                throw failure(COMPONENT_NOT_AVAILABLE);
            }
        }
    }

    private void validateReservedActionCodes(A2uiApplicationDraft draft, ShowFacts showFacts) {
        for (A2uiActionDeclaration declaration : showFacts.getActionDeclarations()) {
            rejectReservedActionCode(declaration == null ? null : declaration.getActionCode());
        }
        for (A2uiLoadBinding binding : draft.getLoadBindings()) {
            rejectReservedActionCode(binding == null || binding.getCapability() == null
                    ? null : binding.getCapability().getActionCode());
        }
        for (A2uiActionBinding binding : draft.getActionBindings()) {
            rejectReservedActionCode(binding == null ? null : binding.getActionCode());
            rejectReservedActionCode(binding == null || binding.getCapability() == null
                    ? null : binding.getCapability().getActionCode());
        }
    }

    private void rejectReservedActionCode(String actionCode) {
        if (A2uiReservedActionCode.isReserved(actionCode)) {
            throw failure(ACTION_CODE_RESERVED);
        }
    }

    private Map<String, A2uiComponentOriginType> compileComponentOrigins(
            List<A2uiCatalogComponentContract> components, List<String> referencedTypes) {
        Map<String, A2uiComponentOriginType> availableOrigins = new HashMap<>();
        for (A2uiCatalogComponentContract component : components) {
            availableOrigins.put(component.getType(), component.getComponentOriginType());
        }
        Map<String, A2uiComponentOriginType> result = new TreeMap<>();
        for (String referencedType : referencedTypes) {
            A2uiComponentOriginType origin = availableOrigins.get(referencedType);
            if (origin == null) {
                throw failure(COMPONENT_NOT_AVAILABLE);
            }
            result.put(referencedType, origin);
        }
        return Collections.unmodifiableMap(result);
    }

    private List<A2uiCompiledActionBinding> compileActionBindings(List<A2uiActionBinding> bindings,
            List<A2uiActionDeclaration> declarations,
            Map<String, Set<String>> contextFieldsByDeclarationKey,
            Map<String, A2uiCurrentCapabilityContract> currentCapabilities,
            Map<String, Object> paramsSchema) {
        if (bindings.stream().anyMatch(binding -> binding == null
                || isBlank(binding.getBindingId())
                || isBlank(binding.getSurfaceId())
                || isBlank(binding.getSourceComponentId())
                || isBlank(binding.getActionCode()))) {
            throw failure(DRAFT_INVALID);
        }
        Map<String, Long> bindingCounts = bindings.stream().collect(Collectors.groupingBy(
                value -> actionKey(value.getSurfaceId(), value.getSourceComponentId(),
                        value.getActionCode()), Collectors.counting()));
        if (bindingCounts.values().stream().anyMatch(count -> count > 1)) {
            throw failure(ACTION_BINDING_AMBIGUOUS);
        }
        for (A2uiActionDeclaration declaration : declarations) {
            boolean matched = bindings.stream().anyMatch(binding -> matches(binding, declaration));
            if (!matched) {
                throw failure(ACTION_UNBOUND);
            }
        }
        List<A2uiCompiledActionBinding> compiled = new ArrayList<>();
        for (A2uiActionBinding binding : bindings) {
            A2uiActionDeclaration declaration = declarations.stream()
                    .filter(value -> matches(binding, value)).findFirst()
                    .orElseThrow(() -> failure(ACTION_BINDING_ORPHAN));
            if (!isBlank(binding.getDeclarationDigest())
                    && !Objects.equals(binding.getDeclarationDigest(), declaration.getContextTemplateDigest())) {
                throw failure(ACTION_BINDING_ORPHAN);
            }
            if (binding.getAllowedSourceComponentIds() == null
                    || !binding.getAllowedSourceComponentIds().contains(binding.getSourceComponentId())
                    || binding.getContextSchema() == null) {
                throw failure(DRAFT_INVALID);
            }
            validateContextSchema(binding, declaration, contextFieldsByDeclarationKey);
            A2uiCurrentCapabilityContract currentCapability = requireCurrentCapability(
                    binding.getCapability(), currentCapabilities);
            validateCapabilitySchemas(currentCapability, binding.getRequestMappings(), paramsSchema,
                    binding.getContextSchema());
            List<A2uiCompiledResultAdapter> success = compileAdapters(
                    binding.getSuccessOutcome(), binding.getResultAdapters(), false,
                    binding.getContextSchema());
            List<A2uiCompiledResultAdapter> failure = compileAdapters(
                    binding.getFailureOutcome(), binding.getFailureResultAdapters(),
                    currentCapability.getSideEffect() != A2uiSideEffectLevel.READ_ONLY,
                    binding.getContextSchema());
            A2uiCompiledBusinessSuccessPredicate businessSuccessPredicate =
                    compileBusinessSuccessPredicate(
                            binding.getBusinessSuccessPredicate(), mayCompleteWorkflowInteraction(binding));
            compiled.add(new A2uiCompiledActionBinding(
                    binding.getBindingId(),
                    binding.getSurfaceId(),
                    binding.getSourceComponentId(),
                    binding.getActionCode(),
                    declaration.getContextTemplateDigest(),
                    A2uiImmutableJsonSupport.immutableStringList(binding.getAllowedSourceComponentIds()),
                    A2uiImmutableJsonSupport.immutableMap(binding.getContextSchema()),
                    compileCapability(binding.getCapability(), currentCapabilities),
                    compileMappings(binding.getRequestMappings()),
                    binding.getSuccessOutcome(),
                    binding.getFailureOutcome(),
                    success,
                    failure,
                    businessSuccessPredicate,
                    binding.isCompleteWorkflowInteractionOnSuccess(),
                    compileSuccessBranches(binding.getSuccessBranches(), binding.getContextSchema())));
        }
        compiled.sort(Comparator.comparing(A2uiCompiledActionBinding::getSurfaceId)
                .thenComparing(A2uiCompiledActionBinding::getActionCode));
        return Collections.unmodifiableList(compiled);
    }

    /**
     * 把受限 JSON Pointer 谓词编译为不可变 Build 数据；不执行脚本，也不按业务 actionCode 分支。
     */
    private A2uiCompiledBusinessSuccessPredicate compileBusinessSuccessPredicate(
            A2uiBusinessSuccessPredicate predicate, boolean required) {
        if (predicate == null) {
            if (required) {
                throw failure(BUSINESS_SUCCESS_PREDICATE_REQUIRED);
            }
            return null;
        }
        if (!BUSINESS_PREDICATE_VERSION.equals(predicate.getVersion())
                || predicate.getAllOf() == null
                || predicate.getAllOf().isEmpty()) {
            throw failure(BUSINESS_SUCCESS_PREDICATE_INVALID);
        }
        List<A2uiCompiledBusinessPredicateClause> clauses = new ArrayList<>();
        for (A2uiBusinessPredicateClause clause : predicate.getAllOf()) {
            if (!validBusinessPredicateClause(clause)) {
                throw failure(BUSINESS_SUCCESS_PREDICATE_INVALID);
            }
            clauses.add(new A2uiCompiledBusinessPredicateClause(
                    clause.getSource(),
                    clause.getSourcePath(),
                    clause.getOperator(),
                    A2uiImmutableJsonSupport.immutableValue(clause.getExpectedValue())));
        }
        return new A2uiCompiledBusinessSuccessPredicate(
                BUSINESS_PREDICATE_VERSION, Collections.unmodifiableList(clauses));
    }

    /** 校验分支身份、必填谓词和结果管线；保持首个命中的声明顺序并深冻结所有配置。 */
    private List<A2uiCompiledSuccessBranch> compileSuccessBranches(List<A2uiSuccessBranch> branches,
            Map<String, Object> contextSchema) {
        if (branches == null || branches.size() > A2uiSuccessBranchValidator.MAX_SUCCESS_BRANCHES) {
            throw failure(DRAFT_INVALID);
        }
        if (branches.isEmpty()) {
            return Collections.emptyList();
        }
        Set<String> branchIds = new HashSet<>();
        List<A2uiCompiledSuccessBranch> compiled = new ArrayList<>();
        for (A2uiSuccessBranch branch : branches) {
            if (branch == null || isBlank(branch.getBranchId())
                    || branch.getBranchId().length() > A2uiSuccessBranchValidator.MAX_SUCCESS_BRANCH_ID_LENGTH
                    || !branchIds.add(branch.getBranchId())) {
                throw failure(DRAFT_INVALID);
            }
            compiled.add(new A2uiCompiledSuccessBranch(
                    branch.getBranchId(), compileBusinessSuccessPredicate(branch.getWhen(), true),
                    branch.getOutcome(), compileAdapters(
                            branch.getOutcome(), branch.getResultAdapters(), false, contextSchema),
                    branch.isCompleteWorkflowInteractionOnSuccess()));
        }
        return Collections.unmodifiableList(compiled);
    }

    /** IS_ARRAY 只接受布尔 true，运行时按 JSON List 类型判定，不引入字符串或数组强转。 */
    private boolean validBusinessPredicateClause(A2uiBusinessPredicateClause clause) {
        if (clause == null
                || !BUSINESS_PREDICATE_SOURCE.equals(clause.getSource())
                || !validJsonPointer(clause.getSourcePath())) {
            return false;
        }
        if (BUSINESS_PREDICATE_EQUALS.equals(clause.getOperator())) {
            return canonicalJsonValue(clause.getExpectedValue());
        }
        if (BUSINESS_PREDICATE_IS_ARRAY.equals(clause.getOperator())) {
            return Boolean.TRUE.equals(clause.getExpectedValue());
        }
        return BUSINESS_PREDICATE_GREATER_THAN.equals(clause.getOperator())
                && finiteNumber(clause.getExpectedValue());
    }

    private boolean canonicalJsonValue(Object value) {
        if (value == null || value instanceof String || value instanceof Number
                || value instanceof Boolean) {
            return !(value instanceof Number) || finiteNumber(value);
        }
        if (value instanceof Map) {
            return ((Map<?, ?>) value).entrySet().stream()
                    .allMatch(entry -> entry.getKey() instanceof String
                            && canonicalJsonValue(entry.getValue()));
        }
        if (value instanceof List) {
            return ((List<?>) value).stream().allMatch(this::canonicalJsonValue);
        }
        return false;
    }

    private boolean finiteNumber(Object value) {
        if (!(value instanceof Number)) {
            return false;
        }
        double number = ((Number) value).doubleValue();
        return !Double.isInfinite(number) && !Double.isNaN(number);
    }

    private boolean validJsonPointer(String pointer) {
        if (pointer == null) {
            return false;
        }
        if (pointer.isEmpty()) {
            return true;
        }
        if (!pointer.startsWith("/")) {
            return false;
        }
        for (int index = 0; index < pointer.length(); index++) {
            if (pointer.charAt(index) == '~'
                    && (index + 1 >= pointer.length()
                    || (pointer.charAt(index + 1) != '0' && pointer.charAt(index + 1) != '1'))) {
                return false;
            }
        }
        return true;
    }

    private List<A2uiCompiledLoadBinding> compileLoadBindings(List<A2uiLoadBinding> bindings,
            Map<String, A2uiCurrentCapabilityContract> currentCapabilities,
            Map<String, Object> paramsSchema) {
        List<A2uiCompiledLoadBinding> compiled = new ArrayList<>();
        for (A2uiLoadBinding binding : bindings) {
            if (binding == null || isBlank(binding.getBindingId())) {
                throw failure(DRAFT_INVALID);
            }
            A2uiCurrentCapabilityContract currentCapability = requireCurrentCapability(
                    binding.getCapability(), currentCapabilities);
            if (currentCapability.getSideEffect() != A2uiSideEffectLevel.READ_ONLY) {
                throw failure(CAPABILITY_LOAD_SIDE_EFFECT_INVALID);
            }
            validateCapabilitySchemas(currentCapability, binding.getRequestMappings(), paramsSchema, null);
            compiled.add(new A2uiCompiledLoadBinding(
                    binding.getBindingId(),
                    compileCapability(binding.getCapability(), currentCapabilities),
                    compileMappings(binding.getRequestMappings()),
                    binding.getSuccessOutcome(),
                    binding.getFailureOutcome(),
                    compileAdapters(binding.getSuccessOutcome(), binding.getResultAdapters(), false, null),
                    compileAdapters(
                    binding.getFailureOutcome(), binding.getFailureResultAdapters(), false, null)));
        }
        compiled.sort(Comparator.comparing(A2uiCompiledLoadBinding::getBindingId));
        return Collections.unmodifiableList(compiled);
    }

    private A2uiCompiledCapabilityActionRef compileCapability(A2uiCapabilityActionRef capability,
            Map<String, A2uiCurrentCapabilityContract> currentCapabilities) {
        return new A2uiCompiledCapabilityActionRef(
                requireCurrentCapability(capability, currentCapabilities).getActionCode());
    }

    /**
     * 生成发布时 schema 校验审计；这些摘要只证明 Build 编译时看到的契约，
     * 不参与 Runtime 版本选择。
     */
    private List<A2uiCapabilitySchemaAudit> compileCapabilityAudits(A2uiApplicationDraft draft,
            Map<String, A2uiCurrentCapabilityContract> currentCapabilities) {
        Set<String> actionCodes = new HashSet<>();
        for (A2uiLoadBinding binding : draft.getLoadBindings()) {
            actionCodes.add(requireCurrentCapability(binding == null ? null : binding.getCapability(),
                    currentCapabilities).getActionCode());
        }
        for (A2uiActionBinding binding : draft.getActionBindings()) {
            actionCodes.add(requireCurrentCapability(binding == null ? null : binding.getCapability(),
                    currentCapabilities).getActionCode());
        }
        List<A2uiCapabilitySchemaAudit> audits = actionCodes.stream()
                .sorted()
                .map(actionCode -> currentCapabilities.get(actionCode))
                .map(this::capabilityAudit)
                .collect(Collectors.toList());
        return Collections.unmodifiableList(audits);
    }

    private A2uiCapabilitySchemaAudit capabilityAudit(A2uiCurrentCapabilityContract contract) {
        Map<String, Object> modelContracts = new TreeMap<>();
        Map<String, Object> resultContracts = new TreeMap<>();
        for (A2uiCurrentCapabilityVariantContract variant : capabilityVariants(contract)) {
            modelContracts.put(variant.getClientType(), variant.getModelContract());
            resultContracts.put(variant.getClientType(), variant.getResultContract());
        }
        return new A2uiCapabilitySchemaAudit(
                contract.getActionCode(),
                A2uiImmutableJsonSupport.digest(modelContracts),
                A2uiImmutableJsonSupport.digest(resultContracts));
    }

    private A2uiCurrentCapabilityContract requireCurrentCapability(A2uiCapabilityActionRef capability,
            Map<String, A2uiCurrentCapabilityContract> currentCapabilities) {
        if (capability == null || isBlank(capability.getActionCode()) || currentCapabilities == null) {
            throw failure(CAPABILITY_REFERENCE_INVALID);
        }
        A2uiCurrentCapabilityContract current = currentCapabilities.get(capability.getActionCode());
        if (current == null || !Objects.equals(capability.getActionCode(), current.getActionCode())
                || current.getSideEffect() == null) {
            throw failure(CAPABILITY_REFERENCE_INVALID);
        }
        capabilityVariants(current);
        return current;
    }

    void validateCapabilitySchemas(A2uiCurrentCapabilityContract capability,
            List<A2uiRequestMapping> mappings, Map<String, Object> paramsSchema,
            Map<String, Object> contextSchema) {
        for (A2uiCurrentCapabilityVariantContract variant : capabilityVariants(capability)) {
            validateCapabilitySchema(variant, mappings, paramsSchema, contextSchema);
        }
    }

    private List<A2uiCurrentCapabilityVariantContract> capabilityVariants(
            A2uiCurrentCapabilityContract capability) {
        if (capability == null || capability.getClientVariants() == null) {
            throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
        }
        List<String> clients = new ArrayList<>(capability.getClientVariants().keySet());
        if (!CLIENT_MODE_PC.equals(clients) && !CLIENT_MODE_APP.equals(clients)
                && !CLIENT_MODE_DIFFERENT.equals(clients) && !CLIENT_MODE_COMMON.equals(clients)) {
            throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
        }
        List<A2uiCurrentCapabilityVariantContract> variants = new ArrayList<>();
        for (String client : clients) {
            A2uiCurrentCapabilityVariantContract variant = capability.getClientVariants().get(client);
            if (variant == null || !Objects.equals(client, variant.getClientType())
                    || variant.getModelContract() == null || variant.getModelContract().isEmpty()
                    || variant.getResultContract() == null || variant.getResultContract().isEmpty()) {
                throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
            }
            variants.add(variant);
        }
        return variants;
    }

    private void validateCapabilitySchema(A2uiCurrentCapabilityVariantContract capability,
            List<A2uiRequestMapping> mappings, Map<String, Object> paramsSchema,
            Map<String, Object> contextSchema) {
        if (capability.getModelContract() == null || capability.getResultContract() == null
                || mappings == null) {
            throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
        }
        Object rawInputFields = capability.getModelContract().get(FIELD_INPUT_FIELDS);
        if (!(rawInputFields instanceof List)) {
            throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
        }
        Set<String> toolFields = new HashSet<>();
        Set<String> requiredToolFields = new HashSet<>();
        Map<String, String> toolFieldTypes = new HashMap<>();
        for (Object rawInputField : (List<?>) rawInputFields) {
            if (!(rawInputField instanceof Map)) {
                throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
            }
            Map<?, ?> inputField = (Map<?, ?>) rawInputField;
            Object rawToolField = inputField.get(FIELD_TOOL_FIELD);
            String toolField = rawToolField == null ? null : String.valueOf(rawToolField);
            if (isBlank(toolField) || !toolFields.add(toolField)) {
                throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
            }
            String toolFieldType = inputField.get(FIELD_TYPE) == null
                    ? null : String.valueOf(inputField.get(FIELD_TYPE));
            if (isBlank(toolFieldType)) {
                throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
            }
            toolFieldTypes.put(toolField, toolFieldType);
            String source = inputField.get(FIELD_SOURCE) == null
                    ? null : String.valueOf(inputField.get(FIELD_SOURCE));
            if (Boolean.TRUE.equals(inputField.get(FIELD_REQUIRED))
                    && (isBlank(source) || SOURCE_MODEL_INPUT.equals(source))) {
                requiredToolFields.add(toolField);
            }
        }
        Set<String> mappedToolFields = new HashSet<>();
        for (A2uiRequestMapping mapping : mappings) {
            String targetField = mapping == null ? null : capabilityTargetField(mapping.getTargetPath());
            if (isBlank(targetField) || !toolFields.contains(targetField)) {
                throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
            }
            validateRequestTransform(mapping, paramsSchema, contextSchema, toolFieldTypes.get(targetField),
                    targetField);
            if (mapping.getSource() == A2uiMappingSource.APP_PARAMS) {
                String paramsType = applicationParamType(paramsSchema, mapping.getSourcePath());
                if (!isSchemaTypeCompatible(paramsType, toolFieldTypes.get(targetField))) {
                    throw failure(BINDING_PARAM_SCHEMA_INCOMPATIBLE);
                }
            }
            mappedToolFields.add(targetField);
        }
        if (!mappedToolFields.containsAll(requiredToolFields)) {
            throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
        }
    }

    /**
     * 校验请求转换的来源权限、精确类型参数和输入输出 schema，
     * 不引入跨根取值或隐式转换。
     */
    private void validateRequestTransform(A2uiRequestMapping mapping,
            Map<String, Object> paramsSchema, Map<String, Object> contextSchema,
            String targetType, String targetField) {
        A2uiRequestTransform transform = mapping.getTransform();
        if (transform == null) {
            return;
        }
        if (transform.getType() == null) {
            throw failure(DRAFT_INVALID);
        }
        Map<String, Object> sourceSchema;
        if (mapping.getSource() == A2uiMappingSource.APP_PARAMS) {
            sourceSchema = paramsSchema;
        } else if (mapping.getSource() == A2uiMappingSource.ACTION_CONTEXT && contextSchema != null) {
            sourceSchema = contextSchema;
        } else {
            throw failure(BINDING_PARAM_SCHEMA_INCOMPATIBLE);
        }
        // Capability inputFields 声明的是字段本身；不能把字符串字段下的子路径视为字符串目标。
        String targetPath = mapping.getTargetPath();
        boolean declaredTarget = Objects.equals(targetPath, "/" + targetField)
                || Objects.equals(targetPath, "/" + TARGET_REQUEST_WRAPPER + "/" + targetField);
        if (!declaredTarget) {
            throw failure(BINDING_PARAM_SCHEMA_INCOMPATIBLE);
        }
        if (transform.getType() == A2uiRequestTransformType.STRING_PREFIX) {
            if (transform.getPrefix() == null || transform.getPrefix().isEmpty()
                    || transform.getMaskSourcePath() != null) {
                throw failure(DRAFT_INVALID);
            }
            if (!TYPE_STRING.equals(applicationParamType(sourceSchema, mapping.getSourcePath()))
                    || !TYPE_STRING.equals(targetType)) {
                throw failure(BINDING_PARAM_SCHEMA_INCOMPATIBLE);
            }
            return;
        }
        if (transform.getType() == A2uiRequestTransformType.ARRAY_FILTER_BY_BOOLEAN_MASK) {
            if (transform.getPrefix() != null || isBlank(transform.getMaskSourcePath())) {
                throw failure(DRAFT_INVALID);
            }
            Map<?, ?> maskSchema = applicationParamSchema(sourceSchema,
                    transform.getMaskSourcePath());
            Object rawMaskItems = maskSchema == null ? null : maskSchema.get(FIELD_ITEMS);
            String maskItemType = rawMaskItems instanceof Map
                    && ((Map<?, ?>) rawMaskItems).get(FIELD_TYPE) != null
                    ? String.valueOf(((Map<?, ?>) rawMaskItems).get(FIELD_TYPE)) : null;
            if (!TYPE_ARRAY.equals(applicationParamType(sourceSchema, mapping.getSourcePath()))
                    || !TYPE_ARRAY.equals(applicationParamType(sourceSchema,
                            transform.getMaskSourcePath()))
                    || !TYPE_BOOLEAN.equals(maskItemType)
                    || !TYPE_ARRAY.equals(targetType)) {
                throw failure(BINDING_PARAM_SCHEMA_INCOMPATIBLE);
            }
            return;
        }
        throw failure(DRAFT_INVALID);
    }

    /** JSON Schema integer 是 number 的窄类型；其余 Capability 参数类型要求精确一致。 */
    private boolean isSchemaTypeCompatible(String paramsType, String capabilityType) {
        if (isBlank(paramsType) || isBlank(capabilityType)) {
            return false;
        }
        return paramsType.equals(capabilityType)
                || (TYPE_INTEGER.equals(paramsType) && TYPE_NUMBER.equals(capabilityType));
    }

    /** 按 JSON Pointer 解析 Application paramsSchema 字段类型；非法或未声明路径返回空。 */
    private String applicationParamType(Map<String, Object> paramsSchema, String sourcePath) {
        Map<?, ?> schema = applicationParamSchema(paramsSchema, sourcePath);
        Object rawType = schema == null ? null : schema.get(FIELD_TYPE);
        return rawType == null ? null : String.valueOf(rawType);
    }

    /** 按 JSON Pointer 解析 Application schema 节点；非法转义或未声明路径返回空。 */
    private Map<?, ?> applicationParamSchema(Map<String, Object> paramsSchema, String sourcePath) {
        if (paramsSchema == null || isBlank(sourcePath) || !sourcePath.startsWith("/")) {
            return null;
        }
        Object currentSchema = paramsSchema;
        String[] segments = sourcePath.substring(1).split("/", -1);
        for (String encodedSegment : segments) {
            if (!(currentSchema instanceof Map)) {
                return null;
            }
            String segment = decodeJsonPointerSegment(encodedSegment);
            Object rawProperties = ((Map<?, ?>) currentSchema).get(FIELD_PROPERTIES);
            if (segment == null || !(rawProperties instanceof Map)
                    || !((Map<?, ?>) rawProperties).containsKey(segment)) {
                return null;
            }
            currentSchema = ((Map<?, ?>) rawProperties).get(segment);
        }
        if (!(currentSchema instanceof Map)) {
            return null;
        }
        return (Map<?, ?>) currentSchema;
    }

    /** 解码 RFC 6901 path segment；非法转义直接 fail closed。 */
    private String decodeJsonPointerSegment(String encodedSegment) {
        StringBuilder decoded = new StringBuilder();
        for (int index = 0; index < encodedSegment.length(); index++) {
            char current = encodedSegment.charAt(index);
            if (current != '~') {
                decoded.append(current);
                continue;
            }
            if (++index >= encodedSegment.length()) {
                return null;
            }
            char escaped = encodedSegment.charAt(index);
            if (escaped == '0') {
                decoded.append('~');
            } else if (escaped == '1') {
                decoded.append('/');
            } else {
                return null;
            }
        }
        return decoded.toString();
    }

    private String capabilityTargetField(String targetPath) {
        if (isBlank(targetPath)) {
            return null;
        }
        String normalized = targetPath.trim();
        if (normalized.startsWith("$")) {
            normalized = normalized.substring(1);
        }
        while (normalized.startsWith(".") || normalized.startsWith("/")) {
            normalized = normalized.substring(1);
        }
        if (normalized.isEmpty()) {
            return null;
        }
        String[] segments = normalized.split("[./]");
        if (segments.length > 1 && TARGET_REQUEST_WRAPPER.equals(segments[0])) {
            return segments[1];
        }
        return segments[0];
    }

    private List<A2uiCompiledRequestMapping> compileMappings(List<A2uiRequestMapping> mappings) {
        if (mappings == null) {
            throw failure(DRAFT_INVALID);
        }
        List<A2uiCompiledRequestMapping> compiled = new ArrayList<>();
        for (A2uiRequestMapping mapping : mappings) {
            if (mapping == null || mapping.getSource() == null || isBlank(mapping.getTargetPath())) {
                throw failure(DRAFT_INVALID);
            }
            compiled.add(new A2uiCompiledRequestMapping(
                    mapping.getSource(), mapping.getSourcePath(), mapping.getTargetPath(),
                    A2uiImmutableJsonSupport.immutableValue(mapping.getConstantValue()),
                    compileRequestTransform(mapping.getTransform())));
        }
        compiled.sort(Comparator.comparing(A2uiCompiledRequestMapping::getTargetPath));
        return Collections.unmodifiableList(compiled);
    }

    /** 新建只读转换值对象，避免作者态后续编辑影响 Build 及 sourceDigest。 */
    private A2uiCompiledRequestTransform compileRequestTransform(A2uiRequestTransform transform) {
        return transform == null ? null
                : new A2uiCompiledRequestTransform(transform.getType(), transform.getPrefix(),
                        transform.getMaskSourcePath());
    }

    private List<A2uiCompiledResultAdapter> compileAdapters(A2uiResultOutcome outcome,
            List<A2uiResultAdapter> adapters, boolean failurePipelineRequired,
            Map<String, Object> contextSchema) {
        if (outcome == null || adapters == null
                || outcome == A2uiResultOutcome.NO_UI_MESSAGES && !adapters.isEmpty()
                || outcome == A2uiResultOutcome.ADAPTER_PIPELINE && adapters.isEmpty()
                || failurePipelineRequired && outcome != A2uiResultOutcome.ADAPTER_PIPELINE) {
            throw failure(RESULT_ADAPTER_INVALID);
        }
        Set<Integer> orders = new HashSet<>();
        List<A2uiCompiledResultAdapter> compiled = new ArrayList<>();
        for (A2uiResultAdapter adapter : adapters) {
            if (adapter == null
                    || isBlank(adapter.getAdapterId())
                    || adapter.getOrder() <= 0
                    || !orders.add(adapter.getOrder())
                    || adapter.getType() == null) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            validateAdapter(adapter);
            compiled.add(new A2uiCompiledResultAdapter(
                    adapter.getAdapterId(), adapter.getOrder(), adapter.getType(),
                    adapter.getTemplateCode(), adapter.getTemplateRevision(), adapter.getTemplateDigest(),
                    A2uiImmutableJsonSupport.immutableMap(adapter.getMessageTemplate()),
                    compileTemplateBindings(adapter.getBindings(), contextSchema),
                    adapter.getSource(), adapter.getSourcePath(), adapter.getCardinality(), adapter.isRequired(),
                    compileEmittedActionDeclarations(adapter)));
        }
        compiled.sort(Comparator.comparingInt(A2uiCompiledResultAdapter::getOrder));
        return Collections.unmodifiableList(compiled);
    }

    private void validateAdapter(A2uiResultAdapter adapter) {
        if (adapter.getType() == A2uiResultAdapterType.MESSAGE_TEMPLATE) {
            if (adapter.getMessageTemplate() == null
                    || !PROTOCOL_VERSION.equals(adapter.getMessageTemplate().get("version"))
                    || adapter.getEmittedActionDeclarations() != null
                    && !adapter.getEmittedActionDeclarations().isEmpty()) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            showTemplateAnalyzer.validateServerMessage(adapter.getMessageTemplate());
        } else if (!isCapabilityRoot(adapter.getSource())
                || isBlank(adapter.getSourcePath())
                || readsBusinessDataThroughMetadata(adapter.getSource(), adapter.getSourcePath())
                || !("ONE".equals(adapter.getCardinality()) || "MANY".equals(adapter.getCardinality()))
                || adapter.getEmittedActionDeclarations() == null
                || adapter.getEmittedActionDeclarations().isEmpty()) {
            throw failure(RESULT_ADAPTER_INVALID);
        }
    }

    private List<A2uiCompiledEmittedActionDeclaration> compileEmittedActionDeclarations(
            A2uiResultAdapter adapter) {
        if (adapter.getEmittedActionDeclarations() == null) {
            return Collections.emptyList();
        }
        return adapter.getEmittedActionDeclarations().stream()
                .map(value -> new A2uiCompiledEmittedActionDeclaration(
                        value.getSurfaceId(), value.getSourceComponentId(), value.getActionCode(),
                        A2uiImmutableJsonSupport.immutableMap(value.getContextSchema())))
                .sorted(Comparator.comparing(A2uiCompiledEmittedActionDeclaration::getSurfaceId)
                        .thenComparing(A2uiCompiledEmittedActionDeclaration::getSourceComponentId)
                        .thenComparing(A2uiCompiledEmittedActionDeclaration::getActionCode))
                .collect(Collectors.toUnmodifiableList());
    }

    private List<A2uiCompiledMessageTemplateBinding> compileTemplateBindings(
            List<A2uiMessageTemplateBinding> bindings, Map<String, Object> contextSchema) {
        if (bindings == null) {
            return Collections.emptyList();
        }
        List<A2uiCompiledMessageTemplateBinding> compiled = new ArrayList<>();
        for (A2uiMessageTemplateBinding binding : bindings) {
            if (binding == null
                    || isBlank(binding.getTargetPath())
                    || binding.getSource() == null
                    || (requiresSourcePath(binding.getSource()) && isBlank(binding.getSourcePath()))
                    || (binding.getSource() == A2uiResultSource.ACTION_CONTEXT
                    && applicationParamSchema(contextSchema, binding.getSourcePath()) == null)
                    || readsBusinessDataThroughMetadata(binding.getSource(), binding.getSourcePath())) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            compiled.add(new A2uiCompiledMessageTemplateBinding(
                    binding.getTargetPath(), binding.getSource(), binding.getSourcePath(),
                    binding.isRequired(), A2uiImmutableJsonSupport.immutableValue(binding.getConstantValue()),
                    compileResultTransform(binding.getTransform(), contextSchema)));
        }
        compiled.sort(Comparator.comparing(A2uiCompiledMessageTemplateBinding::getTargetPath));
        return Collections.unmodifiableList(compiled);
    }

    /** 校验并新建只读结果转换，避免作者态对象后续修改污染已发布 Build。 */
    private A2uiCompiledResultTransform compileResultTransform(A2uiResultTransform transform,
            Map<String, Object> contextSchema) {
        if (transform == null) {
            return null;
        }
        if (transform.getType() == A2uiResultTransformType.PAGINATION_STATE) {
            if (transform.getScale() != null || transform.getComponentIds() != null
                    || !positivePagingInteger(transform.getPageSize())
                    || (transform.getPageNumber() == null) == (transform.getActionPagePath() == null)) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            if (transform.getActionPagePath() == null) {
                if (!positivePagingInteger(transform.getPageNumber())) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
            } else if (contextSchema == null
                    || !numericPagingPath(contextSchema, transform.getActionPagePath())) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            return new A2uiCompiledResultTransform(transform.getType(), null, null,
                    transform.getPageSize().intValue(), transform.getPageNumber() == null
                    ? null : transform.getPageNumber().intValue(), transform.getActionPagePath());
        }
        if (transform.getPageSize() != null || transform.getPageNumber() != null
                || transform.getActionPagePath() != null) {
            throw failure(RESULT_ADAPTER_INVALID);
        }
        if (transform.getType() == A2uiResultTransformType.MINOR_UNIT_TO_DECIMAL_STRING) {
            if (!isIntegralScaleTwo(transform.getScale())
                    || transform.getComponentIds() != null) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            return new A2uiCompiledResultTransform(
                    transform.getType(), MINOR_UNIT_DECIMAL_SCALE, null, null, null, null);
        }
        if (transform.getType() == A2uiResultTransformType.ARRAY_TO_CHILDREN_PREFIX) {
            if (transform.getScale() != null || !validChildComponentIds(transform.getComponentIds())) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            return new A2uiCompiledResultTransform(transform.getType(), null,
                    A2uiImmutableJsonSupport.immutableStringList(transform.getComponentIds()), null, null, null);
        }
        if (transform.getType() == A2uiResultTransformType.BOOLEAN_ARRAY_TRUE_COUNT
                || transform.getType() == A2uiResultTransformType.NUMBER_TO_STRING) {
            if (transform.getScale() != null || transform.getComponentIds() != null) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            return new A2uiCompiledResultTransform(transform.getType(), null, null, null, null, null);
        }
        throw failure(RESULT_ADAPTER_INVALID);
    }

    /** 动作分页只读取 context schema 已声明的数值字段，禁止 Load 隐式读取。 */
    private boolean numericPagingPath(Map<String, Object> contextSchema, String path) {
        Map<?, ?> schema = applicationParamSchema(contextSchema, path);
        return schema != null && (TYPE_NUMBER.equals(schema.get("type")) || TYPE_INTEGER.equals(schema.get("type")));
    }

    /** 分页配置仅接受正整型数值，不把小数静默截断。 */
    private boolean positivePagingInteger(Number value) {
        if (value == null) {
            return false;
        }
        try {
            return new java.math.BigDecimal(value.toString()).intValueExact() > 0;
        } catch (NumberFormatException | ArithmeticException exception) {
            return false;
        }
    }

    private boolean validChildComponentIds(List<String> componentIds) {
        if (componentIds == null || componentIds.isEmpty()
                || componentIds.size() > MAX_CHILD_COMPONENT_IDS) {
            return false;
        }
        Set<String> uniqueIds = new HashSet<>();
        return componentIds.stream().allMatch(componentId ->
                !isBlank(componentId) && uniqueIds.add(componentId));
    }

    /**
     * 校验 children 前缀转换只能引用同一首屏 Surface 已声明的组件，避免 Build 在运行时制造组件身份。
     */
    private void validateResultTransformComponentClosure(
            List<Map<String, Object>> initialMessages,
            List<A2uiCompiledActionBinding> actionBindings,
            List<A2uiCompiledLoadBinding> loadBindings) {
        Map<String, Set<String>> initialComponentIds = collectInitialComponentIds(initialMessages);
        for (A2uiCompiledActionBinding binding : actionBindings) {
            validateAdapterTransformClosure(binding.getResultAdapters(), initialComponentIds);
            validateAdapterTransformClosure(binding.getFailureResultAdapters(), initialComponentIds);
            for (A2uiCompiledSuccessBranch branch : binding.getSuccessBranches()) {
                validateAdapterTransformClosure(branch.getResultAdapters(), initialComponentIds);
            }
        }
        for (A2uiCompiledLoadBinding binding : loadBindings) {
            validateAdapterTransformClosure(binding.getResultAdapters(), initialComponentIds);
            validateAdapterTransformClosure(binding.getFailureResultAdapters(), initialComponentIds);
        }
    }

    private Map<String, Set<String>> collectInitialComponentIds(
            List<Map<String, Object>> initialMessages) {
        Map<String, Set<String>> componentIdsBySurface = new HashMap<>();
        for (Map<String, Object> message : initialMessages) {
            Object rawCreate = message.get(FIELD_CREATE_SURFACE);
            if (rawCreate instanceof Map) {
                Object rawSurfaceId = ((Map<?, ?>) rawCreate).get(FIELD_SURFACE_ID);
                if (!(rawSurfaceId instanceof String) || isBlank((String) rawSurfaceId)) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
                componentIdsBySurface.put((String) rawSurfaceId, new HashSet<>());
                continue;
            }
            Object rawDelete = message.get(FIELD_DELETE_SURFACE);
            if (rawDelete instanceof Map) {
                Object rawSurfaceId = ((Map<?, ?>) rawDelete).get(FIELD_SURFACE_ID);
                if (!(rawSurfaceId instanceof String) || isBlank((String) rawSurfaceId)) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
                componentIdsBySurface.remove(rawSurfaceId);
                continue;
            }
            Object rawUpdate = message.get(FIELD_UPDATE_COMPONENTS);
            if (!(rawUpdate instanceof Map)) {
                continue;
            }
            Map<?, ?> update = (Map<?, ?>) rawUpdate;
            Object rawSurfaceId = update.get(FIELD_SURFACE_ID);
            Object rawComponents = update.get(FIELD_COMPONENTS);
            if (!(rawSurfaceId instanceof String) || isBlank((String) rawSurfaceId)
                    || !(rawComponents instanceof List)) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            Set<String> componentIds = componentIdsBySurface.get(rawSurfaceId);
            if (componentIds == null) {
                throw failure(RESULT_ADAPTER_INVALID);
            }
            for (Object rawComponent : (List<?>) rawComponents) {
                if (!(rawComponent instanceof Map)) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
                Object rawComponentId = ((Map<?, ?>) rawComponent).get(FIELD_COMPONENT_ID);
                if (!(rawComponentId instanceof String) || isBlank((String) rawComponentId)) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
                componentIds.add((String) rawComponentId);
            }
        }
        return componentIdsBySurface;
    }

    private void validateAdapterTransformClosure(List<A2uiCompiledResultAdapter> adapters,
            Map<String, Set<String>> initialComponentIds) {
        for (A2uiCompiledResultAdapter adapter : adapters) {
            for (A2uiCompiledMessageTemplateBinding binding : adapter.getBindings()) {
                A2uiCompiledResultTransform transform = binding.getTransform();
                if (transform == null
                        || transform.getType() != A2uiResultTransformType.ARRAY_TO_CHILDREN_PREFIX) {
                    continue;
                }
                Map<String, Object> messageTemplate = adapter.getMessageTemplate();
                Object rawUpdate = messageTemplate.get(FIELD_UPDATE_COMPONENTS);
                if (!(rawUpdate instanceof Map)) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
                Map<?, ?> update = (Map<?, ?>) rawUpdate;
                Object rawSurfaceId = update.get(FIELD_SURFACE_ID);
                Object rawComponents = update.get(FIELD_COMPONENTS);
                int targetIndex = childrenTargetComponentIndex(binding.getTargetPath());
                if (!(rawSurfaceId instanceof String)
                        || !(rawComponents instanceof List)
                        || targetIndex < 0
                        || targetIndex >= ((List<?>) rawComponents).size()) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
                Object rawTarget = ((List<?>) rawComponents).get(targetIndex);
                if (!(rawTarget instanceof Map)
                        || !(((Map<?, ?>) rawTarget).get(FIELD_CHILDREN) instanceof List)) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
                Set<String> availableIds = initialComponentIds.get(rawSurfaceId);
                if (availableIds == null
                        || !availableIds.containsAll(transform.getComponentIds())) {
                    throw failure(RESULT_ADAPTER_INVALID);
                }
            }
        }
    }

    private int childrenTargetComponentIndex(String targetPath) {
        if (targetPath == null) {
            return -1;
        }
        String[] segments = targetPath.split("/", -1);
        if (segments.length != 5
                || !segments[0].isEmpty()
                || !FIELD_UPDATE_COMPONENTS.equals(segments[1])
                || !FIELD_COMPONENTS.equals(segments[2])
                || !FIELD_CHILDREN.equals(segments[4])) {
            return -1;
        }
        String indexSegment = segments[3];
        if (indexSegment.length() > 1 && indexSegment.charAt(0) == '0') {
            return -1;
        }
        try {
            int targetIndex = Integer.parseInt(indexSegment);
            return targetIndex < 0 ? -1 : targetIndex;
        } catch (NumberFormatException ignored) {
            return -1;
        }
    }

    private boolean isIntegralScaleTwo(Number scale) {
        return (scale instanceof Byte || scale instanceof Short
                || scale instanceof Integer || scale instanceof Long)
                && scale.longValue() == MINOR_UNIT_DECIMAL_SCALE;
    }

    private boolean isCapabilityRoot(A2uiResultSource source) {
        return source == A2uiResultSource.CAPABILITY_DATA
                || source == A2uiResultSource.CAPABILITY_META;
    }

    private boolean requiresSourcePath(A2uiResultSource source) {
        return source != A2uiResultSource.CONSTANT;
    }

    private boolean readsBusinessDataThroughMetadata(A2uiResultSource source, String sourcePath) {
        if (source != A2uiResultSource.CAPABILITY_META || isBlank(sourcePath)) {
            return false;
        }
        String normalized = sourcePath.trim();
        return BUSINESS_DATA_ROOT_POINTER.equals(normalized)
                || normalized.startsWith(BUSINESS_DATA_ROOT_POINTER + "/");
    }

    private List<A2uiCompiledShowInputBinding> compileInputBindings(List<A2uiShowInputBinding> bindings) {
        List<A2uiCompiledShowInputBinding> compiled = bindings.stream()
                .map(binding -> new A2uiCompiledShowInputBinding(
                        binding.getTargetMessageIndex(), binding.getTargetPath(), binding.getSource(),
                        binding.getSourcePath(), binding.isRequired(),
                        A2uiImmutableJsonSupport.immutableValue(binding.getConstantValue())))
                .sorted(Comparator.comparingInt(A2uiCompiledShowInputBinding::getTargetMessageIndex)
                        .thenComparing(A2uiCompiledShowInputBinding::getTargetPath))
                .collect(Collectors.toList());
        return Collections.unmodifiableList(compiled);
    }

    /** 校验显式操作区引用，禁止将根节点、嵌套节点或缺失组件移出内容树。 */
    private void validateFooterComponents(A2uiApplicationDraft draft) {
        for (A2uiSurfaceDeclaration surface : draft.getShowTemplate().getSurfaceDeclarations()) {
            List<String> footerIds = surface.getFooterComponentIds();
            if (footerIds == null || footerIds.isEmpty()) {
                continue;
            }
            Map<String, Map<?, ?>> components = new HashMap<>();
            for (Map<String, Object> message : draft.getShowTemplate().getMessageTemplates()) {
                Object raw = message.get(FIELD_UPDATE_COMPONENTS);
                if (!(raw instanceof Map)) {
                    continue;
                }
                Map<?, ?> update = (Map<?, ?>) raw;
                if (!Objects.equals(surface.getSurfaceId(), update.get(FIELD_SURFACE_ID))) {
                    continue;
                }
                for (Object item : (List<?>) update.get(FIELD_COMPONENTS)) {
                    Map<?, ?> component = (Map<?, ?>) item;
                    components.put((String) component.get(FIELD_COMPONENT_ID), component);
                }
            }
            Map<?, ?> root = components.get(surface.getRootComponentId());
            if (new HashSet<>(footerIds).size() != footerIds.size()
                    || root == null || !(root.get(FIELD_CHILDREN) instanceof List)) {
                throw failure(DRAFT_INVALID);
            }
            for (String id : footerIds) {
                if (isBlank(id) || id.equals(surface.getRootComponentId())
                        || !components.containsKey(id) || !((List<?>) root.get(FIELD_CHILDREN)).contains(id)
                        || !FOOTER_COMPONENT_TYPE.equals(components.get(id).get(FOOTER_TYPE_FIELD))
                        || components.values().stream().filter(value -> value.get(FIELD_CHILDREN) instanceof List
                                && ((List<?>) value.get(FIELD_CHILDREN)).contains(id)).count() != 1) {
                    throw failure(DRAFT_INVALID);
                }
            }
        }
    }

    private List<A2uiCompiledSurfaceDeclaration> compileSurfaces(List<A2uiSurfaceDeclaration> surfaces) {
        List<A2uiCompiledSurfaceDeclaration> compiled = surfaces.stream()
                .map(value -> new A2uiCompiledSurfaceDeclaration(
                        value.getSurfaceId(), value.getRootComponentId(),
                        List.copyOf(value.getFooterComponentIds() == null
                                ? Collections.emptyList() : value.getFooterComponentIds())))
                .sorted(Comparator.comparing(A2uiCompiledSurfaceDeclaration::getSurfaceId))
                .collect(Collectors.toList());
        return Collections.unmodifiableList(compiled);
    }

    private boolean matches(A2uiActionBinding binding, A2uiActionDeclaration declaration) {
        return Objects.equals(binding.getSurfaceId(), declaration.getSurfaceId())
                && Objects.equals(binding.getSourceComponentId(), declaration.getSourceComponentId())
                && Objects.equals(binding.getActionCode(), declaration.getActionCode());
    }

    private void validateContextSchema(A2uiActionBinding binding, A2uiActionDeclaration declaration,
            Map<String, Set<String>> contextFieldsByDeclarationKey) {
        Set<String> contextFields = contextFieldsByDeclarationKey.getOrDefault(
                declarationKey(declaration), Collections.emptySet());
        Object rawProperties = binding.getContextSchema().get("properties");
        if (!contextFields.isEmpty()
                && (!(rawProperties instanceof Map)
                || !((Map<?, ?>) rawProperties).keySet().containsAll(contextFields))) {
            throw failure(ACTION_CONTEXT_SCHEMA_MISMATCH);
        }
    }

    private String declarationKey(A2uiActionDeclaration declaration) {
        return String.valueOf(declaration.getSurfaceId()) + "\u0000"
                + String.valueOf(declaration.getSourceComponentId()) + "\u0000"
                + String.valueOf(declaration.getActionCode());
    }

    private String declarationKey(A2uiScannedActionDeclaration declaration) {
        return String.valueOf(declaration.getSurfaceId()) + "\u0000"
                + String.valueOf(declaration.getSourceComponentId()) + "\u0000"
                + String.valueOf(declaration.getActionCode());
    }

    private String actionKey(String surfaceId, String sourceComponentId, String actionCode) {
        return String.valueOf(surfaceId) + "\u0000" + String.valueOf(sourceComponentId)
                + "\u0000" + String.valueOf(actionCode);
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private A2uiApplicationValidationException failure(A2uiApplicationErrorCode errorCode) {
        return new A2uiApplicationValidationException(errorCode);
    }

}
