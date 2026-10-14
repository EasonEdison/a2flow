package dev.a2flow.management.lifecycle;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.domain.WorkflowCapabilityCandidateView;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowBusinessCapabilityNode;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregate;
import dev.a2flow.management.release.CapabilityReleasePayloadAdapter;
import dev.a2flow.management.release.PublishedAssetQueryService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.PublishedAssetSnapshot;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyType;

/** Published actionCode to management identity resolution; no drafts or cross-environment publication fallback. */
@Service
public class WorkflowCapabilitySelector {
    @Resource private PublishedAssetQueryService published;
    @Resource private CapabilityReleasePayloadAdapter payloads;
    @Resource private AssetAuthorizationService authorization;

    public List<WorkflowCapabilityCandidateView> candidates(String operator, String workflowCode) {
        authorization.requirePermission(operator, ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, AssetAction.VIEW);
        Map<String, Map<ReleaseEnvironment, List<WorkflowCapabilityCandidateView>>> choices = directory(workflowCode);
        List<WorkflowCapabilityCandidateView> result = new ArrayList<>();
        choices.forEach((key, environments) -> {
            for (var entries : environments.values()) requireUnique(entries, workflowCode, "abilityKey");
            var item = environments.containsKey(ReleaseEnvironment.PRT)
                    ? environments.get(ReleaseEnvironment.PRT).get(0) : environments.get(ReleaseEnvironment.ONLINE).get(0);
            result.add(new WorkflowCapabilityCandidateView(key, item.displayName(), item.description(), item.draftId(),
                    environments.keySet().stream().map(Enum::name).sorted().toList()));
        });
        return List.copyOf(result);
    }

    /** Authoring can select an identity present in either environment; publication must resolve the target again. */
    public void validateReferences(String workflowCode, WorkflowGraphAggregate graph) {
        List<WorkflowBusinessCapabilityNode> nodes = graph.getNodes().stream()
                .filter(WorkflowBusinessCapabilityNode.class::isInstance).map(WorkflowBusinessCapabilityNode.class::cast).toList();
        if (nodes.isEmpty()) return;
        var choices = directory(workflowCode);
        for (var node : nodes) {
            String path = "nodes[" + node.getNodeCode() + "].abilityKey";
            var environments = choices.get(node.getAbilityKey());
            if (environments == null || environments.isEmpty()) throw failure("WORKFLOW_CAPABILITY_NOT_PUBLISHED", workflowCode, path);
            for (var entries : environments.values()) requireUnique(entries, workflowCode, path);
        }
    }

    public List<AssetDependencyReference> dependencies(String workflowCode, List<String> abilityKeys, ReleaseEnvironment environment) {
        if (abilityKeys.isEmpty()) return List.of();
        if (environment == null) throw failure("WORKFLOW_CAPABILITY_ENVIRONMENT_REQUIRED", workflowCode, "dependencies");
        var entries = environmentEntries(workflowCode, environment);
        List<AssetDependencyReference> result = new ArrayList<>();
        for (String key : abilityKeys) {
            var selected = entries.get(key);
            requireUnique(selected, workflowCode, "dependencies[abilityKey=" + key + "]");
            result.add(new AssetDependencyReference().setAssetType(AssetDependencyType.CAPABILITY_ACTION)
                    .setAssetKey(selected.get(0).draftId()));
        }
        return result;
    }

    private Map<String, Map<ReleaseEnvironment, List<WorkflowCapabilityCandidateView>>> directory(String workflowCode) {
        Map<String, Map<ReleaseEnvironment, List<WorkflowCapabilityCandidateView>>> result = new TreeMap<>();
        for (ReleaseEnvironment environment : ReleaseEnvironment.values()) {
            environmentEntries(workflowCode, environment).forEach((key, entries) ->
                    result.computeIfAbsent(key, ignored -> new EnumMap<>(ReleaseEnvironment.class)).put(environment, entries));
        }
        return result;
    }

    private Map<String, List<WorkflowCapabilityCandidateView>> environmentEntries(String workflowCode, ReleaseEnvironment environment) {
        Map<String, List<WorkflowCapabilityCandidateView>> result = new TreeMap<>();
        List<PublishedAssetSnapshot> snapshots = published.listPublished(ReleaseAssetType.CAPABILITY_ACTION, environment);
        for (var source : snapshots) {
            var draft = payloads.requireDraft(source.getSnapshot(), source.getAssetKey());
            if (!payloads.isEnabled(source.getSnapshot(), source.getAssetKey())) continue;
            Object raw = draft.getDraft().get("basicInfo");
            if (!(raw instanceof Map<?, ?> info) || !(info.get("actionCode") instanceof String key) || key.isBlank()) {
                throw failure("WORKFLOW_CAPABILITY_SNAPSHOT_INVALID", workflowCode, "abilityKey");
            }
            var item = new WorkflowCapabilityCandidateView(key, text(info.get("nameCn")), text(info.get("description")),
                    source.getAssetKey(), List.of(environment.name()));
            result.computeIfAbsent(key, ignored -> new ArrayList<>()).add(item);
        }
        return result;
    }

    private static void requireUnique(List<?> entries, String workflowCode, String path) {
        if (entries == null || entries.isEmpty()) throw failure("WORKFLOW_CAPABILITY_NOT_PUBLISHED", workflowCode, path);
        if (entries.size() != 1) throw failure("WORKFLOW_CAPABILITY_AMBIGUOUS", workflowCode, path);
    }
    private static String text(Object value) { return value instanceof String text ? text : ""; }
    private static WorkflowControlPlaneException failure(String code, String workflowCode, String path) {
        return new WorkflowControlPlaneException(code, code, workflowCode, path);
    }
}
