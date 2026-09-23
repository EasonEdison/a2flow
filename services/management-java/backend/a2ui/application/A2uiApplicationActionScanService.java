package dev.a2flow.management.a2ui.application;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionDeclarationSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionDeclarationSourceType;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionDeclarationStatus;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationActionScanResult;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiScannedActionDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowTemplate;

/**
 * 扫描当前未保存 Application 作者态中的完整 Action 声明闭包。
 *
 * <p>声明只来自初始 ShowTemplate、Binding 根管线与全部成功分支的 MESSAGE_TEMPLATE 和 PASSTHROUGH 显式声明；
 * runtime/demo payload 不参与扫描。本服务不持久化、不修改 Binding，也不解析 Capability。
 */
@Service
public class A2uiApplicationActionScanService {

    private static final String FIELD_SHOW_TEMPLATE = "showTemplate";
    private static final String FIELD_MESSAGE_TEMPLATES = "messageTemplates";
    private static final String FIELD_ACTION_BINDINGS = "actionBindings";
    private static final String FIELD_RESULT_ADAPTERS = "resultAdapters";
    private static final String FIELD_FAILURE_RESULT_ADAPTERS = "failureResultAdapters";
    private static final String FIELD_SUCCESS_BRANCHES = "successBranches";
    private static final String FIELD_BINDING_ID = "bindingId";
    private static final String FIELD_MESSAGE_TEMPLATE = "messageTemplate";
    private static final String OUTCOME_SUCCESS = "SUCCESS";
    private static final String OUTCOME_FAILURE = "FAILURE";
    private static final String PATH_ACTION_BINDINGS = "/actionBindings/";
    private static final String FIELD_EMITTED_ACTION_DECLARATIONS = "emittedActionDeclarations";
    private static final String TYPE_MESSAGE_TEMPLATE = "MESSAGE_TEMPLATE";
    private static final String TYPE_A2UI_PASSTHROUGH = "A2UI_PASSTHROUGH";
    private static final String ERROR_ACTION_UNBOUND = "A2UI_ACTION_UNBOUND";
    private static final String ERROR_ACTION_UNREFERENCED = "A2UI_ACTION_UNREFERENCED";
    private static final String ERROR_ACTION_RESERVED = "A2UI_ACTION_RESERVED";
    private static final String ERROR_ACTION_NEEDS_REVALIDATION =
            "A2UI_ACTION_NEEDS_REVALIDATION";
    private static final String ERROR_ACTION_DECLARATION_CONFLICT =
            "A2UI_ACTION_DECLARATION_CONFLICT";
    private static final String ERROR_ACTION_BINDING_AMBIGUOUS =
            "A2UI_ACTION_BINDING_AMBIGUOUS";
    private static final String ERROR_PASSTHROUGH_DECLARATION_REQUIRED =
            "A2UI_PASSTHROUGH_ACTION_DECLARATION_REQUIRED";
    private static final String ERROR_ACTION_SCAN_INVALID = "A2UI_ACTION_SCAN_INVALID";

    private final A2uiShowTemplateAnalyzer showTemplateAnalyzer = new A2uiShowTemplateAnalyzer();

    /** 扫描一份作者态快照并返回只读分析结果，不改写调用方 Map。 */
    public A2uiApplicationActionScanResult scan(Map<String, Object> source) {
        Map<String, Object> immutableSource = mapCopy(source);
        ScanContext context = new ScanContext();
        Map<String, Object> show = mapValue(immutableSource.get(FIELD_SHOW_TEMPLATE));
        validateShow(immutableSource, show, context);
        scanMessages(listValue(show == null ? null : show.get(FIELD_MESSAGE_TEMPLATES)),
                DiscoverySource.showTemplate(), context);

        List<Map<String, Object>> bindings = mapList(immutableSource.get(FIELD_ACTION_BINDINGS));
        scanBindingAdapters(bindings, context);
        addUnreferencedBindings(bindings, context);
        return result(immutableSource, bindings, context);
    }

    /** 发布前按扫描结果 fail closed；调用方不得提交或覆盖该结果。 */
    public void requireReleaseClosure(A2uiApplicationActionScanResult result) {
        List<String> blockers = result == null
                ? List.of(ERROR_ACTION_SCAN_INVALID) : result.getReleaseBlockers();
        for (String blocker : blockers == null ? Collections.<String>emptyList() : blockers) {
            if (blocker.startsWith(ERROR_PASSTHROUGH_DECLARATION_REQUIRED)) {
                throw failure(A2uiApplicationErrorCode.RESULT_ADAPTER_INVALID);
            }
            if (blocker.startsWith(ERROR_ACTION_RESERVED)) {
                throw failure(A2uiApplicationErrorCode.ACTION_CODE_RESERVED);
            }
            if (blocker.startsWith(ERROR_ACTION_BINDING_AMBIGUOUS)) {
                throw failure(A2uiApplicationErrorCode.ACTION_BINDING_AMBIGUOUS);
            }
            if (blocker.startsWith(ERROR_ACTION_UNBOUND)) {
                throw failure(A2uiApplicationErrorCode.ACTION_UNBOUND);
            }
            if (blocker.startsWith(ERROR_ACTION_NEEDS_REVALIDATION)) {
                throw failure(A2uiApplicationErrorCode.ACTION_CONTEXT_SCHEMA_MISMATCH);
            }
            if (blocker.startsWith(ERROR_ACTION_UNREFERENCED)
                    || blocker.startsWith(ERROR_ACTION_DECLARATION_CONFLICT)) {
                throw failure(A2uiApplicationErrorCode.ACTION_BINDING_ORPHAN);
            }
            if (blocker.startsWith(A2uiApplicationErrorCode.SHOW_INPUT_AUTHORITY_FORBIDDEN.getCode())) {
                throw failure(A2uiApplicationErrorCode.SHOW_INPUT_AUTHORITY_FORBIDDEN);
            }
            if (blocker.startsWith(A2uiApplicationErrorCode.SHOW_INVALID.getCode())) {
                throw failure(A2uiApplicationErrorCode.SHOW_INVALID);
            }
            throw failure(A2uiApplicationErrorCode.DRAFT_INVALID);
        }
    }

    private void validateShow(Map<String, Object> source, Map<String, Object> show,
            ScanContext context) {
        try {
            A2uiShowTemplate template = JsonSupport.fromJSON(
                    JsonSupport.toJSON(show), A2uiShowTemplate.class);
            String catalogId = stringValue(source.get("catalogId"));
            if (catalogId == null) {
                Map<String, Object> catalog = mapValue(source.get("catalog"));
                catalogId = stringValue(catalog == null ? null : catalog.get("catalogId"));
            }
            showTemplateAnalyzer.analyze(template, catalogId);
            showTemplateAnalyzer.validateInputBindings(template);
        } catch (A2uiApplicationValidationException exception) {
            addProblem(context, exception.getErrorCode());
        } catch (RuntimeException exception) {
            addProblem(context, ERROR_ACTION_SCAN_INVALID);
        }
    }

    /** 从已可达 Action 展开根管线和每个成功分支，新增声明继续进入同一闭包队列。 */
    private void scanBindingAdapters(List<Map<String, Object>> bindings, ScanContext context) {
        Set<String> scannedKeys = new LinkedHashSet<>();
        while (!context.pendingKeys.isEmpty()) {
            String key = context.pendingKeys.removeFirst();
            if (!scannedKeys.add(key)) {
                continue;
            }
            DeclarationAggregate declaration = context.declarations.get(key);
            if (declaration == null || A2uiReservedActionCode.isReserved(declaration.actionCode)) {
                continue;
            }
            List<Map<String, Object>> matches = matchingBindings(bindings, declaration);
            if (matches.size() != 1) {
                continue;
            }
            Map<String, Object> binding = matches.get(0);
            String bindingId = stringValue(binding.get(FIELD_BINDING_ID));
            String bindingPath = PATH_ACTION_BINDINGS + bindingId;
            scanAdapters(mapList(binding.get(FIELD_RESULT_ADAPTERS)),
                    DiscoverySource.messageTemplate(bindingPath + "/" + FIELD_RESULT_ADAPTERS,
                            bindingId, OUTCOME_SUCCESS, null), context);
            scanAdapters(mapList(binding.get(FIELD_FAILURE_RESULT_ADAPTERS)),
                    DiscoverySource.messageTemplate(bindingPath + "/" + FIELD_FAILURE_RESULT_ADAPTERS,
                            bindingId, OUTCOME_FAILURE, null), context);
            List<Map<String, Object>> branches = mapList(binding.get(FIELD_SUCCESS_BRANCHES));
            for (int branchIndex = 0; branchIndex < branches.size(); branchIndex++) {
                scanAdapters(mapList(branches.get(branchIndex).get(FIELD_RESULT_ADAPTERS)),
                        DiscoverySource.messageTemplate(bindingPath + "/" + FIELD_SUCCESS_BRANCHES
                                        + "/" + branchIndex + "/" + FIELD_RESULT_ADAPTERS,
                                bindingId, OUTCOME_SUCCESS, null), context);
            }
        }
    }

    /** 扫描单条结果管线，分支位置保存在来源路径中，绑定身份仍归属父 Action。 */
    private void scanAdapters(List<Map<String, Object>> adapters, DiscoverySource discovery,
            ScanContext context) {
        for (int index = 0; index < adapters.size(); index++) {
            Map<String, Object> adapter = adapters.get(index);
            String type = stringValue(adapter.get("type"));
            String adapterId = stringValue(adapter.get("adapterId"));
            String path = discovery.basePath + "/" + index;
            if (TYPE_MESSAGE_TEMPLATE.equals(type)) {
                if (!(adapter.get(FIELD_MESSAGE_TEMPLATE) instanceof Map)) {
                    addProblem(context, ERROR_ACTION_SCAN_INVALID + ":" + path);
                    continue;
                }
                scanMessages(List.of(adapter.get(FIELD_MESSAGE_TEMPLATE)),
                        DiscoverySource.messageTemplate(
                                path, discovery.bindingId, discovery.outcome, adapterId), context);
            } else if (TYPE_A2UI_PASSTHROUGH.equals(type)) {
                scanPassthrough(adapter, path, discovery.bindingId, discovery.outcome, adapterId, context);
            }
        }
    }

    private void scanPassthrough(Map<String, Object> adapter, String path, String bindingId,
            String outcome, String adapterId, ScanContext context) {
        List<Map<String, Object>> declarations = mapList(
                adapter.get(FIELD_EMITTED_ACTION_DECLARATIONS));
        if (declarations.isEmpty()) {
            addProblem(context, ERROR_PASSTHROUGH_DECLARATION_REQUIRED + ":" + path);
            return;
        }
        for (int index = 0; index < declarations.size(); index++) {
            Map<String, Object> declaration = declarations.get(index);
            String surfaceId = stringValue(declaration.get("surfaceId"));
            String componentId = stringValue(declaration.get("sourceComponentId"));
            String actionCode = stringValue(declaration.get("actionCode"));
            Map<String, Object> contextSchema = mapValue(declaration.get("contextSchema"));
            A2uiActionDeclarationSource source = actionSource(
                    A2uiActionDeclarationSourceType.A2UI_PASSTHROUGH,
                    path + "/" + FIELD_EMITTED_ACTION_DECLARATIONS + "/" + index,
                    bindingId, outcome, adapterId);
            Map<String, Object> effectiveSchema = contextSchema == null
                    ? Collections.emptyMap() : contextSchema;
            addDeclaration(new DiscoveredDeclaration(surfaceId, componentId, actionCode,
                    null, effectiveSchema, schemaFields(effectiveSchema), source), context);
        }
    }

    private void scanMessages(List<?> messages, DiscoverySource discovery,
            ScanContext context) {
        if (messages == null) {
            addProblem(context, ERROR_ACTION_SCAN_INVALID + ":" + discovery.basePath);
            return;
        }
        for (int messageIndex = 0; messageIndex < messages.size(); messageIndex++) {
            Map<String, Object> message = mapValue(messages.get(messageIndex));
            Map<String, Object> update = message == null
                    ? null : mapValue(message.get("updateComponents"));
            if (update == null) {
                continue;
            }
            String surfaceId = stringValue(update.get("surfaceId"));
            List<Map<String, Object>> components = mapList(update.get("components"));
            for (int componentIndex = 0; componentIndex < components.size(); componentIndex++) {
                Map<String, Object> component = components.get(componentIndex);
                String componentId = stringValue(component.get("id"));
                for (A2uiShowTemplateAnalyzer.ComponentAction componentAction
                        : showTemplateAnalyzer.componentActions(component)) {
                    Map<String, Object> event = componentAction.getEvent();
                    String actionCode = stringValue(event.get("name"));
                    Map<String, Object> actionContext = mapValue(event.get("context"));
                    Map<String, Object> contextValue = actionContext == null
                            ? Collections.emptyMap() : actionContext;
                    String path = discovery.basePath + "/" + messageIndex
                            + "/updateComponents/components/" + componentIndex
                            + componentAction.getPathSuffix();
                    addDeclaration(new DiscoveredDeclaration(surfaceId, componentId, actionCode,
                            A2uiImmutableJsonSupport.digest(contextValue), null,
                            contextValue.keySet(), actionSource(discovery.sourceType, path,
                                    discovery.bindingId, discovery.outcome,
                                    discovery.adapterId)), context);
                }
            }
        }
    }

    private void addDeclaration(DiscoveredDeclaration candidate, ScanContext context) {
        if (StringUtils.isAnyBlank(
                candidate.surfaceId, candidate.componentId, candidate.actionCode)) {
            addProblem(context, ERROR_ACTION_SCAN_INVALID + ":" + candidate.source.getPath());
            return;
        }
        String key = stableKey(
                candidate.surfaceId, candidate.componentId, candidate.actionCode);
        DeclarationAggregate aggregate = context.declarations.get(key);
        if (aggregate == null) {
            aggregate = new DeclarationAggregate(
                    candidate.surfaceId, candidate.componentId, candidate.actionCode);
            context.declarations.put(key, aggregate);
            context.pendingKeys.addLast(key);
        }
        aggregate.sources.add(candidate.source);
        aggregate.contextFields.addAll(candidate.contextFields == null
                ? Collections.emptySet() : candidate.contextFields);
        if (candidate.contextDigest != null) {
            if (aggregate.contextDigest != null
                    && !Objects.equals(aggregate.contextDigest, candidate.contextDigest)) {
                aggregate.conflict = true;
            }
            aggregate.contextDigest = aggregate.contextDigest == null
                    ? candidate.contextDigest : aggregate.contextDigest;
        }
        if (candidate.contextSchema != null) {
            Map<String, Object> schemaCopy = mapCopy(candidate.contextSchema);
            if (aggregate.explicitContextSchema != null
                    && !Objects.equals(aggregate.explicitContextSchema, schemaCopy)) {
                aggregate.conflict = true;
            }
            aggregate.explicitContextSchema = aggregate.explicitContextSchema == null
                    ? schemaCopy : aggregate.explicitContextSchema;
        }
    }

    private void addUnreferencedBindings(List<Map<String, Object>> bindings, ScanContext context) {
        for (Map<String, Object> binding : bindings) {
            String surfaceId = stringValue(binding.get("surfaceId"));
            String componentId = stringValue(binding.get("sourceComponentId"));
            String actionCode = stringValue(binding.get("actionCode"));
            if (StringUtils.isAnyBlank(surfaceId, componentId, actionCode)) {
                addProblem(context, ERROR_ACTION_SCAN_INVALID + ":/actionBindings");
                continue;
            }
            context.declarations.computeIfAbsent(stableKey(surfaceId, componentId, actionCode),
                    ignored -> new DeclarationAggregate(surfaceId, componentId, actionCode));
        }
    }

    private A2uiApplicationActionScanResult result(Map<String, Object> source,
            List<Map<String, Object>> bindings, ScanContext context) {
        List<A2uiScannedActionDeclaration> declarations = new ArrayList<>();
        for (DeclarationAggregate aggregate : context.declarations.values()) {
            List<Map<String, Object>> matches = matchingBindings(bindings, aggregate);
            A2uiActionDeclarationStatus status = status(aggregate, matches, context);
            Map<String, Object> schema = aggregate.explicitContextSchema;
            if ((schema == null || schema.isEmpty()) && matches.size() == 1) {
                schema = mapValue(matches.get(0).get("contextSchema"));
            }
            String digest = declarationDigest(aggregate, schema);
            declarations.add(new A2uiScannedActionDeclaration()
                    .setEventName(aggregate.actionCode)
                    .setSurfaceId(aggregate.surfaceId)
                    .setSourceComponentId(aggregate.componentId)
                    .setActionCode(aggregate.actionCode)
                    .setContextTemplateDigest(digest)
                    .setContextSchema(schema == null ? Collections.emptyMap() : mapCopy(schema))
                    .setContextFields(new ArrayList<>(aggregate.contextFields))
                    .setDiscoveredFrom(new ArrayList<>(aggregate.sources))
                    .setStatus(status));
        }
        declarations.sort(Comparator.comparing(A2uiScannedActionDeclaration::getSurfaceId)
                .thenComparing(A2uiScannedActionDeclaration::getSourceComponentId)
                .thenComparing(A2uiScannedActionDeclaration::getActionCode));
        return new A2uiApplicationActionScanResult()
                .setActionDeclarations(declarations)
                .setValidationErrors(new ArrayList<>(context.validationErrors))
                .setReleaseBlockers(new ArrayList<>(context.releaseBlockers))
                .setSourceDigest(A2uiImmutableJsonSupport.digest(source));
    }

    private A2uiActionDeclarationStatus status(DeclarationAggregate aggregate,
            List<Map<String, Object>> matches, ScanContext context) {
        if (A2uiReservedActionCode.isReserved(aggregate.actionCode)) {
            addProblem(context, ERROR_ACTION_RESERVED + ":" + aggregate.key());
            return A2uiActionDeclarationStatus.RESERVED;
        }
        if (aggregate.sources.isEmpty()) {
            addProblem(context, ERROR_ACTION_UNREFERENCED + ":" + aggregate.key());
            return A2uiActionDeclarationStatus.UNREFERENCED;
        }
        if (matches.isEmpty()) {
            addProblem(context, ERROR_ACTION_UNBOUND + ":" + aggregate.key());
            return A2uiActionDeclarationStatus.UNBOUND;
        }
        if (matches.size() > 1) {
            addProblem(context, ERROR_ACTION_BINDING_AMBIGUOUS + ":" + aggregate.key());
            return A2uiActionDeclarationStatus.NEEDS_REVALIDATION;
        }
        Map<String, Object> binding = matches.get(0);
        String declarationDigest = stringValue(binding.get("declarationDigest"));
        Map<String, Object> bindingSchema = mapValue(binding.get("contextSchema"));
        boolean digestChanged = declarationDigest != null
                && !Objects.equals(declarationDigest,
                        declarationDigest(aggregate, aggregate.explicitContextSchema));
        boolean schemaChanged = aggregate.explicitContextSchema != null
                && !Objects.equals(mapCopy(bindingSchema), aggregate.explicitContextSchema);
        if (aggregate.conflict || digestChanged || schemaChanged) {
            addProblem(context, (aggregate.conflict
                    ? ERROR_ACTION_DECLARATION_CONFLICT : ERROR_ACTION_NEEDS_REVALIDATION)
                    + ":" + aggregate.key());
            return A2uiActionDeclarationStatus.NEEDS_REVALIDATION;
        }
        return A2uiActionDeclarationStatus.BOUND;
    }

    private String declarationDigest(DeclarationAggregate aggregate,
            Map<String, Object> contextSchema) {
        return aggregate.contextDigest != null
                ? aggregate.contextDigest
                : A2uiImmutableJsonSupport.digest(contextSchema == null
                        ? Collections.emptyMap() : contextSchema);
    }

    private List<Map<String, Object>> matchingBindings(List<Map<String, Object>> bindings,
            DeclarationAggregate declaration) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> binding : bindings) {
            if (Objects.equals(declaration.surfaceId, binding.get("surfaceId"))
                    && Objects.equals(declaration.componentId, binding.get("sourceComponentId"))
                    && Objects.equals(declaration.actionCode, binding.get("actionCode"))) {
                result.add(binding);
            }
        }
        return result;
    }

    private A2uiActionDeclarationSource actionSource(A2uiActionDeclarationSourceType sourceType,
            String path, String bindingId, String outcome, String adapterId) {
        return new A2uiActionDeclarationSource()
                .setSourceType(sourceType)
                .setPath(path)
                .setBindingId(bindingId)
                .setOutcome(outcome)
                .setAdapterId(adapterId);
    }

    private void addProblem(ScanContext context, String problem) {
        context.validationErrors.add(problem);
        context.releaseBlockers.add(problem);
    }

    private Set<String> schemaFields(Map<String, Object> schema) {
        Map<String, Object> properties = mapValue(schema.get("properties"));
        return properties == null ? Collections.emptySet() : properties.keySet();
    }

    private String stableKey(String surfaceId, String componentId, String actionCode) {
        return surfaceId + "\u0000" + componentId + "\u0000" + actionCode;
    }

    private String stringValue(Object value) {
        return value instanceof String && StringUtils.isNotBlank((String) value)
                ? (String) value : null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapCopy(Map<String, Object> value) {
        if (value == null) {
            return new LinkedHashMap<>();
        }
        Object canonical = A2uiImmutableJsonSupport.canonicalize(value);
        return canonical instanceof Map
                ? new LinkedHashMap<>((Map<String, Object>) canonical) : new LinkedHashMap<>();
    }

    private List<?> listValue(Object value) {
        return value instanceof List ? (List<?>) value : null;
    }

    private List<Map<String, Object>> mapList(Object value) {
        List<?> values = listValue(value);
        if (values == null) {
            return Collections.emptyList();
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : values) {
            Map<String, Object> map = mapValue(item);
            if (map != null) {
                result.add(map);
            }
        }
        return result;
    }

    private A2uiApplicationValidationException failure(A2uiApplicationErrorCode errorCode) {
        return new A2uiApplicationValidationException(errorCode);
    }

    private static final class ScanContext {
        private final Map<String, DeclarationAggregate> declarations = new LinkedHashMap<>();
        private final Deque<String> pendingKeys = new ArrayDeque<>();
        private final Set<String> validationErrors = new LinkedHashSet<>();
        private final Set<String> releaseBlockers = new LinkedHashSet<>();
    }

    private static final class DiscoveredDeclaration {
        private final String surfaceId;
        private final String componentId;
        private final String actionCode;
        private final String contextDigest;
        private final Map<String, Object> contextSchema;
        private final Set<String> contextFields;
        private final A2uiActionDeclarationSource source;

        private DiscoveredDeclaration(String surfaceId, String componentId, String actionCode,
                String contextDigest, Map<String, Object> contextSchema,
                Set<String> contextFields, A2uiActionDeclarationSource source) {
            this.surfaceId = surfaceId;
            this.componentId = componentId;
            this.actionCode = actionCode;
            this.contextDigest = contextDigest;
            this.contextSchema = contextSchema;
            this.contextFields = contextFields;
            this.source = source;
        }
    }

    private static final class DiscoverySource {
        private final A2uiActionDeclarationSourceType sourceType;
        private final String basePath;
        private final String bindingId;
        private final String outcome;
        private final String adapterId;

        private DiscoverySource(A2uiActionDeclarationSourceType sourceType, String basePath,
                String bindingId, String outcome, String adapterId) {
            this.sourceType = sourceType;
            this.basePath = basePath;
            this.bindingId = bindingId;
            this.outcome = outcome;
            this.adapterId = adapterId;
        }

        private static DiscoverySource showTemplate() {
            return new DiscoverySource(A2uiActionDeclarationSourceType.SHOW_TEMPLATE,
                    "/showTemplate/messageTemplates", null, null, null);
        }

        private static DiscoverySource messageTemplate(String basePath, String bindingId,
                String outcome, String adapterId) {
            return new DiscoverySource(A2uiActionDeclarationSourceType.MESSAGE_TEMPLATE,
                    basePath, bindingId, outcome, adapterId);
        }
    }

    private static final class DeclarationAggregate {
        private final String surfaceId;
        private final String componentId;
        private final String actionCode;
        private final List<A2uiActionDeclarationSource> sources = new ArrayList<>();
        private final Set<String> contextFields = new LinkedHashSet<>();
        private String contextDigest;
        private Map<String, Object> explicitContextSchema;
        private boolean conflict;

        private DeclarationAggregate(String surfaceId, String componentId, String actionCode) {
            this.surfaceId = surfaceId;
            this.componentId = componentId;
            this.actionCode = actionCode;
        }

        private String key() {
            return surfaceId + ":" + componentId + ":" + actionCode;
        }
    }
}
