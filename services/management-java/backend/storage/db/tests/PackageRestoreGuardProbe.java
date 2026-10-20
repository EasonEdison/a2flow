package dev.a2flow.management.lifecycle.artifact;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import dev.a2flow.management.lifecycle.SkillFactoryWorkspaceService;
import dev.a2flow.management.lifecycle.SkillFactoryValidationException;
import dev.a2flow.management.lifecycle.SkillFactoryMethodDispatcher;
import dev.a2flow.management.model.SkillFactoryExecutionResult;

/** Isolated contract probe: no database, HTTP calls, credentials or existing workspace. */
public final class PackageRestoreGuardProbe {
    private static int checks;
    public static void main(String[] args) throws Exception {
        if (args.length != 0) throw new IllegalArgumentException("This probe accepts no external paths or endpoints");
        Path root = Files.createTempDirectory("a2flow-package-guard-probe-");
        try {
            var service = limited(512, 256, 3);
            Path workspace = root.resolve("skill");
            Files.createDirectories(workspace);
            Files.writeString(workspace.resolve("original.txt"), "original");
            byte[] normal = zip(Map.of("skill/SKILL.md", "synthetic skill".getBytes(StandardCharsets.UTF_8)));
            int restored = service.restoreImmutablePackage(root, workspace, normal, "skill");
            require(restored == 1 && Files.readString(workspace.resolve("SKILL.md")).equals("synthetic skill"));
            require(!Files.exists(workspace.resolve("original.txt")));
            emptyTemporary(root);
            service.importUploadedZip(root, workspace, "skill", "skill.zip", normal);
            require(Files.readString(workspace.resolve("SKILL.md")).equals("synthetic skill"));
            emptyTemporary(root);
            Path releaseZip = root.resolve("release.zip");
            Files.write(releaseZip, normal);
            require(service.readValidatedReleasePackage(releaseZip, "skill").length == normal.length);

            // Each rejection occurs before workspace replacement, even if previous entries were extracted.
            rejectedRestore(root, workspace, limited(512, 256, 3), zip(entries("ok", 12, "oversized", 257)), "PACKAGE_ENTRY_BYTES_EXCEEDED");
            rejectedRestore(root, workspace, limited(512, 256, 3), zip(entries("first", 256, "second", 256, "third", 1)), "PACKAGE_EXPANDED_BYTES_EXCEEDED");
            rejectedRestore(root, workspace, limited(512, 256, 3), zip(entries("one", 1, "two", 1, "three", 1, "four", 1)), "PACKAGE_ENTRY_COUNT_EXCEEDED");
            rejectedRestore(root, workspace, service, zip(entries(".git/config", 257)), "PACKAGE_ENTRY_BYTES_EXCEEDED");
            rejectedRestore(root, workspace, service, zip(entries("__MACOSX/one", 256, "__MACOSX/two", 256, "good", 1)), "PACKAGE_EXPANDED_BYTES_EXCEEDED");
            rejectedRestore(root, workspace, service, zip(entries(".git/one", 0, ".git/two", 0, ".git/three", 0, ".git/four", 0)), "PACKAGE_ENTRY_COUNT_EXCEEDED");
            rejectedRestore(root, workspace, service, zip(entries("folder/", 257)), "PACKAGE_ENTRY_BYTES_EXCEEDED");
            rejectedRestore(root, workspace, service, zip(entries("one/", 0, "two/", 0, "three/", 0, "four/", 0)), "PACKAGE_ENTRY_COUNT_EXCEEDED");
            rejectedRestore(root, workspace, service, zip(entries("../outside", 1)), "restore path outside workspace");
            require(!Files.exists(root.resolve("outside")));
            rejectedRestore(root, workspace, service, zip(Map.of()), "zip package is empty");
            rejectedRestore(root, workspace, service, zip(entries(".git/config", 1)), "zip package is empty");
            rejectedRestore(root, workspace, service, new byte[]{1,2,3}, "zip package is empty");
            rejectedRestore(root, workspace, limited(0, 0, 3), normal, "PACKAGE_EXTRACTION_LIMITS_INVALID");

            expect("PACKAGE_ENTRY_BYTES_EXCEEDED", () -> service.importUploadedZip(root, workspace,
                    "skill", "skill.zip", zip(entries(".git/config", 257))));
            unchanged(workspace); emptyTemporary(root);
            Files.write(releaseZip, zip(entries("skill/SKILL.md", 12, ".git/config", 257)));
            expect("PACKAGE_ENTRY_BYTES_EXCEEDED", () -> service.readValidatedReleasePackage(releaseZip, "skill"));
            Files.write(releaseZip, zip(entries("skill/SKILL.md", 12, "skill/one", 1, "skill/two", 1, "skill/three", 1)));
            expect("PACKAGE_ENTRY_COUNT_EXCEEDED", () -> service.readValidatedReleasePackage(releaseZip, "skill"));

            // No URL is dereferenced, not even a file URL. Marker must not be copied to errors.
            for (String source : new String[]{"https://example.invalid/package.zip?signature=SYNTHETIC_PRIVATE_MARKER",
                    "http://127.0.0.1/package.zip", "file:///nonexistent/package.zip", "unsupported:package", ""}) {
                expect("PACKAGE_RESTORE_SOURCE_REQUIRED", () -> service.restorePackage(root, workspace, source));
                expect("PACKAGE_RESTORE_SOURCE_REQUIRED", () -> new SkillFactoryWorkspaceService()
                        .restorePackage("skill", source, Map.of()));
            }
            unchanged(workspace); emptyTemporary(root);
            // Confirm the existing dispatcher preserves the typed public error contract.
            var knownFailure = SkillFactoryMethodDispatcher.class.getDeclaredMethod("knownFailure", Exception.class);
            knownFailure.setAccessible(true);
            var reply = (SkillFactoryExecutionResult) knownFailure.invoke(new SkillFactoryMethodDispatcher(),
                    SkillFactoryValidationException.packageRestoreSourceRequired());
            require(!reply.isSuccess());
            require("PACKAGE_RESTORE_SOURCE_REQUIRED".equals(((Map<?,?>)reply.getData()).get("errorCode")));
            require("sourceId".equals(((Map<?,?>)reply.getData()).get("fieldPath")));
            System.out.println("{\"result\":\"PASS\",\"probe\":\"package-restore-guards\",\"checks\":" + checks
                    + ",\"externalCalls\":0,\"syntheticOnly\":true}");
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }
    private static SkillPackageArtifactService limited(long total, long perEntry, int entries) throws Exception {
        var service = new SkillPackageArtifactService();
        for (var setting : Map.<String,Object>of("maxExpandedBytes", total, "maxEntryBytes", perEntry, "maxEntries", entries).entrySet()) {
            var field = SkillPackageArtifactService.class.getDeclaredField(setting.getKey());
            field.setAccessible(true); field.set(service, setting.getValue());
        }
        return service;
    }
    private static void rejectedRestore(Path root, Path workspace, SkillPackageArtifactService service,
            byte[] bytes, String code) throws Exception {
        expect(code, () -> service.restoreImmutablePackage(root, workspace, bytes, "skill"));
        unchanged(workspace); emptyTemporary(root);
    }
    private static void unchanged(Path workspace) throws Exception {
        require(Files.readString(workspace.resolve("SKILL.md")).equals("synthetic skill"));
        try (var files = Files.list(workspace)) { require(files.count() == 1); }
    }
    private static void emptyTemporary(Path root) throws Exception {
        Path scratch = root.resolve("_restore");
        if (Files.exists(scratch)) try (var files = Files.list(scratch)) { require(files.count() == 0); }
    }
    private static Map<String,byte[]> entries(Object... pairs) {
        Map<String,byte[]> result = new LinkedHashMap<>();
        for (int index=0; index<pairs.length; index+=2) result.put((String)pairs[index], new byte[(Integer)pairs[index+1]]);
        return result;
    }
    private static byte[] zip(Map<String,byte[]> entries) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ZipOutputStream output = new ZipOutputStream(buffer)) {
            for (var entry : entries.entrySet()) {
                output.putNextEntry(new ZipEntry(entry.getKey())); output.write(entry.getValue()); output.closeEntry();
            }
        }
        return buffer.toByteArray();
    }
    private static void expect(String code, Checked action) throws Exception {
        try { action.run(); }
        catch (IllegalArgumentException expected) {
            require(expected instanceof SkillFactoryValidationException validation
                    ? validation.getErrorCode().equals(code) : expected.getMessage().startsWith(code));
            require(!expected.getMessage().contains("SYNTHETIC_PRIVATE_MARKER"));
            return;
        }
        throw new AssertionError("Expected rejection: " + code);
    }
    private static void require(boolean value) { if (!value) throw new AssertionError("Contract check failed"); checks++; }
    @FunctionalInterface private interface Checked { void run() throws Exception; }
}
