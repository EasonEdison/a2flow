package dev.a2flow.management.managementagent;

import java.util.Map;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

/** Browser-safe factual projection. No schemas, business arguments, credentials or arbitrary URLs. */
public final class ManagementAssetProjection {
    private ManagementAssetProjection() { }
    public static ArrayNode assets(ObjectMapper mapper, String method, Map<String, String> params, JsonNode data) {
        ArrayNode assets = mapper.createArrayNode();
        if (data == null || !data.isObject()) return assets;
        ObjectNode asset = mapper.createObjectNode();
        ObjectNode detail = asset.putObject("detail");
        if (method.startsWith("RELEASE_")) {
            asset.put("assetType", params.get("assetType")).put("assetKey", params.get("assetKey"));
            switch (params.get("assetType")) {
                case "SKILL" -> detail.put("skillCode", params.get("assetKey"));
                case "CAPABILITY_ACTION" -> detail.put("draftId", params.get("assetKey"));
                case "COMPONENT" -> detail.put("id", params.get("assetKey"));
                case "ORCHESTRATION_CONFIG" -> detail.put("workflowCode", params.get("assetKey"));
                default -> { }
            }
            JsonNode pointer = method.equals("RELEASE_OVERVIEW") ? data.path("environments").path("PRT") : null;
            if (pointer != null && pointer.isObject() && !pointer.path("sourceId").asText().isBlank()) {
                ObjectNode publication = asset.putObject("publication").put("environment", "PRT").put("status", "EFFECTIVE");
                copy(publication, pointer, "version", "sourceId", "deploymentId", "digest");
            } else if (method.equals("RELEASE_DEPLOYMENT_DETAIL") && data.path("environment").asText().equals("PRT")) {
                ObjectNode publication = asset.putObject("publication").put("environment", "PRT");
                copy(publication, data, "status", "sourceId", "deploymentId");
                if (data.hasNonNull("sourceVersion")) publication.put("version", data.path("sourceVersion").asText());
            }
        } else if (method.startsWith("WORKFLOW_") && data.hasNonNull("workflowCode")) {
            asset.put("assetType", "ORCHESTRATION_CONFIG").put("assetKey", data.path("workflowCode").asText());
            detail.put("workflowCode", data.path("workflowCode").asText()); copyName(asset, data, "displayName");
        } else if (method.startsWith("CAPABILITY_") && data.hasNonNull("draftId")) {
            asset.put("assetType", "CAPABILITY_ACTION").put("assetKey", data.path("draftId").asText());
            detail.put("draftId", data.path("draftId").asText()); copyName(asset, data.path("draft").path("basicInfo"), "nameCn");
        } else if (method.startsWith("A2UI_APPLICATION_") && data.hasNonNull("appCode") && data.hasNonNull("id")) {
            asset.put("assetType", "A2UI_APPLICATION").put("assetKey", data.path("appCode").asText());
            detail.put("id", data.path("id").asText()); copyName(asset, data, "nameCn");
        } else if ((method.startsWith("SKILL_") || method.startsWith("WORKSPACE_")) && data.hasNonNull("skillCode")) {
            asset.put("assetType", "SKILL").put("assetKey", data.path("skillCode").asText());
            detail.put("skillCode", data.path("skillCode").asText()); copyName(asset, data, "skillNameCn");
        } else if (method.startsWith("COMPONENT_") && data.hasNonNull("id")) {
            asset.put("assetType", "COMPONENT").put("assetKey", data.path("id").asText());
            detail.put("id", data.path("id").asText()); copyName(asset, data, "componentNameCn");
        }
        if (asset.hasNonNull("assetKey") && !asset.path("assetKey").asText().isBlank()) assets.add(asset);
        return assets;
    }
    private static void copy(ObjectNode target, JsonNode source, String... fields) {
        for (String field : fields) if (source.hasNonNull(field) && source.path(field).isValueNode()) target.put(field, source.path(field).asText());
    }
    private static void copyName(ObjectNode target, JsonNode source, String field) {
        if (source.path(field).isTextual()) target.put("displayName", source.path(field).asText());
    }
}
