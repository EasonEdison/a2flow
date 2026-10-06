package dev.a2flow.management.lifecycle.publish;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import static dev.a2flow.management.lifecycle.publish.PublicationJson.*;

public final class PublicationMaterialTest {
    interface Checked { void run() throws Exception; }
    static void rejects(Checked action) throws Exception {
        try { action.run(); throw new AssertionError("invalid material accepted"); } catch (IOException expected) { }
    }
    static byte[] archive(String path, String text) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(bytes)) { zip.putNextEntry(new ZipEntry(path)); zip.write(text.getBytes(StandardCharsets.UTF_8)); zip.closeEntry(); }
        return bytes.toByteArray();
    }
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && "--canonical".equals(args[0])) {
            try (var lines = new java.io.BufferedReader(new java.io.InputStreamReader(System.in, StandardCharsets.UTF_8))) {
                for (String line = lines.readLine(); line != null; line = lines.readLine()) System.out.println(new String(bytes(parse(line)), StandardCharsets.UTF_8));
            }
            return;
        }
        if (!new String(bytes(parse("{\"z\":null,\"中文\":\"你好\",\"a\":[1,true]}")), StandardCharsets.UTF_8).equals("{\"a\":[1,true],\"z\":null,\"中文\":\"你好\"}")) throw new AssertionError("canonical JSON");
        rejects(() -> parse("{\"a\":1,\"a\":2}"));
        byte[] archive = archive("example/SKILL.md", "# 中文说明");
        var definition = PublicationMaterial.skill("example", archive, digest(archive));
        var candidate = object("kind", "SKILL", "key", "example", "assetId", "skill-example", "versionId", "v1", "definition", definition, "dependencies", array());
        var assets = new HashMap<String, com.fasterxml.jackson.databind.JsonNode>(); assets.put("SKILL:example@v1", candidate);
        var states = new HashMap<String, com.fasterxml.jackson.databind.JsonNode>(); states.put("SKILL:example", object("kind", "SKILL", "key", "example", "current", "v1", "stable", null, "gray", null, "grayUserIds", array()));
        RuntimePublicationStore.validate(new RuntimePublicationStore.Snapshot(assets, states), "PRT");
        byte[] traversal = archive("example/../SKILL.md", "x"); rejects(() -> PublicationMaterial.skill("example", traversal, digest(traversal)));
        rejects(() -> PublicationMaterial.skill("example", archive, "sha256:bad"));
        rejects(() -> PublicationMaterial.skillDependencies(parse("{\"componentBindings\":[{\"assetType\":\"LEGACY\"}],\"capabilityBindings\":[]}")));
        candidate.set("dependencies", array(object("kind", "ABILITY", "key", "missing")));
        rejects(() -> RuntimePublicationStore.validate(new RuntimePublicationStore.Snapshot(assets, states), "PRT"));
        String payload = "{\"draftId\":\"draft-1\",\"draft\":{\"basicInfo\":{\"actionCode\":\"ability-one\"}}}";
        var java = object("runtimeProfile", "a2flow.java-rpc.v1", "assetKey", "draft-1", "sourceId", "source-1", "sourceDigest", hash(payload.getBytes(StandardCharsets.UTF_8)), "payloadDigest", digest(payload.getBytes(StandardCharsets.UTF_8)), "payloadJson", payload);
        PublicationMaterial.javaDependencies("ABILITY", "ability-one", java);
        rejects(() -> PublicationMaterial.javaDependencies("ABILITY", "other", java));
        System.out.println("PASS: canonical Unicode, duplicate keys, Skill archive, traversal, digest, dependency closure, Java envelope");
    }
}
