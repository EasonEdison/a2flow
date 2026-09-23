package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;

import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;

/**
 * Publishes the validated Skill definition and frozen dependencies into the selected runtime DB.
 * Implementations must enforce environment isolation and idempotency. An artifact save alone
 * cannot produce a receipt. Deliberately has no no-op/default implementation.
 */
public interface RuntimeSkillPublicationPort {
    record Receipt(String assetKey, String environment, String packageDigest, String versionId,
            String contentDigest, String servingDigest, String requestId) { }

    Receipt publish(SkillDraft draft, ReleaseArtifact artifact, byte[] packageBytes, int version,
            String environment, SkillPublicationInput input) throws IOException;
}
