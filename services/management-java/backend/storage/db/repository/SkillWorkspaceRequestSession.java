package dev.a2flow.management.storage.db.repository;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import jakarta.annotation.PreDestroy;
import javax.sql.DataSource;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import dev.a2flow.management.access.ManagementIdentityProvider;

/** One disposable working copy per authenticated request; PostgreSQL remains authoritative. */
@Component
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class SkillWorkspaceRequestSession {
    private final DataSource dataSource;
    private final PostgresSkillWorkspaceStore store;
    private final SkillFactoryWorkspaceFileRepository files;
    private final String namespace;
    private final long userId;
    private final Map<String, WorkingCopy> workspaces = new LinkedHashMap<>();

    public SkillWorkspaceRequestSession(DataSource dataSource, ObjectMapper mapper,
            SkillFactoryWorkspaceFileRepository files, ManagementIdentityProvider identity) {
        this.dataSource = dataSource;
        this.store = new PostgresSkillWorkspaceStore(dataSource, mapper);
        this.files = files;
        this.namespace = identity.namespace();
        this.userId = identity.userId();
        if (namespace == null || namespace.isBlank()) {
            throw new IllegalStateException("Authenticated management identity is required");
        }
    }

    public boolean exists(String assetKey) throws IOException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            return store.load(connection, namespace, assetKey).isPresent();
        } catch (SQLException failure) {
            throw new IOException("Cannot read PostgreSQL workspace", failure);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    public Path load(String assetKey, Path projectionParent) throws IOException {
        WorkingCopy existing = workspaces.get(assetKey);
        if (existing != null) {
            return existing.path;
        }
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            PostgresSkillWorkspaceStore.Snapshot snapshot = store.load(connection, namespace, assetKey)
                    .orElseThrow(() -> new java.io.FileNotFoundException("PostgreSQL workspace does not exist"));
            Files.createDirectories(projectionParent);
            Path path = store.materialize(snapshot.document, projectionParent);
            workspaces.put(assetKey, new WorkingCopy(path, snapshot));
            return path;
        } catch (SQLException failure) {
            throw new IOException("Cannot read PostgreSQL workspace", failure);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    /** Must participate in the same transaction as Skill metadata creation. */
    public void create(String assetKey, long baseDraftRevision) throws IOException {
        requireTransaction();
        PostgresSkillWorkspaceStore.Document document = new PostgresSkillWorkspaceStore.Document();
        document.baseDraftRevision = baseDraftRevision;
        document.dirty = false;
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            store.save(connection, namespace, assetKey, 0, document, userId);
        } catch (SQLException failure) {
            throw new IOException("Cannot create PostgreSQL workspace", failure);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    /** Persist the request's edited projection via CAS, sharing the metadata transaction connection. */
    public void save(String assetKey) throws IOException {
        WorkingCopy copy = workspaces.get(assetKey);
        if (copy == null) {
            throw new IllegalStateException("Load the PostgreSQL workspace before editing");
        }
        PostgresSkillWorkspaceStore.Document document = files.captureDocument(store, copy.snapshot.document, copy.path);
        if (sameFiles(document, copy.snapshot.document)) {
            return;
        }
        requireTransaction();
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            copy.snapshot = store.save(connection, namespace, assetKey, copy.snapshot.revision, document, userId);
        } catch (SQLException failure) {
            throw new IOException("Cannot save PostgreSQL workspace", failure);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    public boolean hasChanges(String assetKey) throws IOException {
        WorkingCopy copy = workspaces.get(assetKey);
        if (copy == null) {
            throw new IllegalStateException("Load the PostgreSQL workspace before checking changes");
        }
        return !sameFiles(files.captureDocument(store, copy.snapshot.document, copy.path), copy.snapshot.document);
    }

    private void requireTransaction() {
        if (!TransactionSynchronizationManager.isActualTransactionActive()
                || !TransactionSynchronizationManager.hasResource(dataSource)) {
            throw new IllegalStateException("Workspace and metadata require the same active DataSource transaction");
        }
    }

    private boolean sameFiles(PostgresSkillWorkspaceStore.Document current,
            PostgresSkillWorkspaceStore.Document previous) {
        if (current.entries.size() != previous.entries.size()) {
            return false;
        }
        Map<String, String> oldDigests = new LinkedHashMap<>();
        for (PostgresSkillWorkspaceStore.Entry entry : previous.entries) {
            oldDigests.put(entry.logicalPath, entry.contentDigest);
        }
        return current.entries.stream().allMatch(entry -> entry.contentDigest.equals(oldDigests.get(entry.logicalPath)));
    }

    @PreDestroy
    public void close() throws IOException {
        IOException failure = null;
        for (WorkingCopy copy : workspaces.values()) {
            try (java.util.stream.Stream<Path> paths = Files.walk(copy.path)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).collect(java.util.stream.Collectors.toList())) {
                    Files.deleteIfExists(path);
                }
            } catch (IOException cleanupFailure) {
                if (failure == null) {
                    failure = cleanupFailure;
                } else {
                    failure.addSuppressed(cleanupFailure);
                }
            }
        }
        workspaces.clear();
        if (failure != null) {
            throw failure;
        }
    }

    private static final class WorkingCopy {
        private final Path path;
        private PostgresSkillWorkspaceStore.Snapshot snapshot;

        private WorkingCopy(Path path, PostgresSkillWorkspaceStore.Snapshot snapshot) {
            this.path = path;
            this.snapshot = snapshot;
        }
    }
}
