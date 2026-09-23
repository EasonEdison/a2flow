package dev.a2flow.management.lifecycle.publish;

import java.util.LinkedHashMap;
import java.util.Map;

import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;

/** A runtime database publication receipt, not an upload/install result. */
public record SkillDatabasePublishResult(boolean success, String publishStatus, String publishStage,
        String environment, String versionId, String contentDigest, ReleaseArtifact artifact) {
    public boolean isSuccess() { return success; }
    public ReleaseArtifact getArtifact() { return artifact; }
    public String getPublishStage() { return publishStage; }

    public Map<String, Object> toMap() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("publishStatus", publishStatus);
        result.put("externalPublishStage", publishStage);
        result.put("environment", environment);
        result.put("versionId", versionId);
        result.put("contentDigest", contentDigest);
        result.put("artifact", artifact);
        result.put("retryable", false);
        return result;
    }
}
