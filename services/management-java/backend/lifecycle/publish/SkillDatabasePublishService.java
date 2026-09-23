package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import java.util.Objects;

import org.springframework.stereotype.Service;

import dev.a2flow.management.lifecycle.artifact.DatabaseArtifactService;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleaseDeployment;

/** Publishes only after a runtime database adapter returns a verified receipt. */
@Service
public final class SkillDatabasePublishService {
    public static final String ENV_PRT = "PRT";
    public static final String ENV_PROD = "ONLINE";
    private final DatabaseArtifactService artifacts;
    private final RuntimeSkillPublicationPort runtime;

    public SkillDatabasePublishService(DatabaseArtifactService artifacts, RuntimeSkillPublicationPort runtime) {
        this.artifacts = artifacts;
        this.runtime = runtime;
    }

    public SkillDatabasePublishResult publish(SkillDraft draft, String description, ReleaseArtifact artifact,
            int version, String environment, String operator, String requestId,
            ReleaseDeployment previousDeployment, SkillPublicationInput input) throws IOException {
        if (draft == null || version <= 0 || requestId == null || requestId.isBlank()
                || !(ENV_PRT.equals(environment) || ENV_PROD.equals(environment))) {
            throw new IllegalArgumentException("SKILL_PUBLICATION_IDENTITY_INVALID");
        }
        if (input == null || !requestId.equals(input.requestId())) {
            throw new IllegalArgumentException("IMMUTABLE_SKILL_PUBLICATION_INPUT_REQUIRED");
        }
        byte[] bytes = artifacts.load(draft.getWorkspaceId(), artifact);
        RuntimeSkillPublicationPort.Receipt receipt = runtime.publish(
                draft, artifact, bytes, version, environment, input);
        if (receipt == null || !Objects.equals(draft.getSkillCode(), receipt.assetKey())
                || !environment.equals(receipt.environment())
                || !artifact.getPackageDigest().equals(receipt.packageDigest())
                || receipt.versionId() == null || receipt.versionId().isBlank()
                || !requestId.equals(receipt.requestId()) || receipt.servingDigest() == null
                || !receipt.servingDigest().matches("sha256:[0-9a-f]{64}") || receipt.contentDigest() == null
                || !receipt.contentDigest().matches("sha256:[0-9a-f]{64}")) {
            throw new IOException("SKILL_PUBLICATION_RECEIPT_INVALID");
        }
        return new SkillDatabasePublishResult(true, "SUCCEEDED", "PUBLISHED", environment,
                receipt.versionId(), receipt.contentDigest(), artifact);
    }
}
