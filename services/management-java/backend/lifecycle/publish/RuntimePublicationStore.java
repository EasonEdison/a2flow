package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;
import static dev.a2flow.management.lifecycle.publish.PublicationJson.*;

/** One namespace lock and transaction covers retained material, serving CAS and retry receipt. */
@Service
public final class RuntimePublicationStore {
    record Destination(String environment, String url, String user, String password, String database, String namespace) { }
    private final Map<String, Destination> destinations;
    public RuntimePublicationStore(Environment environment) {
        Map<String, Destination> values = new HashMap<>();
        for (String name : new String[]{"PRT", "ONLINE"}) {
            String prefix = "A2FLOW_PUBLICATION_" + name + "_";
            Destination destination = new Destination(name, environment.getRequiredProperty(prefix + "JDBC_URL"),
                    environment.getRequiredProperty(prefix + "USER"), environment.getRequiredProperty(prefix + "PASSWORD"),
                    environment.getRequiredProperty(prefix + "DATABASE"), environment.getRequiredProperty(prefix + "NAMESPACE"));
            if (!destination.url().startsWith("jdbc:postgresql:") || destination.database().isBlank()
                    || !destination.namespace().matches("[a-z][a-z0-9-]{0,63}")) throw new IllegalArgumentException("INVALID_PUBLICATION_DESTINATION");
            values.put(name, destination);
        }
        if (values.get("PRT").database().equals(values.get("ONLINE").database())) throw new IllegalArgumentException("SEPARATE_ENVIRONMENT_DATABASES_REQUIRED");
        destinations = Map.copyOf(values);
    }
    private Destination destination(String environment) throws IOException {
        Destination result = destinations.get(environment);
        if (result == null) throw failure("INVALID_ENVIRONMENT");
        return result;
    }
    private Connection connect(Destination destination) throws SQLException, IOException {
        Properties properties = new Properties();
        properties.setProperty("user", destination.user()); properties.setProperty("password", destination.password());
        properties.setProperty("connectTimeout", "5"); properties.setProperty("socketTimeout", "20");
        properties.setProperty("ApplicationName", "a2flow-java-publication");
        properties.setProperty("options", "-c statement_timeout=10000 -c lock_timeout=5000");
        Connection connection = DriverManager.getConnection(destination.url(), properties);
        try {
            connection.setAutoCommit(false);
            try (PreparedStatement query = connection.prepareStatement("SELECT current_database()"); ResultSet rows = query.executeQuery()) {
                if (!rows.next() || !destination.database().equals(rows.getString(1))) throw failure("DATABASE_MISMATCH");
            }
            try (PreparedStatement query = connection.prepareStatement("SELECT environment FROM a2flow_asset_environment WHERE singleton=TRUE"); ResultSet rows = query.executeQuery()) {
                if (!rows.next() || !destination.environment().equals(rows.getString(1)) || rows.next()) throw failure("DATABASE_ENVIRONMENT_MISMATCH");
            }
            long lock = ByteBuffer.wrap(java.util.HexFormat.of().parseHex(hash(destination.namespace().getBytes(StandardCharsets.UTF_8)))).getLong();
            try (PreparedStatement query = statement(connection, "SELECT pg_advisory_xact_lock(?)", lock)) { query.execute(); }
            return connection;
        } catch (SQLException | IOException exception) { connection.close(); throw exception; }
    }
    public String selection(String kind, String key, String environment) throws IOException {
        PublicationMaterial.key(kind, key); Destination target = destination(environment);
        try (Connection connection = connect(target)) {
            Snapshot snapshot = read(connection, target); validate(snapshot, environment);
            return digest(bytes(snapshot.states().get(identity(kind, key))));
        } catch (SQLException exception) { throw failure("ASSET_DATABASE_ERROR"); }
    }
    ObjectNode publish(String kind, String key, String environment, String receiptId, ObjectNode request,
            String version, ObjectNode definition, ArrayNode dependencies, String expectedServing) throws IOException {
        PublicationMaterial.key(kind, key); Destination target = destination(environment);
        if (!Set.of("SKILL", "ABILITY", "APPLICATION").contains(kind)) throw failure("UNKNOWN_ASSET_KIND");
        for (String field : new String[]{"sourceId", "sourceDigest", "requestId"}) {
            if (text(request, field).length() > 256) throw failure("PUBLICATION_FIELD_TYPE_INVALID");
        }
        String fingerprint = digest(bytes(request));
        try (Connection connection = connect(target)) {
            try {
                try (PreparedStatement query = statement(connection,
                        "SELECT request_digest,receipt FROM a2flow_management_publication_receipts WHERE namespace=? AND request_id=?", target.namespace(), receiptId);
                        ResultSet rows = query.executeQuery()) {
                    if (rows.next()) {
                        if (!fingerprint.equals(rows.getString(1))) throw failure("REQUEST_ID_CONFLICT");
                        ObjectNode receipt = (ObjectNode) parse(new String(rows.getBytes(2), StandardCharsets.UTF_8));
                        verifyRetained(connection, target.namespace(), kind, key, text(receipt, "versionId"), text(receipt, "contentDigest"));
                        connection.commit(); return receipt;
                    }
                }
                Snapshot before = read(connection, target); validate(before, environment);
                String id = identity(kind, key);
                JsonNode oldState = before.states().get(id);
                if (!digest(bytes(oldState)).equals(expectedServing)) throw failure("STALE_SERVING_SELECTION");
                String assetId = kind.toLowerCase(java.util.Locale.ROOT) + "-" + hash(key.getBytes(StandardCharsets.UTF_8));
                for (JsonNode asset : before.assets().values()) if (id.equals(identity(asset))) { assetId = text(asset, "assetId"); break; }
                ObjectNode candidate = object("kind", kind, "key", key, "assetId", assetId, "versionId", version,
                        "definition", definition, "dependencies", dependencies);
                byte[] material = bytes(candidate); String contentDigest = digest(material);
                String assetIdentity = id + "@" + version;
                JsonNode retained = before.assets().get(assetIdentity);
                if (retained != null && !Arrays.equals(bytes(retained), material)) throw failure("ASSET_CONFLICT");
                ObjectNode state = object("kind", kind, "key", key, "current", "PRT".equals(environment) ? version : null,
                        "stable", "ONLINE".equals(environment) ? version : null, "gray", null, "grayUserIds", array());
                before.assets().put(assetIdentity, candidate); before.states().put(id, state);
                validate(before, environment);
                if (retained == null) update(connection,
                        "INSERT INTO a2flow_asset_versions(namespace,kind,asset_key,version_id,document,digest) VALUES(?,?,?,?,?,?)",
                        target.namespace(), kind, key, version, material, contentDigest);
                int changed = oldState == null ? update(connection,
                        "INSERT INTO a2flow_asset_serving(namespace,kind,asset_key,document) VALUES(?,?,?,?) ON CONFLICT(namespace,kind,asset_key) DO NOTHING",
                        target.namespace(), kind, key, bytes(state)) : update(connection,
                        "UPDATE a2flow_asset_serving SET document=? WHERE namespace=? AND kind=? AND asset_key=? AND document=?",
                        bytes(state), target.namespace(), kind, key, bytes(oldState));
                if (changed != 1) throw failure("STALE_SERVING_SELECTION");
                Snapshot observed = read(connection, target); validate(observed, environment);
                if (!Arrays.equals(bytes(state), bytes(observed.states().get(id)))) throw failure("READBACK_SERVING_MISMATCH");
                verifyRetained(connection, target.namespace(), kind, key, version, contentDigest);
                ObjectNode receipt = object("published", true, "environment", environment, "versionId", version,
                        "contentDigest", contentDigest, "servingDigest", digest(bytes(state)), "requestId", request.get("requestId"));
                if ("SKILL".equals(kind)) { receipt.put("assetKey", key); receipt.set("packageDigest", request.get("packageDigest")); }
                else { receipt.put("kind", kind); receipt.put("key", key); receipt.set("sourceId", request.get("sourceId")); receipt.set("sourceDigest", request.get("sourceDigest")); }
                update(connection, "INSERT INTO a2flow_management_publication_receipts(namespace,request_id,request_digest,receipt) VALUES(?,?,?,?)",
                        target.namespace(), receiptId, fingerprint, bytes(receipt));
                connection.commit(); return receipt;
            } catch (SQLException | IOException exception) { connection.rollback(); throw exception; }
        } catch (SQLException exception) { throw failure("PUBLICATION_DATABASE_OUTCOME_REQUIRES_RETRY"); }
    }
    private static void verifyRetained(Connection connection, String ns, String kind, String key, String version, String expected) throws SQLException, IOException {
        try (PreparedStatement query = statement(connection, "SELECT document,digest FROM a2flow_asset_versions WHERE namespace=? AND kind=? AND asset_key=? AND version_id=?", ns, kind, key, version);
                ResultSet rows = query.executeQuery()) {
            if (!rows.next() || !expected.equals(rows.getString(2)) || !expected.equals(digest(rows.getBytes(1)))) throw failure("RECEIPT_READBACK_MISMATCH");
        }
    }
    record Snapshot(Map<String, JsonNode> assets, Map<String, JsonNode> states) { }
    private static Snapshot read(Connection connection, Destination target) throws SQLException, IOException {
        Map<String, JsonNode> assets = new HashMap<>(), states = new HashMap<>();
        long total = 0;
        long persistedBytes = 0;
        for (String table : new String[]{"a2flow_asset_versions", "a2flow_asset_serving"}) {
            try (PreparedStatement query = statement(connection, "SELECT count(*),coalesce(sum(octet_length(document)),0) FROM " + table + " WHERE namespace=?", target.namespace()); ResultSet rows = query.executeQuery()) {
                rows.next();
                if (rows.getLong(1) > 128) throw failure("ASSET_LIMIT");
                persistedBytes += rows.getLong(2);
                if (persistedBytes > MAX_BYTES) throw failure("BUNDLE_TOO_LARGE");
            }
        }
        try (PreparedStatement query = statement(connection, "SELECT kind,asset_key,version_id,document,digest FROM a2flow_asset_versions WHERE namespace=? ORDER BY kind,asset_key,version_id", target.namespace()); ResultSet rows = query.executeQuery()) {
            while (rows.next()) {
                byte[] raw = rows.getBytes(4); total += raw.length;
                if (total > MAX_BYTES || assets.size() >= 128) throw failure("BUNDLE_TOO_LARGE");
                JsonNode asset = parse(new String(raw, StandardCharsets.UTF_8));
                if (!digest(raw).equals(rows.getString(5)) || !Arrays.equals(raw, bytes(asset))) throw failure("READBACK_DIGEST_MISMATCH");
                if (!rows.getString(1).equals(asset.path("kind").asText()) || !rows.getString(2).equals(asset.path("key").asText())
                        || !rows.getString(3).equals(asset.path("versionId").asText())) throw failure("READBACK_IDENTITY_MISMATCH");
                assets.put(identity(asset) + "@" + rows.getString(3), asset);
            }
        }
        try (PreparedStatement query = statement(connection, "SELECT kind,asset_key,document FROM a2flow_asset_serving WHERE namespace=?", target.namespace()); ResultSet rows = query.executeQuery()) {
            while (rows.next()) {
                byte[] raw = rows.getBytes(3); total += raw.length;
                if (total > MAX_BYTES || states.size() >= 128) throw failure("BUNDLE_TOO_LARGE");
                JsonNode state = parse(new String(raw, StandardCharsets.UTF_8));
                if (!Arrays.equals(raw, bytes(state)) || !rows.getString(1).equals(state.path("kind").asText())
                        || !rows.getString(2).equals(state.path("key").asText())) throw failure("READBACK_IDENTITY_MISMATCH");
                states.put(identity(state), state);
            }
        }
        return new Snapshot(assets, states);
    }
    static String identity(String kind, String key) { return kind + ":" + key; }
    static String identity(JsonNode node) throws IOException { return identity(text(node, "kind"), text(node, "key")); }
    private static PreparedStatement statement(Connection connection, String sql, Object... values) throws SQLException {
        PreparedStatement result = connection.prepareStatement(sql);
        for (int index = 0; index < values.length; index++) {
            if (values[index] instanceof byte[] bytes) result.setBytes(index + 1, bytes); else result.setObject(index + 1, values[index]);
        }
        return result;
    }
    private static int update(Connection connection, String sql, Object... values) throws SQLException {
        try (PreparedStatement query = statement(connection, sql, values)) { return query.executeUpdate(); }
    }
    static void validate(Snapshot snapshot, String environment) throws IOException {
        PublicationValidation.validate(snapshot, environment);
    }
}
