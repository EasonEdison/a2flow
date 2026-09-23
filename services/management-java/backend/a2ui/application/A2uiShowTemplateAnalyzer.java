package dev.a2flow.management.a2ui.application;

import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.SHOW_INPUT_AUTHORITY_FORBIDDEN;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.SHOW_INVALID;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiActionDeclaration;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowInputSource;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiShowTemplate;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiSurfaceDeclaration;

import lombok.Value;

/**
 * Application 私有 ShowTemplate 的协议结构分析器。
 *
 * <p>上游传入完整 v0.9.1 message AST，下游获得只读 component type 与 derived ActionDeclaration。
 * 本类校验 Surface/组件/root/children/action/input authority；不读取第二份 Action JSON、不执行模板
 * 绑定，也不负责 Catalog Renderer 或运行时 MessageProcessor。
 */
final class A2uiShowTemplateAnalyzer {

    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final Set<String> SERVER_MESSAGE_KEYS = Set.of(
            "createSurface", "updateComponents", "updateDataModel", "deleteSurface");
    private static final Set<String> FORBIDDEN_PRESENTATION_CONTEXT = Set.of(
            "authorization", "cookie", "credential", "credentials", "environment",
            "transportauthority", "transport_authority");
    private static final String FIELD_ACTION = "action";
    private static final String FIELD_CHANGE_ACTION = "changeAction";
    private static final String FIELD_ACTIONS = "actions";
    private static final String FIELD_EVENT = "event";

    ShowFacts analyze(A2uiShowTemplate show, String catalogId) {
        validateShowHeader(show);
        Set<String> createdSurfaces = new HashSet<>();
        Set<String> deletedSurfaces = new HashSet<>();
        Set<String> componentKeys = new HashSet<>();
        Set<String> componentTypes = new HashSet<>();
        List<A2uiActionDeclaration> declarations = new ArrayList<>();
        Map<String, Set<String>> contextFieldsByDeclarationKey = new HashMap<>();
        for (Map<String, Object> message : show.getMessageTemplates()) {
            String messageType = validateServerMessage(message);
            Map<String, Object> payload = mapValue(message.get(messageType));
            String surfaceId = payload == null ? null : stringValue(payload.get("surfaceId"));
            if (surfaceId == null) {
                throw failure(SHOW_INVALID);
            }
            if ("createSurface".equals(messageType)) {
                validateCreateSurface(catalogId, surfaceId, payload, createdSurfaces, deletedSurfaces);
            } else if (!createdSurfaces.contains(surfaceId) || deletedSurfaces.contains(surfaceId)) {
                throw failure(SHOW_INVALID);
            } else if ("updateComponents".equals(messageType)) {
                analyzeComponents(surfaceId, payload.get("components"), componentKeys,
                        componentTypes, declarations, contextFieldsByDeclarationKey);
            } else if ("updateDataModel".equals(messageType)
                    && stringValue(payload.get("path")) == null) {
                throw failure(SHOW_INVALID);
            } else if ("deleteSurface".equals(messageType)) {
                deletedSurfaces.add(surfaceId);
            }
        }
        validateSurfaceRoots(show.getSurfaceDeclarations(), componentKeys);
        List<String> sortedTypes = new ArrayList<>(componentTypes);
        Collections.sort(sortedTypes);
        declarations.sort(Comparator.comparing(A2uiActionDeclaration::getSurfaceId)
                .thenComparing(A2uiActionDeclaration::getActionCode)
                .thenComparing(A2uiActionDeclaration::getSourceComponentId));
        return new ShowFacts(Collections.unmodifiableList(sortedTypes),
                Collections.unmodifiableList(declarations), immutableContextFields(contextFieldsByDeclarationKey));
    }

    void validateInputBindings(A2uiShowTemplate show) {
        for (A2uiShowInputBinding binding : show.getInputBindings()) {
            if (binding == null
                    || binding.getTargetMessageIndex() < 0
                    || binding.getTargetMessageIndex() >= show.getMessageTemplates().size()
                    || isBlank(binding.getTargetPath())
                    || binding.getSource() == null) {
                throw failure(SHOW_INVALID);
            }
            String sourcePath = normalizeContextPath(binding.getSourcePath());
            String targetPath = normalizeContextPath(binding.getTargetPath());
            if (containsForbiddenContext(targetPath)
                    || binding.getSource() == A2uiShowInputSource.TRUSTED_CONTEXT
                    && (isBlank(sourcePath) || containsForbiddenContext(sourcePath))) {
                throw failure(SHOW_INPUT_AUTHORITY_FORBIDDEN);
            }
        }
    }

    String validateServerMessage(Map<String, Object> message) {
        if (message == null || !PROTOCOL_VERSION.equals(message.get("version")) || message.size() != 2) {
            throw failure(SHOW_INVALID);
        }
        List<String> types = SERVER_MESSAGE_KEYS.stream().filter(message::containsKey).collect(Collectors.toList());
        if (types.size() != 1 || mapValue(message.get(types.get(0))) == null) {
            throw failure(SHOW_INVALID);
        }
        return types.get(0);
    }

    private void validateShowHeader(A2uiShowTemplate show) {
        if (show == null
                || isBlank(show.getTemplateCode())
                || show.getParamsSchema() == null
                || show.getSurfaceDeclarations() == null
                || show.getMessageTemplates() == null
                || show.getMessageTemplates().isEmpty()
                || show.getInputBindings() == null) {
            throw failure(SHOW_INVALID);
        }
    }

    private void validateCreateSurface(String catalogId, String surfaceId, Map<String, Object> payload,
            Set<String> createdSurfaces, Set<String> deletedSurfaces) {
        if (!Objects.equals(catalogId, payload.get("catalogId"))
                || createdSurfaces.contains(surfaceId) && !deletedSurfaces.contains(surfaceId)) {
            throw failure(SHOW_INVALID);
        }
        createdSurfaces.add(surfaceId);
        deletedSurfaces.remove(surfaceId);
    }

    private void validateSurfaceRoots(List<A2uiSurfaceDeclaration> surfaces, Set<String> componentKeys) {
        for (A2uiSurfaceDeclaration surface : surfaces) {
            if (surface == null
                    || !componentKeys.contains(componentKey(surface.getSurfaceId(), surface.getRootComponentId()))) {
                throw failure(SHOW_INVALID);
            }
        }
    }

    private void analyzeComponents(String surfaceId, Object rawComponents, Set<String> componentKeys,
            Set<String> componentTypes, List<A2uiActionDeclaration> declarations,
            Map<String, Set<String>> contextFieldsByDeclarationKey) {
        List<?> components = listValue(rawComponents);
        if (components == null) {
            throw failure(SHOW_INVALID);
        }
        for (Object rawComponent : components) {
            Map<String, Object> component = mapValue(rawComponent);
            String componentId = component == null ? null : stringValue(component.get("id"));
            String componentType = component == null ? null : stringValue(component.get("component"));
            if (componentId == null || componentType == null
                    || !componentKeys.add(componentKey(surfaceId, componentId))) {
                throw failure(SHOW_INVALID);
            }
            componentTypes.add(componentType);
            addActionDeclaration(surfaceId, componentId, component,
                    declarations, contextFieldsByDeclarationKey);
        }
        validateChildren(surfaceId, components, componentKeys);
    }

    private void addActionDeclaration(String surfaceId, String componentId, Map<String, Object> component,
            List<A2uiActionDeclaration> declarations,
            Map<String, Set<String>> contextFieldsByDeclarationKey) {
        for (ComponentAction componentAction : componentActions(component)) {
            Map<String, Object> event = componentAction.getEvent();
            String actionCode = stringValue(event.get("name"));
            if (actionCode == null) {
                throw failure(SHOW_INVALID);
            }
            Map<String, Object> context = mapValue(event.get("context"));
            String contextDigest = A2uiImmutableJsonSupport.digest(
                    context == null ? Collections.emptyMap() : context);
            declarations.add(new A2uiActionDeclaration(
                    surfaceId, componentId, actionCode, contextDigest));
            String declarationKey = declarationKey(surfaceId, componentId, actionCode);
            Set<String> contextFields = context == null
                    ? Collections.emptySet() : new HashSet<>(context.keySet());
            if (contextFieldsByDeclarationKey.put(declarationKey, contextFields) != null) {
                throw failure(SHOW_INVALID);
            }
        }
    }

    /**
     * 统一抽取单动作、变化动作与按钮组的作者态事件；子动作仍归属外层组件 id，避免生成第二份组件身份。
     */
    List<ComponentAction> componentActions(Map<String, Object> component) {
        List<ComponentAction> result = new ArrayList<>();
        addComponentAction(result, mapValue(component.get(FIELD_ACTION)), "/action/event");
        addComponentAction(result, mapValue(component.get(FIELD_CHANGE_ACTION)),
                "/changeAction/event");
        List<?> actions = listValue(component.get(FIELD_ACTIONS));
        if (actions == null) {
            return result;
        }
        for (int index = 0; index < actions.size(); index++) {
            Map<String, Object> item = mapValue(actions.get(index));
            Map<String, Object> action = item == null
                    ? null : mapValue(item.get(FIELD_ACTION));
            addComponentAction(result, action,
                    "/actions/" + index + "/action/event");
        }
        return result;
    }

    private void addComponentAction(List<ComponentAction> result,
            Map<String, Object> action, String pathSuffix) {
        Map<String, Object> event = action == null ? null : mapValue(action.get(FIELD_EVENT));
        if (event != null) {
            result.add(new ComponentAction(event, pathSuffix));
        }
    }

    private void validateChildren(String surfaceId, List<?> components, Set<String> componentKeys) {
        for (Object rawComponent : components) {
            Map<String, Object> component = mapValue(rawComponent);
            List<?> children = component == null ? null : listValue(component.get("children"));
            if (children == null) {
                continue;
            }
            for (Object child : children) {
                if (!componentKeys.contains(componentKey(surfaceId, stringValue(child)))) {
                    throw failure(SHOW_INVALID);
                }
            }
        }
    }

    private String componentKey(String surfaceId, String componentId) {
        return String.valueOf(surfaceId) + "\u0000" + String.valueOf(componentId);
    }

    private String normalizeContextPath(String sourcePath) {
        if (sourcePath == null) {
            return null;
        }
        return sourcePath.replace("/", "")
                .replace(".", "")
                .replace("_", "")
                .replace("-", "")
                .toLowerCase();
    }

    private boolean containsForbiddenContext(String normalizedPath) {
        return !isBlank(normalizedPath)
                && FORBIDDEN_PRESENTATION_CONTEXT.stream().anyMatch(normalizedPath::contains);
    }

    private String declarationKey(String surfaceId, String componentId, String actionCode) {
        return String.valueOf(surfaceId) + "\u0000" + String.valueOf(componentId)
                + "\u0000" + String.valueOf(actionCode);
    }

    private Map<String, Set<String>> immutableContextFields(Map<String, Set<String>> source) {
        Map<String, Set<String>> copy = new HashMap<>();
        source.forEach((key, fields) -> copy.put(key,
                Collections.unmodifiableSet(new HashSet<>(fields))));
        return Collections.unmodifiableMap(copy);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : null;
    }

    private List<?> listValue(Object value) {
        return value instanceof List ? (List<?>) value : null;
    }

    private String stringValue(Object value) {
        return value instanceof String && !isBlank((String) value) ? (String) value : null;
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private A2uiApplicationValidationException failure(A2uiApplicationErrorCode errorCode) {
        return new A2uiApplicationValidationException(errorCode);
    }

    @Value
    static class ShowFacts {
        private List<String> componentTypes;
        private List<A2uiActionDeclaration> actionDeclarations;
        private Map<String, Set<String>> contextFieldsByDeclarationKey;
    }

    @Value
    static class ComponentAction {
        private Map<String, Object> event;
        private String pathSuffix;
    }
}
