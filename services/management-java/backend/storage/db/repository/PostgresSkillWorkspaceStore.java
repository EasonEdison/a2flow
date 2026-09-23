package dev.a2flow.management.storage.db.repository;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import javax.sql.DataSource;

import com.fasterxml.jackson.databind.ObjectMapper;

/** PostgreSQL is authoritative; directories created by this adapter are disposable projections. */
public final class PostgresSkillWorkspaceStore {
    private final DataSource dataSource;
    private final ObjectMapper mapper;

    public PostgresSkillWorkspaceStore(DataSource dataSource, ObjectMapper mapper) {
        this.dataSource = java.util.Objects.requireNonNull(dataSource);
        this.mapper = java.util.Objects.requireNonNull(mapper);
    }

    public static final class Entry {
        public String handleId;
        public String logicalPath;
        public String mediaType;
        public long byteSize;
        public String contentDigest;
        public String base64;

        public byte[] bytes() throws IOException {
            final byte[] value;
            try {
                value = Base64.getDecoder().decode(base64);
            } catch (IllegalArgumentException | NullPointerException e) {
                throw new IOException("Invalid workspace entry encoding", e);
            }
            if (value.length != byteSize || !sha256(value).equals(contentDigest)) {
                throw new IOException("Workspace entry integrity mismatch: " + logicalPath);
            }
            return value;
        }
    }

    public static final class Document {
        public long baseDraftRevision;
        public List<Entry> entries = new ArrayList<>();
        public boolean dirty;
    }

    public static final class Snapshot {
        public final long revision;
        public final Document document;

        public Snapshot(long revision, Document document) {
            this.revision = revision;
            this.document = document;
        }
    }

    public Optional<Snapshot> load(String namespace, String assetKey) throws SQLException, IOException {
        try (Connection connection = dataSource.getConnection()) {
            return load(connection, namespace, assetKey);
        }
    }

    /** Does not commit, roll back, or close the caller's transaction connection. */
    public Optional<Snapshot> load(Connection connection, String namespace, String assetKey)
            throws SQLException, IOException {
        try (PreparedStatement statement = connection.prepareStatement(
                        "SELECT revision, document, digest FROM a2flow_management_drafts "
                                + "WHERE namespace = ? AND kind = 'SKILL' AND asset_key = ?")) {
            statement.setString(1, workspaceNamespace(namespace));
            statement.setString(2, required(assetKey));
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty();
                }
                byte[] bytes = result.getBytes("document");
                if (!sha256(bytes).equals(result.getString("digest"))) {
                    throw new IOException("Workspace document integrity mismatch");
                }
                Document document = mapper.readValue(bytes, Document.class);
                validate(document);
                return Optional.of(new Snapshot(result.getLong("revision"), document));
            }
        }
    }

    /** expectedRevision == 0 creates; all subsequent writes compare-and-swap the existing row. */
    public Snapshot save(String namespace, String assetKey, long expectedRevision, Document document,
            long updatedBy) throws SQLException, IOException {
        try (Connection connection = dataSource.getConnection()) {
            return save(connection, namespace, assetKey, expectedRevision, document, updatedBy);
        }
    }

    /** Does not commit, roll back, or close the caller's transaction connection. */
    public Snapshot save(Connection connection, String namespace, String assetKey, long expectedRevision,
            Document document, long updatedBy) throws SQLException, IOException {
        if (expectedRevision < 0 || expectedRevision == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid workspace revision");
        }
        validate(document);
        byte[] bytes = mapper.writeValueAsBytes(document);
        long revision = expectedRevision + 1;
        String sql = expectedRevision == 0
                ? "INSERT INTO a2flow_management_drafts "
                        + "(namespace, kind, asset_key, revision, document, digest, updated_by) "
                        + "VALUES (?, 'SKILL', ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING"
                : "UPDATE a2flow_management_drafts SET revision = ?, document = ?, digest = ?, updated_by = ? "
                        + "WHERE namespace = ? AND kind = 'SKILL' AND asset_key = ? AND revision = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            if (expectedRevision == 0) {
                statement.setString(1, workspaceNamespace(namespace));
                statement.setString(2, required(assetKey));
                statement.setLong(3, revision);
                statement.setBytes(4, bytes);
                statement.setString(5, sha256(bytes));
                statement.setLong(6, updatedBy);
            } else {
                statement.setLong(1, revision);
                statement.setBytes(2, bytes);
                statement.setString(3, sha256(bytes));
                statement.setLong(4, updatedBy);
                statement.setString(5, workspaceNamespace(namespace));
                statement.setString(6, required(assetKey));
                statement.setLong(7, expectedRevision);
            }
            if (statement.executeUpdate() != 1) {
                throw new java.util.ConcurrentModificationException("Workspace revision changed; reload before saving");
            }
        }
        return new Snapshot(revision, mapper.readValue(bytes, Document.class));
    }

    /** Returns a copy with one file updated; no mutation occurs until save succeeds. */
    public Document put(Document source, String logicalPath, String mediaType, byte[] bytes) throws IOException {
        validatePath(logicalPath);
        Document target = copy(source);
        Entry previous = target.entries.stream().filter(entry -> logicalPath.equals(entry.logicalPath))
                .findFirst().orElse(null);
        Entry entry = new Entry();
        entry.handleId = previous == null ? UUID.randomUUID().toString() : previous.handleId;
        entry.logicalPath = logicalPath;
        entry.mediaType = required(mediaType);
        entry.byteSize = bytes.length;
        entry.contentDigest = sha256(bytes);
        entry.base64 = Base64.getEncoder().encodeToString(bytes);
        target.entries.removeIf(item -> logicalPath.equals(item.logicalPath));
        target.entries.add(entry);
        target.entries.sort(Comparator.comparing(item -> item.logicalPath));
        target.dirty = true;
        validate(target);
        return target;
    }

    public Document delete(Document source, String logicalPath, boolean recursive) throws IOException {
        validatePath(logicalPath);
        Document target = copy(source);
        boolean removed = target.entries.removeIf(entry -> entry.logicalPath.equals(logicalPath)
                || (recursive && entry.logicalPath.startsWith(logicalPath + "/")));
        if (!removed) {
            throw new java.io.FileNotFoundException(logicalPath);
        }
        target.dirty = true;
        return target;
    }

    /** Caller supplies an existing trusted parent. Creates a fresh directory, never overlays stale files. */
    public Path materialize(Document document, Path parent) throws IOException {
        validate(document);
        Path trustedParent = parent.toRealPath();
        if (!Files.isDirectory(trustedParent, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Workspace projection parent is not a directory");
        }
        Path root = Files.createTempDirectory(trustedParent, "skill-workspace-");
        try {
            for (Entry entry : document.entries) {
                Path target = root.resolve(entry.logicalPath).normalize();
                Files.createDirectories(target.getParent());
                Files.write(target, entry.bytes(), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            }
            return root;
        } catch (IOException | RuntimeException failure) {
            // Only remove the brand-new projection owned by this invocation.
            try (java.util.stream.Stream<Path> files = Files.walk(root)) {
                for (Path path : files.sorted(Comparator.reverseOrder()).collect(java.util.stream.Collectors.toList())) {
                    Files.deleteIfExists(path);
                }
            } catch (IOException cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
            throw failure;
        }
    }

    private Document copy(Document source) throws IOException {
        validate(source);
        return mapper.readValue(mapper.writeValueAsBytes(source), Document.class);
    }

    public static void validate(Document document) throws IOException {
        if (document == null || document.entries == null || document.baseDraftRevision < 0) {
            throw new IOException("Invalid workspace document");
        }
        Set<String> paths = new HashSet<>();
        Set<String> handles = new HashSet<>();
        for (Entry entry : document.entries) {
            if (entry == null) {
                throw new IOException("Missing workspace entry");
            }
            validatePath(entry.logicalPath);
            if (entry.handleId == null || entry.handleId.isBlank() || !handles.add(entry.handleId)
                    || entry.mediaType == null || entry.mediaType.isBlank() || !paths.add(entry.logicalPath)) {
                throw new IOException("Invalid or duplicate workspace entry");
            }
            entry.bytes();
        }
        for (String path : paths) {
            int slash = path.indexOf('/');
            while (slash >= 0) {
                if (paths.contains(path.substring(0, slash))) {
                    throw new IOException("Workspace path is both file and directory: " + path);
                }
                slash = path.indexOf('/', slash + 1);
            }
        }
    }

    private static void validatePath(String path) throws IOException {
        if (path == null || path.isBlank() || path.startsWith("/") || path.contains("\\")
                || path.indexOf('\0') >= 0 || path.contains(":")) {
            throw new IOException("Invalid workspace logical path");
        }
        for (String part : path.split("/", -1)) {
            if (part.isEmpty() || part.equals(".") || part.equals("..")) {
                throw new IOException("Noncanonical workspace logical path");
            }
        }
    }

    public static String workspaceNamespace(String namespace) {
        return "skill-workspace:" + sha256(required(namespace).getBytes(StandardCharsets.UTF_8)).substring(7);
    }

    public static String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder hex = new StringBuilder("sha256:");
            for (byte value : digest) {
                hex.append(String.format("%02x", value & 0xff));
            }
            return hex.toString();
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static String required(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Required workspace identity or media type is blank");
        }
        return value;
    }
}
