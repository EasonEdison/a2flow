package dev.a2flow.management.lifecycle.artifact;

import java.io.IOException;
import java.sql.SQLException;

import org.springframework.stereotype.Service;

import dev.a2flow.management.access.ManagementIdentityProvider;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.storage.db.repository.PostgresArtifactRepository;

/** Database-backed build bytes, scoped by the authenticated management identity. */
@Service
public final class DatabaseArtifactService {
    private final PostgresArtifactRepository repository;
    private final ManagementIdentityProvider identity;

    public DatabaseArtifactService(PostgresArtifactRepository repository, ManagementIdentityProvider identity) {
        this.repository = repository;
        this.identity = identity;
    }

    public ReleaseArtifact save(String assetKey, byte[] content, ReleaseArtifact artifact) throws IOException {
        try {
            String digest = repository.save(identity.namespace(), assetKey, content, artifact.getPackageDigest());
            return artifact.setStorageProvider(PostgresArtifactRepository.PROVIDER)
                    .setObjectKey(digest).setBucket(null).setPackageUrl(null);
        } catch (SQLException failure) {
            throw new IOException("ARTIFACT_DATABASE_WRITE_FAILED", failure);
        }
    }

    public byte[] load(String assetKey, ReleaseArtifact artifact) throws IOException {
        if (artifact == null || !PostgresArtifactRepository.PROVIDER.equals(artifact.getStorageProvider())
                || artifact.getPackageDigest() == null
                || !artifact.getPackageDigest().equals(artifact.getObjectKey())) {
            throw new IOException("ARTIFACT_DATABASE_REFERENCE_REQUIRED");
        }
        try {
            return repository.load(identity.namespace(), assetKey, artifact.getPackageDigest());
        } catch (SQLException failure) {
            throw new IOException("ARTIFACT_DATABASE_READ_FAILED", failure);
        }
    }
}
