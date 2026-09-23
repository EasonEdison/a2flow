package dev.a2flow.management.lifecycle.publish;

/** Immutable release facts supplied by the shared release control plane, not browser parameters. */
public record SkillPublicationInput(String sourceId, String sourceDigest, String snapshotJson, String requestId) {
    public SkillPublicationInput {
        if (sourceId == null || sourceId.isBlank() || sourceDigest == null || sourceDigest.isBlank()
                || snapshotJson == null || snapshotJson.isBlank() || requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("IMMUTABLE_SKILL_PUBLICATION_INPUT_REQUIRED");
        }
    }
}
