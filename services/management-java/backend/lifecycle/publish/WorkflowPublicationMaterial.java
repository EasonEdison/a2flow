package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowNodeType;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowSkillNode;
import dev.a2flow.management.release.WorkflowReleasePayload;
import static dev.a2flow.management.lifecycle.publish.PublicationJson.*;

/** Projects only supported linear plans; unsupported execution semantics fail closed. */
final class WorkflowPublicationMaterial {
    private WorkflowPublicationMaterial() { }

    static ObjectNode definition(WorkflowReleasePayload payload) throws IOException {
        var plan = payload.getCompiledPlan();
        var graph = payload.getWorkflowGraph();
        if (plan == null || graph == null || !plan.getRouterDefinitions().isEmpty()
                || !plan.getParallelDefinitions().isEmpty()
                || plan.getNodeMap().size() < 3 || plan.getNodeMap().size() > 9) {
            throw failure("WORKFLOW_RUNTIME_REQUIRES_LINEAR_SKILLS");
        }
        var summary = graph.getSummaryConfig();
        if (summary == null || (summary.getDetailSummaryPrompt() != null
                && !summary.getDetailSummaryPrompt().isBlank())
                || (summary.getHandlingSuggestions() != null && !summary.getHandlingSuggestions().isEmpty())) {
            throw failure("WORKFLOW_RUNTIME_SUMMARY_OPTIONS_UNSUPPORTED");
        }
        for (var node : graph.getNodes()) {
            if (node instanceof WorkflowSkillNode skill && skill.getQuickTriggerMessage() != null
                    && !skill.getQuickTriggerMessage().isBlank()) {
                throw failure("WORKFLOW_RUNTIME_QUICK_TRIGGER_UNSUPPORTED");
            }
        }
        ArrayNode nodes = array();
        Set<String> visited = new HashSet<>();
        String next = plan.getEntryNodeCode();
        while (!plan.getSummaryNodeCode().equals(next)) {
            var node = plan.getNodeMap().get(next);
            if (node == null || node.getNodeType() != WorkflowNodeType.SKILL || !visited.add(next)) {
                throw failure("WORKFLOW_RUNTIME_REQUIRES_LINEAR_SKILLS");
            }
            if (node.isAllowSkip()) throw failure("WORKFLOW_RUNTIME_SKIP_UNSUPPORTED");
            ObjectNode projected = object("nodeId", node.getNodeCode(), "skillKey", node.getSkillCode(),
                    "nodePrompt", node.getNodePrompt());
            if (node.getDisplayName() != null) projected.put("displayName", node.getDisplayName());
            nodes.add(projected);
            next = plan.getFixedSuccessorByNode().get(next);
        }
        if (visited.size() + 1 != plan.getNodeMap().size()
                || plan.getFixedSuccessorByNode().size() != visited.size()
                || plan.getEdgeMap().size() != visited.size()
                || plan.getFixedSuccessorByNode().containsKey(plan.getSummaryNodeCode())) {
            throw failure("WORKFLOW_RUNTIME_REQUIRES_LINEAR_SKILLS");
        }
        ObjectNode definition = object("definitionKey", payload.getWorkflowCode(),
                "displayName", payload.getDisplayName(), "entryNodeId", plan.getEntryNodeCode(),
                "nodes", nodes, "summaryPrompt", plan.getSummaryPrompt());
        dependencies(payload.getWorkflowCode(), definition);
        return definition;
    }

    static ArrayNode dependencies(String key, JsonNode definition) throws IOException {
        if (!definition.isObject() || !fields(definition, Set.of("definitionKey", "entryNodeId", "nodes"),
                Set.of("definitionKey", "entryNodeId", "nodes", "displayName", "summaryPrompt"))
                || !key.equals(text(definition, "definitionKey")) || !definition.path("nodes").isArray()
                || definition.path("nodes").size() < 2 || definition.path("nodes").size() > 8) {
            throw failure("UNSUPPORTED_WORKFLOW");
        }
        optionalText(definition, "displayName", 200);
        optionalText(definition, "summaryPrompt", 4096);
        Set<String> nodeIds = new HashSet<>();
        TreeSet<String> skillKeys = new TreeSet<>();
        for (JsonNode node : definition.path("nodes")) {
            if (!fields(node, Set.of("nodeId", "skillKey"),
                    Set.of("nodeId", "skillKey", "displayName", "nodePrompt"))) {
                throw failure("UNSUPPORTED_WORKFLOW");
            }
            String id = text(node, "nodeId"), skill = text(node, "skillKey");
            if (definition.has("summaryPrompt") && "workflow-summary".equals(id)) {
                throw failure("INVALID_WORKFLOW_SUMMARY_NODE");
            }
            PublicationMaterial.key("ID", id); PublicationMaterial.key("SKILL", skill);
            if (!nodeIds.add(id)) throw failure("INVALID_WORKFLOW_ENTRY");
            optionalText(node, "displayName", 200); optionalText(node, "nodePrompt", 4096);
            skillKeys.add(skill);
        }
        if (!text(definition, "entryNodeId").equals(definition.path("nodes").get(0).path("nodeId").asText())) {
            throw failure("INVALID_WORKFLOW_ENTRY");
        }
        ArrayNode dependencies = array();
        skillKeys.forEach(skill -> dependencies.add(object("kind", "SKILL", "key", skill)));
        return dependencies;
    }

    private static boolean fields(JsonNode value, Set<String> required, Set<String> allowed) {
        Set<String> actual = new HashSet<>(); value.fieldNames().forEachRemaining(actual::add);
        return value.isObject() && actual.containsAll(required) && allowed.containsAll(actual);
    }

    private static void optionalText(JsonNode value, String field, int limit) throws IOException {
        if ("displayName".equals(field) && value.path(field).isNull()) return;
        if (value.has(field) && (!value.path(field).isTextual() || value.path(field).asText().isBlank()
                || value.path(field).asText().codePointCount(0, value.path(field).asText().length()) > limit)) {
            throw failure("INVALID_WORKFLOW_" + ("displayName".equals(field) ? "DISPLAY_NAME" : "PROMPT"));
        }
    }
}
