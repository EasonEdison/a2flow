package dev.a2flow.management.storage.db.repository;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.Statement;
import java.util.Arrays;
import org.postgresql.ds.PGSimpleDataSource;

/** Executable integration check; requires an explicitly supplied disposable PostgreSQL database. */
public final class PostgresArtifactRepositoryJdbcTest {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Supply disposable JDBC URL and username");
        }
        PGSimpleDataSource source = new PGSimpleDataSource();
        source.setURL(args[0]);
        source.setUser(args[1]);
        try (Connection connection = source.getConnection(); Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE IF NOT EXISTS a2flow_asset_versions (namespace TEXT NOT NULL,"
                    + "kind TEXT NOT NULL,asset_key TEXT NOT NULL,version_id TEXT NOT NULL,document BYTEA NOT NULL,"
                    + "digest TEXT NOT NULL,PRIMARY KEY(namespace,kind,asset_key,version_id))");
        }
        String namespace = "artifact-test-" + java.util.UUID.randomUUID();
        PostgresArtifactRepository repository = new PostgresArtifactRepository(source);
        byte[] bytes = "immutable package 中文\u0000".getBytes(StandardCharsets.UTF_8);
        String digest = PostgresSkillWorkspaceStore.sha256(bytes);
        repository.save(namespace, "test-skill", bytes, digest);
        repository.save(namespace, "test-skill", bytes, digest);
        if (!Arrays.equals(bytes, repository.load(namespace, "test-skill", digest))) {
            throw new AssertionError("Round trip changed artifact bytes");
        }
        mustFail(() -> repository.load(namespace + "-other", "test-skill", digest));
        mustFail(() -> repository.load(namespace, "different-skill", digest));
        mustFail(() -> repository.save(namespace, "test-skill", new byte[] {1}, digest));
        try (Connection connection = source.getConnection(); var statement = connection.prepareStatement(
                "UPDATE a2flow_asset_versions SET document=? WHERE namespace=? AND kind='BUILD_ARTIFACT'")) {
            statement.setBytes(1, new byte[] {0});
            statement.setString(2, "build-artifact:" + namespace);
            statement.executeUpdate();
        }
        mustFail(() -> repository.load(namespace, "test-skill", digest));
        mustFail(() -> repository.save(namespace, "test-skill", bytes, digest));
        System.out.println("ARTIFACT_JDBC_PASS: roundtrip, idempotency, isolation, mismatch, corruption, immutability");
    }

    private static void mustFail(Checked operation) throws Exception {
        try {
            operation.run();
        } catch (IOException expected) {
            return;
        }
        throw new AssertionError("Expected artifact failure");
    }

    @FunctionalInterface
    private interface Checked { void run() throws Exception; }
}
