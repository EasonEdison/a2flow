package dev.a2flow.management.storage.db.repository;

import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;

import javax.sql.DataSource;

/**
 * Immutable build artifacts in the existing version table. These records are not runtime assets
 * and never create serving pointers. Publication must separately validate and publish a runtime
 * definition; saving a package is not successful deployment.
 */
public final class PostgresArtifactRepository {
    public static final String PROVIDER = "POSTGRESQL";
    private static final String KIND = "BUILD_ARTIFACT";
    private static final int MAX_BYTES = 100 * 1024 * 1024;
    private final DataSource dataSource;

    public PostgresArtifactRepository(DataSource dataSource) {
        this.dataSource = java.util.Objects.requireNonNull(dataSource);
    }

    public String save(String namespace, String assetKey, byte[] content, String expectedDigest)
            throws SQLException, IOException {
        requireIdentity(namespace, assetKey);
        verify(content, expectedDigest);
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO a2flow_asset_versions "
                        + "(namespace,kind,asset_key,version_id,document,digest) VALUES (?,?,?,?,?,?) "
                        + "ON CONFLICT (namespace,kind,asset_key,version_id) DO NOTHING")) {
                    bindIdentity(statement, namespace, assetKey, expectedDigest);
                    statement.setBytes(5, content);
                    statement.setString(6, expectedDigest);
                    statement.executeUpdate();
                }
                byte[] saved = load(connection, namespace, assetKey, expectedDigest);
                if (!Arrays.equals(content, saved)) {
                    throw new IOException("ARTIFACT_IMMUTABILITY_CONFLICT");
                }
                connection.commit();
                return expectedDigest;
            } catch (SQLException | IOException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    public byte[] load(String namespace, String assetKey, String digest) throws SQLException, IOException {
        requireIdentity(namespace, assetKey);
        try (Connection connection = dataSource.getConnection()) {
            return load(connection, namespace, assetKey, digest);
        }
    }

    private byte[] load(Connection connection, String namespace, String assetKey, String digest)
            throws SQLException, IOException {
        if (digest == null || !digest.matches("sha256:[0-9a-f]{64}")) {
            throw new IOException("ARTIFACT_DIGEST_INVALID");
        }
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT document,digest FROM a2flow_asset_versions "
                + "WHERE namespace=? AND kind=? AND asset_key=? AND version_id=?")) {
            bindIdentity(statement, namespace, assetKey, digest);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new IOException("ARTIFACT_NOT_FOUND");
                }
                byte[] bytes = result.getBytes(1);
                if (!digest.equals(result.getString(2))) {
                    throw new IOException("ARTIFACT_DIGEST_MISMATCH");
                }
                verify(bytes, digest);
                return bytes;
            }
        }
    }

    private static void bindIdentity(PreparedStatement statement, String namespace, String assetKey,
            String digest) throws SQLException {
        statement.setString(1, "build-artifact:" + namespace);
        statement.setString(2, KIND);
        statement.setString(3, assetKey);
        statement.setString(4, digest);
    }

    private static void requireIdentity(String namespace, String assetKey) {
        if (namespace == null || namespace.isBlank() || assetKey == null || assetKey.isBlank()) {
            throw new IllegalArgumentException("ARTIFACT_IDENTITY_REQUIRED");
        }
    }

    private static void verify(byte[] bytes, String digest) throws IOException {
        if (bytes == null || bytes.length == 0 || bytes.length > MAX_BYTES
                || !PostgresSkillWorkspaceStore.sha256(bytes).equals(digest)) {
            throw new IOException("ARTIFACT_CONTENT_INVALID");
        }
    }
}
