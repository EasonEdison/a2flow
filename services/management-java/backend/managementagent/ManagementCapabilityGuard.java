package dev.a2flow.management.managementagent;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.a2flow.management.capabilityrpc.GrpcCapabilityContract;
import dev.a2flow.management.lifecycle.CapabilityActionDraftService;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.release.PublishedAssetQueryService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;

/** Agent authoring reuses a real PRT business interface; it cannot register a new target or change execution semantics. */
public final class ManagementCapabilityGuard {
    static final String ACTION_CODE_PATTERN = "^[A-Za-z][A-Za-z0-9]*(?:\\.[A-Za-z][A-Za-z0-9]*){2,}$";
    private final CapabilityActionDraftService drafts;
    private final PublishedAssetQueryService published;
    private final ObjectMapper mapper;
    private final dev.a2flow.management.capabilityrpc.GrpcTargetRegistry targets;
    public ManagementCapabilityGuard(CapabilityActionDraftService drafts, PublishedAssetQueryService published, ObjectMapper mapper, dev.a2flow.management.capabilityrpc.GrpcTargetRegistry targets) {
        this.drafts = drafts; this.published = published; this.mapper = mapper; this.targets = targets;
    }
    public void check(String method, JsonNode arguments) {
        JsonNode candidate;
        try {
            if (method.equals("CAPABILITY_DRAFT_CREATE") || method.equals("CAPABILITY_DRAFT_SAVE")) {
                JsonNode value = arguments.path("draftJson");
                if (value.isTextual()) value = mapper.readTree(value.asText());
                if (value == null || !value.isObject()) throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_CONTRACT_INVALID");
                candidate = mapper.valueToTree(drafts.canonicalizeAuthoringDraft(mapper.convertValue(value,
                        new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() { })));
            } else if (method.equals("CAPABILITY_DRY_RUN")) {
                CapabilityActionDraft current = drafts.detail(requiredText(arguments, "draftId"));
                int revision;
                try { revision = Integer.parseInt(arguments.path("revision").asText()); }
                catch (NumberFormatException error) { throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_REVISION_INVALID"); }
                if (revision <= 0 || !java.util.Objects.equals(current.getRevision(), revision)) {
                    throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_REVISION_CHANGED");
                }
                candidate = mapper.valueToTree(current.getDraft());
                requireReadOnly(candidate);
            } else if (method.equals("RELEASE_PREPROD_DEPLOY") && arguments.path("assetType").asText().equals("CAPABILITY_ACTION")) {
                candidate = mapper.valueToTree(drafts.detail(arguments.path("assetKey").asText()).getDraft());
            } else return;
            List<Contract> registered = new ArrayList<>();
            for (var source : published.listPublished(ReleaseAssetType.CAPABILITY_ACTION, ReleaseEnvironment.PRT)) {
                CapabilityActionDraft frozen = mapper.readValue(source.getSnapshot().getPayloadJson(), CapabilityActionDraft.class);
                registered.addAll(contracts(mapper.valueToTree(frozen.getDraft())));
            }
            List<Contract> requested = contracts(candidate);
            for (Contract contract : requested) {
                if (!targets.isRegistered(contract.executionBinding().path("target").path("targetKey").asText(), ReleaseEnvironment.PRT)) {
                    throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_TARGET_NOT_REGISTERED");
                }
            }
            if (requested.isEmpty() || !registered.containsAll(requested)) throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_INTERFACE_NOT_REGISTERED");
        } catch (java.io.IOException error) { throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_CONTRACT_INVALID"); }
    }
    static void requireReadOnly(JsonNode candidate) {
        if (!candidate.path("governance").path("sideEffectLevel").asText().equals("READ")) {
            throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_READ_ONLY_REQUIRED");
        }
    }
    /** Copy the immutable PRT interface server-side; model arguments never carry binary descriptors. */
    public JsonNode registeredCreateArguments(JsonNode arguments) {
        String sourceId = requiredText(arguments, "sourceDraftId");
        String actionCode = requiredActionCode(arguments);
        String name = requiredText(arguments, "name");
        String description = requiredText(arguments, "description");
        try {
            var source = published.requirePublished(ReleaseAssetType.CAPABILITY_ACTION, sourceId, ReleaseEnvironment.PRT);
            CapabilityActionDraft frozen = mapper.readValue(source.getSnapshot().getPayloadJson(), CapabilityActionDraft.class);
            var draft = mapper.valueToTree(frozen.getDraft());
            if (!draft.isObject() || !draft.path("basicInfo").isObject()) {
                throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_CONTRACT_INVALID");
            }
            var basicInfo = (com.fasterxml.jackson.databind.node.ObjectNode) draft.path("basicInfo");
            basicInfo.put("actionCode", actionCode).put("nameCn", name).put("description", description);
            ((com.fasterxml.jackson.databind.node.ObjectNode) draft).put("mode", "CREATE");
            var result = mapper.createObjectNode();
            result.set("draftJson", draft);
            boolean explicitClassification = arguments.has("businessDomain") || arguments.has("capabilityDomain")
                    || arguments.has("specialistIds");
            if (explicitClassification) {
                for (String field : List.of("businessDomain", "capabilityDomain", "specialistIds")) {
                    result.put(field, requiredText(arguments, field));
                }
            } else {
                // The regular Create path requires full classification to retain a complete authoring draft.
                copyClassification(result, frozen);
            }
            return result;
        } catch (java.io.IOException error) {
            throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_CONTRACT_INVALID");
        }
    }
    /** Edit only requested metadata while keeping the current draft contract and classification intact. */
    public JsonNode metadataUpdateArguments(JsonNode arguments) {
        if (!arguments.has("actionCode") && !arguments.has("name") && !arguments.has("description")) {
            throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_METADATA_REQUIRED");
        }
        String actionCode = arguments.has("actionCode") ? requiredActionCode(arguments) : null;
        String name = arguments.has("name") ? requiredText(arguments, "name") : null;
        String description = arguments.has("description") ? requiredText(arguments, "description") : null;
        String draftId = requiredText(arguments, "draftId");
        CapabilityActionDraft current = drafts.detail(draftId);
        var draft = mapper.valueToTree(current.getDraft());
        if (!draft.isObject() || !draft.path("basicInfo").isObject()) {
            throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_CONTRACT_INVALID");
        }
        var basicInfo = (com.fasterxml.jackson.databind.node.ObjectNode) draft.path("basicInfo");
        if (actionCode != null) basicInfo.put("actionCode", actionCode);
        if (name != null) basicInfo.put("nameCn", name);
        if (description != null) basicInfo.put("description", description);
        var result = mapper.createObjectNode().put("draftId", draftId);
        result.set("baseRevision", arguments.get("baseRevision"));
        result.set("draftJson", draft);
        copyClassification(result, current);
        return result;
    }
    private static String requiredActionCode(JsonNode arguments) {
        String actionCode = requiredText(arguments, "actionCode");
        if (!actionCode.matches(ACTION_CODE_PATTERN)) {
            throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_ACTION_CODE_INVALID");
        }
        return actionCode;
    }
    private static void copyClassification(com.fasterxml.jackson.databind.node.ObjectNode result, CapabilityActionDraft source) {
        if (source.getBusinessDomain() == null || source.getBusinessDomain().isBlank()
                || source.getCapabilityDomain() == null || source.getCapabilityDomain().isBlank()
                || source.getSpecialistId() == null || source.getSpecialistId().isBlank()) {
            throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_CLASSIFICATION_REQUIRED");
        }
        result.put("businessDomain", source.getBusinessDomain());
        result.put("capabilityDomain", source.getCapabilityDomain());
        result.put("specialistIds", source.getSpecialistId());
    }
    private static String requiredText(JsonNode arguments, String field) {
        JsonNode value = arguments.path(field);
        if (!value.isTextual() || value.asText().isBlank()) {
            throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENT_REQUIRED");
        }
        return value.asText();
    }
    private List<Contract> contracts(JsonNode draft) {
        List<Contract> result = new ArrayList<>();
        JsonNode variants = draft.path("clientVariants");
        if (!variants.isObject()) throw new IllegalArgumentException("MANAGEMENT_CAPABILITY_CONTRACT_INVALID");
        String sideEffect = draft.path("governance").path("sideEffectLevel").asText();
        for (JsonNode variant : variants) {
            JsonNode binding = variant.path("executionBinding");
            GrpcCapabilityContract.validateBinding(mapper.convertValue(binding, new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() { }));
            result.add(new Contract(binding, sideEffect));
        }
        return result;
    }
    private record Contract(JsonNode executionBinding, String sideEffectLevel) { }
}
