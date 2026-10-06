package dev.a2flow.management.lifecycle.publish;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import com.fasterxml.jackson.databind.JsonNode;
import static dev.a2flow.management.lifecycle.publish.PublicationJson.*;
import static dev.a2flow.management.lifecycle.publish.RuntimePublicationStore.identity;

/** Validates complete retained graph and all serving cohorts before and after writes. */
final class PublicationValidation {
    private PublicationValidation() { }
    static void validate(RuntimePublicationStore.Snapshot snapshot, String environment) throws IOException {
        if (snapshot.assets().size() > 128 || snapshot.states().size() > 128) throw failure("ASSET_LIMIT");
        Set<String> identities = new HashSet<>(), users = new HashSet<>(); users.add("");
        Map<String, String> ids = new HashMap<>(), aliases = new HashMap<>();
        Map<String, Set<String>> graph = new HashMap<>(); long size = 0;
        for (JsonNode asset : snapshot.assets().values()) {
            closed(asset, Set.of("kind", "key", "assetId", "versionId", "definition", "dependencies"));
            String kind = text(asset, "kind"), key = text(asset, "key"), id = identity(asset);
            if (!Set.of("SKILL", "ABILITY", "APPLICATION", "WORKFLOW", "COMPONENT").contains(kind)) throw failure("UNKNOWN_ASSET_KIND");
            PublicationMaterial.key(kind, key); PublicationMaterial.key("ID", text(asset, "assetId")); PublicationMaterial.key("ID", text(asset, "versionId"));
            String previous = ids.put(id, text(asset, "assetId"));
            if (previous != null && !previous.equals(text(asset, "assetId"))) throw failure("ASSET_ID_CHANGED");
            previous = aliases.put(kind + ":" + text(asset, "assetId"), key);
            if (previous != null && !previous.equals(key)) throw failure("ASSET_ID_ALIAS");
            identities.add(id); size += bytes(asset).length;
            JsonNode deps = asset.path("dependencies");
            if (!deps.isArray() || deps.size() > 128) throw failure("INVALID_DEPENDENCIES");
            Set<String> declared = new HashSet<>();
            for (JsonNode dependency : deps) {
                closed(dependency, Set.of("kind", "key"));
                String dep = identity(dependency);
                if (!declared.add(dep)) throw failure("DUPLICATE_DEPENDENCY");
                if (!snapshot.states().containsKey(dep)) throw failure("MISSING_DEPENDENCY");
            }
            graph.computeIfAbsent(id, unused -> new HashSet<>()).addAll(declared);
            JsonNode definition = asset.path("definition");
            if (!definition.isObject()) throw failure("INVALID_DEFINITION");
            if ("a2flow.java-rpc.v1".equals(definition.path("runtimeProfile").asText())) {
                for (JsonNode dep : PublicationMaterial.javaDependencies(kind, key, definition)) {
                    if (!declared.contains(identity(dep))) throw failure("MISSING_ABILITY_BINDING");
                }
            } else if ("SKILL".equals(kind)) validateSkill(definition);
            else if ("APPLICATION".equals(kind)) {
                if (!declared.contains(identity("COMPONENT", text(definition.path("asset"), "componentCatalogRef")))) throw failure("MISSING_COMPONENT_BINDING");
                if (!definition.path("actionPolicies").isArray()) throw failure("INVALID_APPLICATION");
                for (JsonNode action : definition.path("actionPolicies")) {
                    String[] reference = text(action, "abilityReleaseRef").split("@", -1);
                    if (reference.length != 2 || !declared.contains(identity("ABILITY", reference[0]))
                            || !snapshot.assets().containsKey(identity("ABILITY", reference[0]) + "@" + reference[1])) throw failure("MISSING_ABILITY_RELEASE");
                }
            } else if ("WORKFLOW".equals(kind)) {
                if (!key.equals(definition.path("definitionKey").asText()) || !definition.path("nodes").isArray()
                        || definition.path("nodes").size() < 2 || definition.path("nodes").size() > 8) throw failure("UNSUPPORTED_WORKFLOW");
                for (JsonNode node : definition.path("nodes")) if (!declared.contains(identity("SKILL", text(node, "skillKey")))) throw failure("MISSING_SKILL_BINDING");
            }
        }
        if (!identities.equals(snapshot.states().keySet())) throw failure("MISSING_SERVING_STATE");
        for (JsonNode state : snapshot.states().values()) {
            closed(state, Set.of("kind", "key", "current", "stable", "gray", "grayUserIds"));
            size += bytes(state).length;
            if (!state.path("grayUserIds").isArray() || state.path("grayUserIds").size() > 1024) throw failure("INVALID_GRAY_USERS");
            Set<String> distinct = new HashSet<>();
            for (JsonNode user : state.path("grayUserIds")) {
                if (!(user.isTextual() || user.isIntegralNumber()) || !user.asText().matches("(?:0|[1-9][0-9]*|-[1-9][0-9]*)")) throw failure("INVALID_GRAY_USERS");
                try { Long.parseLong(user.asText()); } catch (NumberFormatException exception) { throw failure("INVALID_GRAY_USERS"); }
                if (!distinct.add(user.asText())) throw failure("INVALID_GRAY_USERS"); users.add(user.asText());
            }
            if ("PRT".equals(environment)) {
                if (!state.path("current").isTextual() || !state.path("stable").isNull() || !state.path("gray").isNull() || !distinct.isEmpty()) throw failure("INVALID_PRT_SERVING");
            } else if (!state.path("current").isNull() || !state.path("stable").isTextual()) throw failure("INVALID_ONLINE_SERVING");
            if (state.path("gray").isNull() && !distinct.isEmpty()) throw failure("GRAY_VERSION_REQUIRED");
            if (!state.path("gray").isNull() && state.path("gray").equals(state.path("stable"))) throw failure("DUPLICATE_SERVING_VERSION");
            for (String slot : new String[]{"current", "stable", "gray"}) if (!state.path(slot).isNull()
                    && !snapshot.assets().containsKey(identity(state) + "@" + text(state, slot))) throw failure("MISSING_SERVING_VERSION");
        }
        if (size > MAX_BYTES) throw failure("BUNDLE_TOO_LARGE");
        for (String id : graph.keySet()) visit(id, graph, new HashSet<>(), new HashSet<>());
        for (String user : users) for (JsonNode state : snapshot.states().values()) {
            if (!"APPLICATION".equals(state.path("kind").asText())) continue;
            JsonNode application = snapshot.assets().get(identity(state) + "@" + selected(state, user, environment)).path("definition");
            if ("a2flow.java-rpc.v1".equals(application.path("runtimeProfile").asText())) continue;
            String catalogKey = text(application.path("asset"), "componentCatalogRef");
            JsonNode catalogState = snapshot.states().get(identity("COMPONENT", catalogKey));
            if (catalogState == null) throw failure("SERVING_DEPENDENCY_MISMATCH");
            JsonNode catalog = snapshot.assets().get(identity(catalogState) + "@" + selected(catalogState, user, environment)).path("definition");
            if (!catalogKey.equals(catalog.path("catalogKey").asText()) || !application.path("asset").path("protocolProfileRef").equals(catalog.path("protocolProfileRef"))) throw failure("SERVING_DEPENDENCY_MISMATCH");
            Set<String> components = new HashSet<>(); catalog.path("components").forEach(item -> components.add(item.asText()));
            if (!application.path("surfaceTemplate").path("components").isArray()) throw failure("SERVING_DEPENDENCY_MISMATCH");
            for (JsonNode component : application.path("surfaceTemplate").path("components")) if (!components.contains(text(component, "component"))) throw failure("SERVING_DEPENDENCY_MISMATCH");
            for (JsonNode action : application.path("actionPolicies")) {
                String[] reference = text(action, "abilityReleaseRef").split("@", -1);
                JsonNode ability = snapshot.states().get(identity("ABILITY", reference[0]));
                if (ability == null || !reference[1].equals(selected(ability, user, environment))) throw failure("SERVING_DEPENDENCY_MISMATCH");
            }
        }
    }
    private static String selected(JsonNode state, String user, String environment) {
        if ("PRT".equals(environment)) return state.path("current").asText();
        for (JsonNode member : state.path("grayUserIds")) if (!user.isEmpty() && member.asText().equals(user)) return state.path("gray").asText();
        return state.path("stable").asText();
    }
    private static void visit(String id, Map<String, Set<String>> graph, Set<String> stack, Set<String> visited) throws IOException {
        if (stack.contains(id)) throw failure("CYCLIC_DEPENDENCY");
        if (!visited.add(id)) return;
        stack.add(id); for (String child : graph.getOrDefault(id, Set.of())) visit(child, graph, stack, visited); stack.remove(id);
    }
    private static void closed(JsonNode node, Set<String> fields) throws IOException {
        Set<String> observed = new HashSet<>(); node.fieldNames().forEachRemaining(observed::add);
        if (!node.isObject() || !observed.equals(fields)) throw failure("INVALID_FIELDS");
    }
    private static void validateSkill(JsonNode definition) throws IOException {
        closed(definition, Set.of("entries", "requiredToolNames"));
        JsonNode entries = definition.path("entries"), names = definition.path("requiredToolNames");
        if (!entries.isArray() || entries.isEmpty() || entries.size() > 128 || !"SKILL.md".equals(entries.get(0).path("logicalPath").asText())) throw failure("INVALID_ENTRIES");
        Set<String> paths = new HashSet<>(); long total = 0;
        for (JsonNode entry : entries) {
            closed(entry, Set.of("handleId", "logicalPath", "mediaType", "byteSize", "contentDigest", "base64"));
            PublicationMaterial.key("ID", text(entry, "handleId"));
            String path = text(entry, "logicalPath");
            if (path.length() > 1024 || !path.matches("[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*") || path.split("/").length > 32
                    || java.util.Arrays.stream(path.split("/")).anyMatch(part -> part.equals(".") || part.equals("..")) || !paths.add(path)) throw failure("INVALID_ENTRY_PATH");
            byte[] content;
            if (!entry.path("base64").isTextual() || entry.path("base64").asText().length() > 6 * 1024 * 1024) throw failure("INVALID_ENTRY_BYTES");
            try { content = Base64.getDecoder().decode(entry.path("base64").asText()); } catch (IllegalArgumentException exception) { throw failure("INVALID_ENTRY_BYTES"); }
            total += content.length;
            if (content.length > 4 * 1024 * 1024 || total > MAX_BYTES || !entry.path("byteSize").isIntegralNumber() || entry.path("byteSize").asLong() != content.length
                    || !digest(content).equals(text(entry, "contentDigest"))) throw failure("INVALID_ENTRY_BYTES");
            if (text(entry, "mediaType").length() > 128) throw failure("INVALID_MEDIA_TYPE");
            if (text(entry, "mediaType").toLowerCase(java.util.Locale.ROOT).startsWith("text/")) StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(content));
            if ("SKILL.md".equals(path) && (content.length == 0 || !text(entry, "mediaType").startsWith("text/"))) throw failure("INVALID_INSTRUCTIONS");
        }
        if (!names.isArray() || names.size() > 32) throw failure("INVALID_TOOL_HINTS");
        Set<String> seen = new HashSet<>();
        for (JsonNode name : names) { PublicationMaterial.key("ID", name.asText()); if (!seen.add(name.asText())) throw failure("INVALID_TOOL_HINTS"); }
    }
}
