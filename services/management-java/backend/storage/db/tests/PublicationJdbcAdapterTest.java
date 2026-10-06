package dev.a2flow.management.lifecycle.publish;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.springframework.core.env.StandardEnvironment;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;

/** Actual Java JDBC client against explicitly configured isolated PostgreSQL databases. */
public class PublicationJdbcAdapterTest {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
            zip.putNextEntry(new ZipEntry("java-client-skill/SKILL.md"));
            zip.write("# Java client skill\nExplain text.".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
        byte[] content = bytes.toByteArray();
        String digest = "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        RuntimePublicationStore store = new RuntimePublicationStore(new StandardEnvironment());
        JdbcRuntimeSkillPublicationAdapter adapter = new JdbcRuntimeSkillPublicationAdapter(store);
        SkillPublicationInput input = new SkillPublicationInput("java-build", digest,
                "{\"componentBindings\":[],\"capabilityBindings\":[]}", "java-client-request");
        RuntimeSkillPublicationPort.Receipt first = adapter.publish(new SkillDraft().setSkillCode("java-client-skill"),
                new ReleaseArtifact().setPackageDigest(digest), content, 1, "PRT", input);
        RuntimeSkillPublicationPort.Receipt retry = adapter.publish(new SkillDraft().setSkillCode("java-client-skill"),
                new ReleaseArtifact().setPackageDigest(digest), content, 1, "PRT", input);
        if (!first.equals(retry) || !first.requestId().equals(input.requestId()) || !first.packageDigest().equals(digest)) {
            throw new AssertionError("Java client receipt/idempotency mismatch");
        }
        try {
            adapter.publish(new SkillDraft().setSkillCode("java-client-skill"), new ReleaseArtifact().setPackageDigest(digest), content, 1, "PRT",
                    new SkillPublicationInput("other-build", digest, input.snapshotJson(), input.requestId()));
            throw new AssertionError("request collision accepted");
        } catch (java.io.IOException expected) { if (!"REQUEST_ID_CONFLICT".equals(expected.getMessage())) throw expected; }
        var online = adapter.publish(new SkillDraft().setSkillCode("java-client-skill"), new ReleaseArtifact().setPackageDigest(digest), content, 1, "ONLINE", input);
        if (!"ONLINE".equals(online.environment())) throw new AssertionError("environment isolation");
        var definition = PublicationMaterial.skill("java-client-skill", content, digest);
        var request = PublicationJson.object("sourceId", "cas-source", "sourceDigest", digest, "requestId", "cas-request", "packageDigest", digest);
        try {
            store.publish("SKILL", "java-client-skill", "PRT", "cas-request", request, "cas-version", definition,
                    PublicationJson.array(), PublicationJson.digest(PublicationJson.bytes(null)));
            throw new AssertionError("stale CAS accepted");
        } catch (java.io.IOException expected) { if (!"STALE_SERVING_SELECTION".equals(expected.getMessage())) throw expected; }
        String abilityPayload = "{\"draftId\":\"draft-parity\",\"draft\":{\"basicInfo\":{\"actionCode\":\"ability-parity\"}},\"fraction\":1e-7,\"中文\":\"留存原文\"}";
        publishJava(store, "ABILITY", "ability-parity", "draft-parity", abilityPayload, "ability-request");
        String applicationPayload = "{\"appCode\":\"application-parity\",\"catalog\":{\"catalogId\":\"catalog\",\"digest\":\"compiled\"},\"componentTypes\":[],\"loadBindings\":[{\"capability\":{\"actionCode\":\"ability-parity\"}}],\"actionBindings\":[]}";
        publishJava(store, "APPLICATION", "application-parity", "application-parity", applicationPayload, "application-request");
        String selection = store.selection("SKILL", "java-client-skill", "PRT");
        try {
            store.publish("SKILL", "java-client-skill", "PRT", "missing-request", PublicationJson.object("sourceId", "missing", "sourceDigest", digest, "requestId", "missing-request", "packageDigest", digest),
                    "missing-version", definition, PublicationJson.array(PublicationJson.object("kind", "ABILITY", "key", "absent")), selection);
            throw new AssertionError("missing dependency accepted");
        } catch (java.io.IOException expected) { if (!"MISSING_DEPENDENCY".equals(expected.getMessage())) throw expected; }
        if (!selection.equals(store.selection("SKILL", "java-client-skill", "PRT"))) throw new AssertionError("failed write changed serving");
        System.out.println("PASS: Java JDBC publication, exact retry, collision, PRT/ONLINE separation");
    }
    static void publishJava(RuntimePublicationStore store, String kind, String key, String assetKey, String payload, String requestId) throws Exception {
        String digest = PublicationJson.digest(payload.getBytes(StandardCharsets.UTF_8));
        var definition = PublicationJson.object("runtimeProfile", "a2flow.java-rpc.v1", "assetKey", assetKey, "sourceId", "source-" + key,
                "sourceDigest", digest, "payloadDigest", digest, "payloadJson", payload);
        var request = PublicationJson.object("kind", kind, "key", key, "environment", "PRT", "assetKey", assetKey, "sourceId", "source-" + key,
                "sourceDigest", digest, "payloadDigest", digest, "payloadJson", payload, "requestId", requestId);
        String version = "java-" + PublicationJson.hash(PublicationJson.bytes(PublicationJson.array("source-" + key, digest)));
        String receiptId = "runtime:" + PublicationJson.hash(PublicationJson.bytes(PublicationJson.array(kind, key, requestId)));
        var first = store.publish(kind, key, "PRT", receiptId, request, version, definition, PublicationMaterial.javaDependencies(kind, key, definition), store.selection(kind, key, "PRT"));
        var retry = store.publish(kind, key, "PRT", receiptId, request, version, definition, PublicationMaterial.javaDependencies(kind, key, definition), store.selection(kind, key, "PRT"));
        if (!first.equals(retry)) throw new AssertionError("Java material receipt retry");
        var context = new dev.a2flow.management.release.ReleaseModels.ReleasePublishContext()
                .setEnvironment(dev.a2flow.management.release.ReleaseEnvironment.PRT).setAssetKey(assetKey)
                .setSourceId("source-" + key).setRequestId(requestId)
                .setSnapshot(new dev.a2flow.management.release.ReleaseModels.AssetSnapshot().setDigest(digest).setPayloadJson(payload));
        var publicReceipt = new RuntimeAssetPublisher(store).publish(kind, key, context);
        if (!publicReceipt.versionId().equals(version) || !publicReceipt.contentDigest().equals(first.path("contentDigest").asText())) throw new AssertionError("publisher port parity");
    }
}
