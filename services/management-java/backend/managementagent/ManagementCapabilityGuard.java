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
