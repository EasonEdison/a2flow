package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import java.util.Base64;
import org.springframework.stereotype.Service;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;

/** Direct PostgreSQL material publication, with no subprocess or HTTP bridge. */
@Service
public final class JdbcRuntimeSkillPublicationAdapter implements RuntimeSkillPublicationPort {
    private final RuntimePublicationStore store;
    public JdbcRuntimeSkillPublicationAdapter(RuntimePublicationStore store) { this.store = store; }
    @Override
    public Receipt publish(SkillDraft draft, ReleaseArtifact artifact, byte[] bytes, int version,
            String environment, SkillPublicationInput input) throws IOException {
        String key = draft.getSkillCode();
        var request = PublicationJson.object("key", key, "environment", environment,
                "sourceId", input.sourceId(), "sourceDigest", input.sourceDigest(),
                "snapshot", PublicationJson.parse(input.snapshotJson()), "requestId", input.requestId(),
                "packageDigest", artifact.getPackageDigest(), "packageBase64", Base64.getEncoder().encodeToString(bytes));
        var definition = PublicationMaterial.skill(key, bytes, artifact.getPackageDigest());
        var dependencies = PublicationMaterial.skillDependencies(request.path("snapshot"));
        var names = new java.util.TreeSet<String>();
        dependencies.forEach(dep -> names.add("ABILITY".equals(dep.path("kind").asText()) ? "execute_ability" : "render_application"));
        var hints = PublicationJson.array(); names.forEach(hints::add);
        definition.set("requiredToolNames", hints);
        String versionId = "java-" + PublicationJson.hash(PublicationJson.bytes(
                PublicationJson.array(input.sourceId(), input.sourceDigest(), artifact.getPackageDigest())));
        var receipt = store.publish("SKILL", key, environment, input.requestId(), request,
                versionId, definition, dependencies, store.selection("SKILL", key, environment));
        return new Receipt(key, environment, artifact.getPackageDigest(), versionId,
                receipt.path("contentDigest").asText(), receipt.path("servingDigest").asText(), input.requestId());
    }
}
