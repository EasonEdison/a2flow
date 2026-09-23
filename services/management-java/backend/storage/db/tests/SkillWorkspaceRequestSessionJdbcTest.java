package dev.a2flow.management.storage.db.repository;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.Statement;
import org.postgresql.ds.PGSimpleDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.transaction.support.TransactionTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.a2flow.management.access.ManagementIdentityProvider;

/** Local real-PostgreSQL test of projection persistence and shared transaction rollback. */
public final class SkillWorkspaceRequestSessionJdbcTest {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !args[0].matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/workspace_adapter_test")) {
            throw new IllegalArgumentException("Requires an explicit local workspace_adapter_test JDBC URL");
        }
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL(args[0]);
        dataSource.setUser(System.getProperty("user.name"));
        ObjectMapper mapper = new ObjectMapper();
        PostgresSkillWorkspaceStore store = new PostgresSkillWorkspaceStore(dataSource, mapper);
        TransactionTemplate transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
        ManagementIdentityProvider identity = new ManagementIdentityProvider() {
            public String namespace() { return "transaction-test"; }
            public long userId() { return 91; }
        };
        SkillFactoryWorkspaceFileRepository files = new SkillFactoryWorkspaceFileRepository();
        SkillWorkspaceRequestSession first = new SkillWorkspaceRequestSession(dataSource, mapper, files, identity);
        Path parent = Files.createTempDirectory("skill-projection-test-");
        try {
            try {
                first.create("skill-transaction", 0);
                throw new AssertionError("Nontransactional write accepted");
            } catch (IllegalStateException expected) {
                // Writes require a real transaction associated with the configured DataSource.
            }
            transaction.execute(status -> {
                try {
                    first.create("skill-transaction", 0);
                    return null;
                } catch (Exception failure) {
                    throw new RuntimeException(failure);
                }
            });
            first.load("skill-transaction", parent);
            first.save("skill-transaction");
            PostgresSkillWorkspaceStore.Snapshot untouched = store.load("transaction-test", "skill-transaction")
                    .orElseThrow();
            check(untouched.revision == 1 && !untouched.document.dirty,
                    "read-only empty draft became dirty or changed revision");
            transaction.execute(status -> {
                try {
                    Path workspace = first.load("skill-transaction", parent);
                    Files.writeString(workspace.resolve("SKILL.md"), "committed");
                    first.save("skill-transaction");
                    return null;
                } catch (Exception failure) {
                    throw new RuntimeException(failure);
                }
            });
            Path original = first.load("skill-transaction", parent);
            long unchangedRevision = store.load("transaction-test", "skill-transaction").orElseThrow().revision;
            boolean unchangedDirty = store.load("transaction-test", "skill-transaction").orElseThrow().document.dirty;
            check(!first.hasChanges("skill-transaction"), "unchanged projection reported dirty");
            first.save("skill-transaction");
            PostgresSkillWorkspaceStore.Snapshot afterRead = store.load("transaction-test", "skill-transaction")
                    .orElseThrow();
            check(afterRead.revision == unchangedRevision && afterRead.document.dirty == unchangedDirty,
                    "read-only projection changed revision or dirty state");
            first.close();
            check(!Files.exists(original), "projection was not cleaned");
            SkillWorkspaceRequestSession second = new SkillWorkspaceRequestSession(dataSource, mapper, files, identity);
            try {
                Path restored = second.load("skill-transaction", parent);
                check(Files.readString(restored.resolve("SKILL.md")).equals("committed"), "DB restoration failed");
                transaction.execute(status -> {
                    try {
                        Files.writeString(restored.resolve("SKILL.md"), "must roll back");
                        second.save("skill-transaction");
                        Connection connection = DataSourceUtils.getConnection(dataSource);
                        try (Statement statement = connection.createStatement()) {
                            statement.execute("CREATE TABLE metadata_rollback_marker (id INTEGER)");
                        } finally {
                            DataSourceUtils.releaseConnection(connection, dataSource);
                        }
                        status.setRollbackOnly();
                        return null;
                    } catch (Exception failure) {
                        throw new RuntimeException(failure);
                    }
                });
                check(new String(store.load("transaction-test", "skill-transaction").orElseThrow()
                        .document.entries.get(0).bytes(), java.nio.charset.StandardCharsets.UTF_8).equals("committed"),
                        "workspace write escaped rollback");
                try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement();
                        java.sql.ResultSet result = statement.executeQuery("SELECT to_regclass('metadata_rollback_marker')")) {
                    result.next();
                    check(result.getString(1) == null, "metadata write escaped rollback");
                }
            } finally {
                second.close();
            }
        } finally {
            first.close();
            Files.delete(parent);
        }
        System.out.println("PASS PostgreSQL session: trusted identity, transaction required, save, fresh request restore, "
                + "read-only no revision/dirty write, shared metadata/file rollback, projection cleanup");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
