package dev.a2flow.management.storage.db.repository;

import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.Statement;
import org.postgresql.ds.PGSimpleDataSource;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Run only against a newly initialized local disposable cluster. Creates test schema. */
public final class PostgresSkillWorkspaceStoreJdbcTest {
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !args[0].matches("jdbc:postgresql://127\\.0\\.0\\.1:[0-9]+/workspace_adapter_test")) {
            throw new IllegalArgumentException("Requires an explicit local workspace_adapter_test JDBC URL");
        }
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL(args[0]);
        dataSource.setUser(System.getProperty("user.name"));
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE a2flow_management_drafts (namespace TEXT NOT NULL, kind TEXT NOT NULL, "
                    + "asset_key TEXT NOT NULL, revision BIGINT NOT NULL, document BYTEA NOT NULL, digest TEXT NOT NULL, "
                    + "updated_by BIGINT NOT NULL, PRIMARY KEY(namespace, kind, asset_key))");
        }
        PostgresSkillWorkspaceStore store = new PostgresSkillWorkspaceStore(dataSource, new ObjectMapper());
        PostgresSkillWorkspaceStore.Document document = store.put(new PostgresSkillWorkspaceStore.Document(),
                "SKILL.md", "text/markdown", "数据库中的 Skill".getBytes(StandardCharsets.UTF_8));
        document.baseDraftRevision = 3;
        check(store.load("test-namespace", "skill-a").isEmpty(), "nonexistent row returned");
        PostgresSkillWorkspaceStore.Snapshot created = store.save("test-namespace", "skill-a", 0, document, 42);
        check(created.revision == 1, "wrong create revision");
        conflict(() -> store.save("test-namespace", "skill-a", 0, document, 42));
        PostgresSkillWorkspaceStore.Snapshot loaded = store.load("test-namespace", "skill-a").orElseThrow();
        check(loaded.document.baseDraftRevision == 3 && loaded.document.entries.size() == 1, "wrong document");
        check(new String(loaded.document.entries.get(0).bytes(), StandardCharsets.UTF_8)
                .equals("数据库中的 Skill"), "database roundtrip changed bytes");
        PostgresSkillWorkspaceStore.Document edited = store.put(loaded.document, "scripts/main.py", "text/x-python",
                "print('hello')".getBytes(StandardCharsets.UTF_8));
        check(store.save("test-namespace", "skill-a", loaded.revision, edited, 43).revision == 2, "wrong update revision");
        conflict(() -> store.save("test-namespace", "skill-a", loaded.revision, document, 44));
        check(store.load("other-namespace", "skill-a").isEmpty(), "namespace isolation failed");
        PostgresSkillWorkspaceStore.Document deleted = store.delete(edited, "scripts", true);
        store.save("test-namespace", "skill-a", 2, deleted, 45);
        check(store.load("test-namespace", "skill-a").orElseThrow().document.entries.size() == 1,
                "delete was not persisted");
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
            statement.execute("UPDATE a2flow_management_drafts SET digest = 'sha256:corrupted'");
        }
        try {
            store.load("test-namespace", "skill-a");
            throw new AssertionError("Corrupt digest accepted");
        } catch (java.io.IOException expected) {
            // Database integrity mismatch must fail closed.
        }
        System.out.println("PASS PostgreSQL: create/read/update/delete, binary document roundtrip, revision CAS, "
                + "duplicate create conflict, namespace isolation, corrupt digest rejection");
    }

    private interface Checked { void run() throws Exception; }

    private static void conflict(Checked action) throws Exception {
        try {
            action.run();
            throw new AssertionError("Expected revision conflict");
        } catch (java.util.ConcurrentModificationException expected) {
            // Expected optimistic concurrency rejection.
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
