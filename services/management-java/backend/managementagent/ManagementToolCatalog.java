package dev.a2flow.management.managementagent;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.google.protobuf.ByteString;
import dev.a2flow.management.managementagent.proto.ManagementTool;

/** Explicit authoring surface. No business mutations, online, owner replacement, deletion or legacy coding tools. */
public final class ManagementToolCatalog {
    private final ObjectMapper mapper;
    private final Map<String, Definition> definitions = new LinkedHashMap<>();
    public ManagementToolCatalog(ObjectMapper mapper) {
        this.mapper = mapper;
        add("AUTHORING_CONTRACT", false, "Read exact canonical capability defaults, full supported workflow JSONSchema, Skill binding protocol and publication sequence before creating assets from scratch. A2UI full sources are available from read-only BLUEPRINT_IMPORT.", "", "");
        add("SKILL_FACTORY_CONFIG", false, "Read real domain, specialist and authoring configuration before choosing classification IDs.", "", "");
        add("SKILL_LIST", false, "Find existing Skills before creating or updating.", "", "keyword,businessDomain,capabilityDomain,specialistId,page,pageSize");
        add("SKILL_DETAIL", false, "Read Skill metadata, draft, bindings and actual permissions.", "skillCode", "");
        add("WORKSPACE_CREATE", true, "Create a Skill database workspace. skillCode must match the existing Runtime key contract: lowercase letters/digits/hyphens, optional slash-separated namespaces, at most 128 characters (example demo-people-browser). No uppercase, underscore or dot; never normalize or rename an existing code implicitly. Choose an unused skillCode; classify only with existing configuration IDs.", "skillCode,skillNameCn,skillDescription", "businessDomain,capabilityDomain,specialistIds,version");
        add("SKILL_UPDATE", true, "Update existing Skill metadata and relation-backed classification.", "skillCode,skillNameCn", "skillDescription,businessDomain,capabilityDomain,specialistIds");
        add("WORKSPACE_TREE", false, "Read Skill workspace file tree.", "workspaceId", "");
        add("WORKSPACE_FILE_CONTENT", false, "Read an existing workspace file before editing; filePath must be a relative path returned by WORKSPACE_TREE, such as SKILL.md. Never pass /large_tool_results or other agent-local/offload paths.", "workspaceId,filePath", "");
        add("WORKSPACE_FILE_SAVE", true, "Save a workspace file through existing file guards. SKILL.md is the Skill entry; do not invent unsupported business tools.", "workspaceId,filePath,content", "");
        add("WORKSPACE_SAVE", true, "Persist current workspace draft through the normal save flow.", "workspaceId", "");
        add("WORKSPACE_DIFF", false, "Read workspace diff.", "workspaceId", "");
        add("SKILL_COMPONENT_CANDIDATE_LIST", false, "Read registered A2UI dependencies available for Skill binding.", "", "workspaceId,keyword");
        add("SKILL_CAPABILITY_CANDIDATE_LIST", false, "Read existing capabilities available for Skill binding; never invent endpoints.", "", "workspaceId,keyword");
        add("SKILL_BINDINGS_REPLACE", true, "Replace Skill bindings using current candidate identifiers and existing binding contract. Use EXECUTION_ONLY if the capability resultContract has no presentationComponents; EXECUTION_AND_RENDER requires actual published presentation components on every supported client. Bind an independent A2UI application separately in componentBindings, not by changing the capability bindMode.", "workspaceId,version,capabilityBindings,componentBindings", "skillCode");
        add("RUNTIME_VALIDATE", true, "Optional legacy workbench output-sample preview, not the native Skill publication gate. PASSED/FAILED/PARTIAL describe this preview only; no samples yields FAILED. Do not invent samples to satisfy it.", "workspaceId", "");
        add("CAPABILITY_LIST", false, "Find current capability drafts.", "", "keyword,page,pageSize,businessDomain,capabilityDomain,specialistId");
        add("CAPABILITY_PUBLISHED_LIST", false, "Read existing published capability contracts and dependencies.", "", "keyword");
        add("CAPABILITY_DRAFT_DETAIL", false, "Read full canonical capability draft and current revision.", "draftId", "");
        add("CAPABILITY_DRAFT_CREATE_FROM_REGISTERED", true, "Preferred way to create a new capability for an existing registered interface: sourceDraftId must identify a capability currently published in PRT. Server copies its immutable complete contract and binary gRPC descriptor exactly, overriding only actionCode/name/description. actionCode needs at least 3 dot-separated alphanumeric segments, each starting with a letter; hyphens and underscores are forbidden (for example demo.people.list). Do NOT copy or regenerate descriptorSetBase64. Classification defaults to source; to change it provide all businessDomain, capabilityDomain, specialistIds from real config. Then CAPABILITY_VALIDATE and normal RELEASE_* publication; creation alone is not publication.", "sourceDraftId,actionCode,name,description", "businessDomain,capabilityDomain,specialistIds");
        add("CAPABILITY_DRAFT_UPDATE_METADATA", true, "Update an EXISTING capability using draftId and current baseRevision from CAPABILITY_DRAFT_DETAIL. Provide at least one of actionCode/name/description; all other configuration and binary gRPC descriptor are preserved server-side. actionCode requires at least 3 dot-separated alphanumeric segments, each starting with a letter, no hyphens or underscores. Use this to fix metadata validation errors on an already-created asset; do not delete/recreate it. Existing permission, editable-change and revision guards apply; validate and publish normally afterwards.", "draftId,baseRevision", "actionCode,name,description");
        add("CAPABILITY_DRY_RUN_READ_ONLY", true, "Required real PRT verification before capability publication. Read current draft revision and supportedClients, then invoke once per supported client. Server permits only READ capabilities matching an existing registered PRT interface. Calls the normal dry-run with the saved inputExampleJson, trusted identity and fixed PRT; persists real digest-bound validation evidence. This tool never accepts arbitrary arguments, credentials or environment. A failed toolResult is a failed verification, not publication; read RELEASE_OVERVIEW evidence before deploying. Do not blindly retry UNKNOWN.", "draftId,revision,clientType", "");
        add("CAPABILITY_VALIDATE", true, "Run and persist the real capability static validation; valid=false is not success. Publication uses RELEASE_* not legacy CAPABILITY_PUBLISH.", "draftId", "");
        add("COMPONENT_LIST", false, "Read current registered component assets.", "", "keyword,page,pageSize");
        add("COMPONENT_DETAIL", false, "Read component source and configuration.", "id", "");
        add("COMPONENT_REGISTER", true, "Create an A2UI component registration through normal component validation.", "assetType,componentName,componentNameCn", "dslType,agentUiDsl,protocolVersion,interactionMode,bundleUrl,appBundleUrl,scene,paramsSchemaJson,renderTemplateJson,officialDemoJson,messageDemoJson,integrationPrompt,allowedActionsJson,runtimeConfigJson,attribute,supportClients,enabled");
        add("COMPONENT_UPDATE", true, "Update an existing component using its actual editable contract from COMPONENT_DETAIL.", "id", "componentNameCn,interactionMode,bundleUrl,appBundleUrl,scene,paramsSchemaJson,renderTemplateJson,officialDemoJson,messageDemoJson,integrationPrompt,allowedActionsJson,runtimeConfigJson,attribute,supportClients,enabled");
        add("A2UI_CATALOG_LIST", false, "Read registered official/managed catalogs and protocol contract.", "", "");
        add("A2UI_CATALOG_DETAIL", false, "Read catalog contract before generating A2UI; use its actual catalogId and component properties.", "id", "");
        add("A2UI_CATALOG_COMPONENT_LIST", false, "Read supported component definitions.", "", "catalogId");
        add("A2UI_CATALOG_COMPONENT_DETAIL", false, "Read a registered component definition.", "id", "");
        add("A2UI_APPLICATION_LIST", false, "Read application drafts and published projections.", "", "keyword,page,pageSize,status");
        add("A2UI_APPLICATION_DETAIL", false, "Read an application's exact source, bindings and release state.", "id", "");
        add("A2UI_APPLICATION_BLUEPRINT_IMPORT", false, "Read a complete validated blueprint source as a deep copy ONLY. Does not create or publish an asset. Get blueprintCode from BLUEPRINT_LIST, change appCode/name and adapt fields/actions to requirements before APPLICATION_CREATE.", "blueprintCode", "");
        add("A2UI_APPLICATION_BLUEPRINT_LIST", false, "Read supported A2UI source shapes and templates; adapt actual requirements, do not claim template import is publication.", "", "");
        add("A2UI_APPLICATION_CREATE", true, "Create validated A2UI application source using the registered catalog, data and action contracts.", "applicationJson", "");
        add("A2UI_APPLICATION_UPDATE", true, "Update validated A2UI application source; preserve declared action/binding contracts.", "id,applicationJson", "");
        add("A2UI_APPLICATION_ACTION_SCAN", false, "Validate and inspect application action references without executing any business action.", "applicationJson", "");
        add("WORKFLOW_LIST", false, "Find current workflows; nextPageToken pagination.", "", "specialistCode,pageToken,limit");
        add("WORKFLOW_DETAIL", false, "Read workflow identity, revision and metadata.", "workflowCode", "");
        add("WORKFLOW_CREATE", true, "Create a workflow draft with an actual registered specialistCode.", "displayName,description,specialistCode", "");
        add("WORKFLOW_BASIC_INFO_UPDATE", true, "Update workflow name and description.", "workflowCode", "displayName,description");
        add("WORKFLOW_DRAFT_DETAIL", false, "Read authoritative graph draft and revision before edits.", "workflowCode", "");
        add("WORKFLOW_CAPABILITY_CANDIDATES", false, "Read published fixed business capability identities for this workflow; environments reports availability, not a fallback. Store only abilityKey plus optional nodePrompt, never schema copies or input mappings. Publication rechecks the exact target environment.", "workflowCode", "");
        add("WORKFLOW_SKILL_CANDIDATES", false, "Read the existing same-specialist Skills available for workflow nodes.", "workflowCode", "");
        add("WORKFLOW_DRAFT_UPDATE", true, "Save exact graph draft with expectedDraftRevision. Native publication requires 1-8 linear SKILL and/or BUSINESS_CAPABILITY nodes plus exactly one SUMMARY; capability nodes use fixed abilityKey and optional nodePrompt, never parameters or mappings. Preserve Skill nodePrompt/summaryConfig semantics.", "workflowCode,draftPayloadJson,expectedDraftRevision", "");
        add("WORKFLOW_COMPILED_PLAN_PREVIEW", false, "Run the real workflow compiler and dependency checks; resolve errors before release.", "workflowCode", "draftPayloadJson");
        add("RELEASE_OVERVIEW", false, "Read actual currentSnapshot.digest, change, builds, versions, dependencies and PRT pointer. Use returned IDs/digest, never invent them.", "assetType,assetKey", "");
        add("RELEASE_CHANGE_CREATE", true, "First read RELEASE_OVERVIEW activeChange and allowedActions. Reuse an existing ACTIVE change; do not create another. Create only when allowedActions includes CREATE_CHANGE. To deploy the current draft, use its currentSnapshot.digest with RELEASE_PREPROD_DEPLOY when DEPLOY_PREPROD is allowed. Supported types SKILL, CAPABILITY_ACTION, COMPONENT, A2UI_APPLICATION, ORCHESTRATION_CONFIG; use actual asset identity.", "assetType,assetKey,changeName", "");
        add("RELEASE_DIFF", false, "Read the actual immutable release diff and content digest.", "assetType,assetKey", "baseVersion,version,entryPath,viewMode,contextLines");
        add("RELEASE_PREPROD_DEPLOY", true, "Compile, validate dependencies and publish through the normal PRT release path. expectedDigest must be read from RELEASE_OVERVIEW. Afterwards read deployment detail AND overview to verify PRT pointer/version. Do not use ONLINE or claim business execution.", "assetType,assetKey,expectedDigest", "");
        add("RELEASE_DEPLOYMENT_DETAIL", false, "Read actual deployment result/evidence, then overview for the effective PRT pointer.", "assetType,assetKey,deploymentId", "");
    }
    private void add(String name, boolean mutating, String description, String required, String optional) {
        ObjectNode schema = mapper.createObjectNode().put("type", "object").put("additionalProperties", false);
        ObjectNode properties = schema.putObject("properties");
        var requiredNode = schema.putArray("required");
        for (String field : (required + "," + optional).split(",")) {
            if (field.isBlank()) continue;
            var property = properties.putObject(field);
            if (Set.of("draftJson", "applicationJson", "draftPayloadJson").contains(field)) property.putArray("type").add("object").add("string");
            else if (field.endsWith("Json") || Set.of("capabilityBindings", "componentBindings", "supportClients", "attribute").contains(field)) property.putArray("type").add("object").add("array").add("string");
            else if (Set.of("protocolVersion", "revision", "baseRevision", "expectedDraftRevision", "page", "pageSize", "limit", "contextLines", "version", "baseVersion").contains(field)) property.putArray("type").add("integer").add("string");
            else if (field.equals("enabled")) property.putArray("type").add("boolean").add("string");
            else property.put("type", "string");
            if (name.equals("CAPABILITY_DRY_RUN_READ_ONLY") && field.equals("clientType")) {
                property.putArray("enum").add("PC").add("APP").add("COMMON");
            }
            if (name.equals("WORKSPACE_CREATE") && field.equals("skillCode")) {
                property.put("pattern", "^" + dev.a2flow.management.lifecycle.SkillKeyValidator.PATTERN + "$").put("maxLength", 128);
            }
            if (field.equals("actionCode")) property.put("pattern", ManagementCapabilityGuard.ACTION_CODE_PATTERN);
            if (Set.of("CAPABILITY_DRAFT_CREATE_FROM_REGISTERED", "CAPABILITY_DRAFT_UPDATE_METADATA").contains(name)
                    && Set.of("sourceDraftId", "draftId", "name", "description").contains(field)) property.put("minLength", 1);
        }
        for (String field : required.split(",")) if (!field.isBlank()) requiredNode.add(field);
        if (name.equals("CAPABILITY_DRAFT_UPDATE_METADATA")) {
            var alternatives = schema.putArray("anyOf");
            for (String field : List.of("actionCode", "name", "description")) alternatives.addObject().putArray("required").add(field);
        }
        definitions.put(name, new Definition(name, mutating, description, schema));
    }
    public List<ManagementTool> tools() {
        return definitions.values().stream().map(value -> ManagementTool.newBuilder().setName(value.name())
                .setMutating(value.mutating()).setDescription(value.description())
                .setInputSchemaJson(ByteString.copyFromUtf8(value.schema().toString())).build()).toList();
    }
    public Definition require(String name, JsonNode arguments) {
        Definition definition = definitions.get(name);
        if (definition == null) throw new IllegalArgumentException("MANAGEMENT_TOOL_NOT_ALLOWED");
        if (arguments == null || !arguments.isObject()) throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENTS_INVALID");
        arguments.fieldNames().forEachRemaining(field -> {
            if (!definition.schema().path("properties").has(field)) throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENT_NOT_ALLOWED");
            JsonNode value = arguments.get(field);
            JsonNode types = definition.schema().path("properties").path(field).path("type");
            boolean accepted = false;
            for (JsonNode type : types.isArray() ? types : mapper.createArrayNode().add(types)) {
                accepted |= switch (type.asText()) {
                    case "string" -> value.isTextual(); case "integer" -> value.isIntegralNumber();
                    case "object" -> value.isObject(); case "array" -> value.isArray(); case "boolean" -> value.isBoolean();
                    default -> false;
                };
            }
            if (!accepted) throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENT_TYPE_INVALID");
            JsonNode property = definition.schema().path("properties").path(field);
            if (property.has("enum")) {
                boolean matches = false;
                for (JsonNode allowed : property.path("enum")) matches |= allowed.equals(value);
                if (!matches) throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENT_VALUE_INVALID");
            }
            if (value.isTextual() && property.has("pattern") && !value.asText().matches(property.path("pattern").asText())) {
                throw new IllegalArgumentException(field.equals("skillCode") ? "INVALID_ASSET_KEY" : "MANAGEMENT_CAPABILITY_ACTION_CODE_INVALID");
            }
            if (value.isTextual() && property.has("maxLength") && value.asText().length() > property.path("maxLength").asInt()) {
                throw new IllegalArgumentException("INVALID_ASSET_KEY");
            }
            if (value.isTextual() && property.has("minLength") && value.asText().isBlank()) {
                throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENT_REQUIRED");
            }
        });
        for (JsonNode field : definition.schema().path("required")) {
            if (!arguments.has(field.asText())) throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENT_REQUIRED");
        }
        if (name.equals("RELEASE_PREPROD_DEPLOY") && arguments.path("assetType").asText().equals("SKILL")
                && !dev.a2flow.management.lifecycle.SkillKeyValidator.isValid(arguments.path("assetKey").asText())) {
            throw new IllegalArgumentException("INVALID_ASSET_KEY");
        }
        if (name.equals("CAPABILITY_DRAFT_UPDATE_METADATA")
                && !arguments.has("actionCode") && !arguments.has("name") && !arguments.has("description")) {
            throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_METADATA_REQUIRED");
        }
        return definition;
    }
    public record Definition(String name, boolean mutating, String description, ObjectNode schema) { }
}
