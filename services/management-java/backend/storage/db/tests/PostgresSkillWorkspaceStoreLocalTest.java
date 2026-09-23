package dev.a2flow.management.storage.db.repository;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import javax.sql.DataSource;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Local contract tests only. Does not claim JDBC or deployed PostgreSQL integration coverage. */
public final class PostgresSkillWorkspaceStoreLocalTest {
    public static void main(String[] args) throws Exception {
        DataSource noConnections = (DataSource) java.lang.reflect.Proxy.newProxyInstance(
                DataSource.class.getClassLoader(), new Class<?>[] {DataSource.class},
                (proxy, method, values) -> { throw new AssertionError("Local test must not access a database"); });
        PostgresSkillWorkspaceStore store = new PostgresSkillWorkspaceStore(noConnections, new ObjectMapper());
        PostgresSkillWorkspaceStore.Document empty = new PostgresSkillWorkspaceStore.Document();
        empty.baseDraftRevision = 7;
        PostgresSkillWorkspaceStore.Document document = store.put(empty, "docs/你好.md", "text/markdown",
                "hello 世界".getBytes(StandardCharsets.UTF_8));
        check(empty.entries.isEmpty(), "put mutated input");
        check(document.baseDraftRevision == 7 && document.dirty, "draft metadata changed");
        String handle = document.entries.get(0).handleId;
        document = store.put(document, "docs/你好.md", "text/markdown", new byte[] {0, 1, 2, -1});
        check(handle.equals(document.entries.get(0).handleId), "handle changed on edit");
        PostgresSkillWorkspaceStore.Document finalDocument = document;
        expectFailure(() -> store.put(empty, "../escape", "text/plain", new byte[0]));
        expectFailure(() -> store.put(empty, "a//b", "text/plain", new byte[0]));
        expectFailure(() -> store.put(empty, "a\\b", "text/plain", new byte[0]));
        expectFailure(() -> store.put(finalDocument, "docs", "text/plain", new byte[0]));
        Path parent = Files.createTempDirectory("skill-db-contract-test-");
        try {
            Path first = store.materialize(document, parent);
            Files.writeString(first.resolve("stale.txt"), "stale");
            Path second = store.materialize(document, parent);
            check(!first.equals(second) && !Files.exists(second.resolve("stale.txt")), "stale files reused");
            check(java.util.Arrays.equals(Files.readAllBytes(second.resolve("docs/你好.md")),
                    new byte[] {0, 1, 2, -1}), "binary restore changed bytes");
            check(store.delete(document, "docs", true).entries.isEmpty(), "recursive delete failed");
            check(document.entries.size() == 1, "delete mutated input");
            document.entries.get(0).contentDigest = "sha256:invalid";
            expectFailure(() -> store.materialize(finalDocument, parent));
        } finally {
            try (java.util.stream.Stream<Path> files = Files.walk(parent)) {
                for (Path path : files.sorted(Comparator.reverseOrder()).collect(java.util.stream.Collectors.toList())) {
                    Files.delete(path);
                }
            }
        }
        System.out.println("PASS: byte integrity, Unicode paths, stable handles, defensive copy, path traversal, "
                + "file/directory collisions, fresh restoration, recursive deletion; JDBC NOT RUN");
    }

    private interface Checked { void run() throws Exception; }

    private static void expectFailure(Checked action) throws Exception {
        try {
            action.run();
            throw new AssertionError("Expected IOException");
        } catch (IOException expected) {
            // Expected rejection of malformed content or paths.
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
