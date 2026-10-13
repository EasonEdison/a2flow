package dev.a2flow.management.managementagent;

import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.a2flow.management.lifecycle.CapabilityActionDraftService;

/** Read-only contract discovery, generated from current domain defaults plus the existing graph/binding protocol. */
public final class ManagementAuthoringContracts {
    private final CapabilityActionDraftService capabilities;
    private final ObjectMapper mapper;
    public ManagementAuthoringContracts(CapabilityActionDraftService capabilities, ObjectMapper mapper) { this.capabilities = capabilities; this.mapper = mapper; }
    public ObjectNode describe() {
        ObjectNode result = mapper.createObjectNode();
        result.set("capabilityDraftSkeleton", mapper.valueToTree(capabilities.canonicalizeAuthoringDraft(Map.of())));
        result.put("capabilityInstructions", "Prefer CAPABILITY_DRAFT_CREATE_FROM_REGISTERED to reuse an existing interface: find a source draftId via CAPABILITY_PUBLISHED_LIST, verify its PRT pointer with RELEASE_OVERVIEW, and pass sourceDraftId/actionCode/name/description. The server copies the frozen PRT contract exactly; never transcribe or regenerate descriptorSetBase64. Optional classification must include all businessDomain/capabilityDomain/specialistIds from real config; omit all to inherit the published source classification. CAPABILITY_DRAFT_DETAIL remains available for inspecting actual contracts. Never invent RPC target/profile or claim a new business backend. SKILL_FACTORY_CONFIG supplies real relation IDs. CAPABILITY_VALIDATE persists real revision/errors. Publish via RELEASE_* only.");
        result.put("a2uiInstructions", "A2UI_APPLICATION_BLUEPRINT_LIST gives blueprintCode; A2UI_APPLICATION_BLUEPRINT_IMPORT returns complete validated source without writing. Read A2UI_CATALOG_LIST then A2UI_CATALOG_DETAIL by numeric id for actual component catalog; APPLICATION_DETAIL returns existing source/binding shape. Adapt full source and use APPLICATION_CREATE/UPDATE, then normal release. Blueprint import is not asset creation or publication.");
        result.put("skillInstructions", "WORKSPACE_CREATE creates the normal SKILL.md workspace. Read WORKSPACE_TREE and WORKSPACE_FILE_CONTENT before changing its real entry format. WORKSPACE_FILE_SAVE + WORKSPACE_SAVE retain file guards. After capabilities/components are effective in PRT, read binding candidates then replace both binding arrays with the Skill's current numeric version. RUNTIME_VALIDATE then normal release. For existing published assets first read RELEASE_OVERVIEW and create editable change if no activeChange.");
        ObjectNode bindings = result.putObject("skillBindingContract");
        bindings.put("capabilityBinding", "{draftId:string from candidates,bindMode:EXECUTION_ONLY|EXECUTION_AND_RENDER}");
        bindings.put("componentBinding", "{assetId:number from candidates,componentCode?:string matching registered identity}");
        bindings.put("replace", "{workspaceId:string,version:current Skill version,capabilityBindings:[...],componentBindings:[...]}; arrays replace the whole set, so preserve existing bindings when adding.");
        result.set("workflowDraftSchema", workflowSchema());
        result.put("workflowInstructions", "workflowCode must equal WORKFLOW_CREATE/DETAIL. Use WORKFLOW_SKILL_CANDIDATES; required 2-8 SKILL nodes with real same-specialist Skills effective in PRT, then exactly one SUMMARY nodeCode __summary__. Native runtime has no one-Skill publication path. Nodes form one connected NORMAL edge chain. Summary prompt equals summaryConfig.prompt; allowSkip=false. Do not include quickTriggerMessage, detailSummaryPrompt, handlingSuggestions, router, loop or parallel execution. Preserve all chosen nodePrompt instructions. Save with current expectedDraftRevision and call WORKFLOW_COMPILED_PLAN_PREVIEW before normal release.");
        result.put("publicationInstructions", "Read RELEASE_OVERVIEW currentSnapshot.digest and activeChange. Create change if absent; use its real digest for RELEASE_PREPROD_DEPLOY. Release type/key: SKILL/skillCode, CAPABILITY_ACTION/draftId, COMPONENT/numeric id, A2UI_APPLICATION/appCode, ORCHESTRATION_CONFIG/workflowCode. Then read RELEASE_DEPLOYMENT_DETAIL(operationId) and RELEASE_OVERVIEW environments.PRT; only the actual effective pointer proves availability. Draft creation, compiler validity and tool transport success are not publication. Dependency failures must be fixed by publishing the actual dependency first; no fallback or invented success.");
        return result;
    }
    private ObjectNode workflowSchema() {
        ObjectNode root = object(); var properties = root.withObject("properties");
        properties.set("snapshotContractVersion", mapper.createObjectNode().put("const", 2));
        properties.set("workflowCode", string()); properties.set("metadata", mapper.createObjectNode().put("type", "object"));
        ObjectNode nodes = properties.putObject("nodes").put("type", "array").put("minItems", 3).put("maxItems", 9);
        var alternatives = nodes.putObject("items").putArray("oneOf");
        ObjectNode skill = object(); var fields = skill.withObject("properties");
        fields.set("nodeCode", string()); fields.set("nodeType", mapper.createObjectNode().put("const", "SKILL"));
        fields.set("displayName", string()); fields.set("skillCode", string()); fields.set("nodePrompt", string());
        ObjectNode control = object(); control.withObject("properties").set("allowSkip", mapper.createObjectNode().put("const", false)); required(control, "allowSkip");
        fields.set("controlPolicy", control); required(skill, "nodeCode", "nodeType", "skillCode", "nodePrompt", "controlPolicy"); alternatives.add(skill);
        ObjectNode summary = object(); fields = summary.withObject("properties");
        fields.set("nodeCode", mapper.createObjectNode().put("const", "__summary__")); fields.set("nodeType", mapper.createObjectNode().put("const", "SUMMARY"));
        fields.set("displayName", string()); fields.set("prompt", string()); fields.set("allowSkip", mapper.createObjectNode().put("const", false)); required(summary, "nodeCode", "nodeType", "prompt", "allowSkip"); alternatives.add(summary);
        ObjectNode edge = object(); fields = edge.withObject("properties");
        for (String field : new String[]{"edgeId", "sourceNodeCode", "targetNodeCode"}) fields.set(field, string());
        fields.set("edgeType", mapper.createObjectNode().put("const", "NORMAL")); required(edge, "edgeId", "sourceNodeCode", "targetNodeCode", "edgeType");
        properties.putObject("edges").put("type", "array").set("items", edge);
        ObjectNode summaryConfig = object(); summaryConfig.withObject("properties").set("prompt", string()); required(summaryConfig, "prompt");
        properties.set("summaryConfig", summaryConfig); required(root, "snapshotContractVersion", "workflowCode", "metadata", "nodes", "edges", "summaryConfig");
        return root;
    }
    private ObjectNode object() { ObjectNode value = mapper.createObjectNode().put("type", "object").put("additionalProperties", false); value.putObject("properties"); return value; }
    private ObjectNode string() { return mapper.createObjectNode().put("type", "string").put("minLength", 1); }
    private void required(ObjectNode value, String... names) { var required = value.putArray("required"); for (String name : names) required.add(name); }
}
