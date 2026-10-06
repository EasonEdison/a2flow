package dev.a2flow.management.lifecycle.publish;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HashSet;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.zip.ZipInputStream;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import static dev.a2flow.management.lifecycle.publish.PublicationJson.*;

/** Lossless material envelopes and bounded archive validation. */
final class PublicationMaterial {
    private PublicationMaterial() { }
    static void key(String kind, String key) throws IOException {
        if (key == null || key.length() > 128 || !key.matches("SKILL".equals(kind)
                ? "[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*" : "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw failure("INVALID_ASSET_KEY");
        }
    }
    static ObjectNode skill(String key, byte[] raw, String expected) throws IOException {
        key("SKILL", key);
        if (raw.length > MAX_BYTES || !digest(raw).equals(expected)) throw failure("PACKAGE_DIGEST_OR_SIZE_INVALID");
        // ZIP's central directory owns Unix symlink flags, absent from ZipEntry's API.
        ByteBuffer directory = ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN);
        int end = -1;
        for (int offset = raw.length - 22; offset >= Math.max(0, raw.length - 65557); offset--) {
            if (directory.getInt(offset) == 0x06054b50 && offset + 22 + Short.toUnsignedInt(directory.getShort(offset + 20)) == raw.length) { end = offset; break; }
        }
        if (end < 0 || directory.getShort(end + 4) != 0 || directory.getShort(end + 6) != 0) throw failure("INVALID_SKILL_PACKAGE");
        int centralEntries = Short.toUnsignedInt(directory.getShort(end + 10));
        int offset = directory.getInt(end + 16);
        if (centralEntries == 0 || centralEntries > 256 || offset < 0) throw failure("PACKAGE_ENTRY_LIMIT");
        for (int index = 0; index < centralEntries; index++) {
            if (offset + 46 > end || directory.getInt(offset) != 0x02014b50) throw failure("INVALID_SKILL_PACKAGE");
            if ((directory.getShort(offset + 8) & 1) != 0
                    || ((directory.getInt(offset + 38) >>> 16) & 0170000) == 0120000) {
                throw failure("PACKAGE_PATH_DUPLICATE_OR_LINK");
            }
            offset += 46 + Short.toUnsignedInt(directory.getShort(offset + 28))
                    + Short.toUnsignedInt(directory.getShort(offset + 30)) + Short.toUnsignedInt(directory.getShort(offset + 32));
        }
        if (offset != end) throw failure("INVALID_SKILL_PACKAGE");
        TreeMap<String, ObjectNode> files = new TreeMap<>();
        int total = 0, count = 0;
        try (ZipInputStream archive = new ZipInputStream(new ByteArrayInputStream(raw), StandardCharsets.UTF_8)) {
            for (var entry = archive.getNextEntry(); entry != null; entry = archive.getNextEntry()) {
                if (++count > 256 || !entry.getName().startsWith(key + "/")) throw failure("PACKAGE_ROOT_OR_ENCRYPTION_INVALID");
                if (entry.isDirectory()) continue;
                String path = entry.getName().substring(key.length() + 1);
                String[] segments = path.split("/", -1);
                if (path.length() > 1024 || segments.length > 32 || !path.matches("[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")
                        || java.util.Arrays.stream(segments).anyMatch(part -> part.equals(".") || part.equals(".."))
                        || files.containsKey(path)) throw failure("PACKAGE_PATH_DUPLICATE_OR_LINK");
                byte[] content = archive.readNBytes(4 * 1024 * 1024 + 1);
                total += content.length;
                if (content.length > 4 * 1024 * 1024 || total > MAX_BYTES) throw failure("PACKAGE_EXPANSION_TOO_LARGE");
                String media = path.endsWith(".md") ? "text/markdown" : path.endsWith(".json") ? "application/json"
                        : path.matches(".*\\.(txt|yaml|yml|py|js)$") ? "text/plain" : "application/octet-stream";
                if (media.startsWith("text/")) StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(content));
                files.put(path, object("handleId", "entry-" + hash(path.getBytes(StandardCharsets.UTF_8)),
                        "logicalPath", path, "mediaType", media, "byteSize", content.length,
                        "contentDigest", digest(content), "base64", Base64.getEncoder().encodeToString(content)));
                if (files.size() > 128) throw failure("INVALID_ENTRIES");
            }
        }
        if (count != centralEntries || !files.containsKey("SKILL.md") || files.get("SKILL.md").path("byteSize").asInt() == 0) {
            throw failure("INVALID_INSTRUCTIONS");
        }
        ArrayNode entries = array(files.remove("SKILL.md")); files.values().forEach(entries::add);
        return object("entries", entries, "requiredToolNames", array());
    }
    static ArrayNode skillDependencies(JsonNode snapshot) throws IOException {
        TreeMap<String, ObjectNode> deps = new TreeMap<>();
        for (String field : new String[]{"componentBindings", "capabilityBindings"}) {
            JsonNode bindings = snapshot.path(field);
            if (!bindings.isArray()) throw failure("FROZEN_BINDING_LIST_REQUIRED");
            for (JsonNode binding : bindings) {
                boolean component = "componentBindings".equals(field);
                if (component && !"A2UI_APPLICATION".equals(binding.path("assetType").asText())) {
                    throw failure("LEGACY_COMPONENT_RUNTIME_MAPPING_UNSUPPORTED");
                }
                String kind = component ? "APPLICATION" : "ABILITY";
                String key = text(binding, component ? "componentName" : "capabilityCode"); key(kind, key);
                if (deps.put(kind + ":" + key, object("kind", kind, "key", key)) != null) throw failure("DUPLICATE_DEPENDENCY");
            }
        }
        ArrayNode result = array(); deps.values().forEach(result::add); return result;
    }
    static ArrayNode javaDependencies(String kind, String key, JsonNode definition) throws IOException {
        key(kind, key);
        if (!java.util.Set.of("ABILITY", "APPLICATION").contains(kind)
                || !"a2flow.java-rpc.v1".equals(definition.path("runtimeProfile").asText())
                || definition.size() != 6) throw failure("UNSUPPORTED_JAVA_RUNTIME_ASSET");
        for (String field : new String[]{"assetKey", "sourceId", "sourceDigest", "payloadDigest", "payloadJson"}) text(definition, field);
        if (!text(definition, "sourceDigest").matches("(?:sha256:)?[0-9a-f]{64}")) throw failure("JAVA_SOURCE_DIGEST_INVALID");
        String payload = text(definition, "payloadJson");
        if (!hash(payload.getBytes(StandardCharsets.UTF_8)).equals(text(definition, "payloadDigest").replaceFirst("^sha256:", ""))) {
            throw failure("JAVA_SNAPSHOT_DIGEST_MISMATCH");
        }
        JsonNode parsed = parse(payload);
        if (!parsed.isObject()) throw failure("INVALID_JAVA_SNAPSHOT");
        ArrayNode result = array();
        if ("ABILITY".equals(kind)) {
            if (!text(definition, "assetKey").equals(parsed.path("draftId").asText())
                    || !key.equals(parsed.path("draft").path("basicInfo").path("actionCode").asText())) {
                throw failure("JAVA_ABILITY_KEY_MISMATCH");
            }
        } else {
            if (!key.equals(parsed.path("appCode").asText()) || !key.equals(text(definition, "assetKey"))) throw failure("JAVA_APPLICATION_KEY_MISMATCH");
            if (!parsed.path("catalog").isObject() || parsed.path("catalog").path("catalogId").asText().isEmpty()
                    || parsed.path("catalog").path("digest").asText().isEmpty() || !parsed.path("componentTypes").isArray()) throw failure("JAVA_COMPILED_CATALOG_REQUIRED");
            TreeSet<String> codes = new TreeSet<>();
            for (String field : new String[]{"loadBindings", "actionBindings"}) {
                if (!parsed.path(field).isArray()) throw failure("JAVA_COMPILED_BINDINGS_REQUIRED");
                for (JsonNode binding : parsed.path(field)) { String code = text(binding.path("capability"), "actionCode"); key("ABILITY", code); codes.add(code); }
            }
            codes.forEach(code -> result.add(object("kind", "ABILITY", "key", code)));
        }
        return result;
    }
}
