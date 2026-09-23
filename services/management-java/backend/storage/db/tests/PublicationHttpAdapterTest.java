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

/** Actual Java HTTP client against the temporary Python bridge, never a success mock. */
public class PublicationHttpAdapterTest {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
            zip.putNextEntry(new ZipEntry("java-client-skill/SKILL.md"));
            zip.write("# Java client skill\nExplain text.".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
        byte[] content = bytes.toByteArray();
        String digest = "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        HttpRuntimeSkillPublicationAdapter adapter = new HttpRuntimeSkillPublicationAdapter(new StandardEnvironment());
        SkillPublicationInput input = new SkillPublicationInput("java-build", digest,
                "{\"componentBindings\":[],\"capabilityBindings\":[]}", "java-client-request");
        RuntimeSkillPublicationPort.Receipt first = adapter.publish(new SkillDraft().setSkillCode("java-client-skill"),
                new ReleaseArtifact().setPackageDigest(digest), content, 1, "PRT", input);
        RuntimeSkillPublicationPort.Receipt retry = adapter.publish(new SkillDraft().setSkillCode("java-client-skill"),
                new ReleaseArtifact().setPackageDigest(digest), content, 1, "PRT", input);
        if (!first.equals(retry) || !first.requestId().equals(input.requestId()) || !first.packageDigest().equals(digest)) {
            throw new AssertionError("Java client receipt/idempotency mismatch");
        }
        System.out.println("PASS: Java HTTP publication + exact retry receipt");
    }
}
